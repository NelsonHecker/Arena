import asyncio
import os
import tempfile
from pathlib import Path

import arena_runtime_msgs.msg
import arena_runtime_msgs.srv
import arena_simulation_setup.tree.World as World
import geometry_msgs.msg
import launch
import launch.actions
import launch.launch_description_sources
import launch_ros.actions
import lifecycle_msgs.msg
import nav2_msgs.srv
import numpy as np
import yaml
from ament_index_python.packages import get_package_share_directory
from arena_rclpy_mixins.Async import ClientWrapper
from arena_rclpy_mixins.shared import FrameNamespace
from arena_runtime._node import NodeInterface
from arena_simulation_setup.shared import Position
from arena_simulation_setup.tree import DynamicPaths
from arena_simulation_setup.tree.World.Map import Map as MapTree

from task_generator.manager.environment_manager import EnvironmentManager
from task_generator.simulators.human.utils import ObstacleLayer

from .utils import WorldLayers, WorldMap, WorldOccupancy
from .world_manager import WorldManager

_DEFAULT_RESOLUTION = 0.05


class MapServerHandler(NodeInterface):
    """Handler functions for the map server lifecycle."""

    async def ensure_map_server(self):
        """Restart the map server if it is not active."""

        wait_interval = 15.0

        while not await self.node.wait_for_lifecycle_state_async(
            self.node.service_namespace('map_server'),
            lifecycle_msgs.msg.State.PRIMARY_STATE_ACTIVE,
            timeout=wait_interval,
        ):
            wait_interval = min(wait_interval * 2, 60.0)

            self._logger.warn('shutting down map server...')

            await self.node.change_lifecycle_state_async(self.node.service_namespace('map_server'), lifecycle_msgs.msg.Transition.TRANSITION_DESTROY)

            self._logger.warn('map server shut down.')
            self._logger.warn('relaunching map server...')

            await self.node.do_launch(launch.LaunchDescription([launch.actions.IncludeLaunchDescription(launch.launch_description_sources.PythonLaunchDescriptionSource(os.path.join(get_package_share_directory('arena_bringup'), 'launch/utils/map_server.launch.py')))]))

        self._logger.info('map server launched.')


class WorldManagerROS(MapServerHandler, WorldManager):
    """Initialize the WorldManager.

    Args:
        environment_manager (EnvironmentManager): The environment manager instance.
    """

    _environment_manager: EnvironmentManager

    _cli: ClientWrapper | None
    _cli_confirm_world: ClientWrapper
    _world_name: str
    _map_server_present: bool

    def _shift_map(self, map_dir: Path) -> tempfile.TemporaryDirectory:
        """Shift the map to the correct origin.

        Args:
            map_dir (Path): The directory containing the map files.

        Returns:
            tempfile.TemporaryDirectory: A temporary directory containing the shifted map files.
        """
        map_dir = map_dir.resolve()
        map_tmpdir = tempfile.TemporaryDirectory()

        # create shifted yaml
        target = map_dir / 'map.yaml'
        with open(target) as f:
            map_yaml = yaml.safe_load(f)
            assert isinstance(map_yaml, dict), "map.yaml must be a dictionary"
        origin = list(map_yaml.get('origin', [0, 0, 0]))
        shifted_origin = self._environment_manager.realize(
            Position(
                x=origin[0],
                y=origin[1],
            )
        )
        origin[0] = shifted_origin.x
        origin[1] = shifted_origin.y
        map_yaml['origin'] = origin
        with open(Path(map_tmpdir.name) / 'map.yaml', 'w') as f:
            yaml.safe_dump(map_yaml, f)

        # symlink all non-targets
        for item in os.listdir(map_dir):
            base = map_dir / item
            if base == target:
                continue
            os.symlink(base, Path(map_tmpdir.name) / item)

        return map_tmpdir

    def _publish_anchor_tf(self, ref_x: float, ref_y: float) -> None:
        """Publish the global `map` -> `<prefix>/map` static transform that anchors the env's local frame."""
        prefix = self.node.rosparam[str].get('prefix', '')
        t = geometry_msgs.msg.TransformStamped()
        t.header.stamp = self.node.get_clock().now().to_msg()
        t.header.frame_id = 'map'
        t.child_frame_id = FrameNamespace(prefix).tf('map')
        t.transform.translation.x = ref_x
        t.transform.translation.y = ref_y
        t.transform.translation.z = 0.0
        t.transform.rotation.w = 1.0
        self.node._static_tf_broadcaster.sendTransform(t)

    def _ensure_world_map_files(self, world: World.World, description: World.WorldDescription, resolution: float) -> None:
        """Render `map/map.png` + `map/map.yaml` if missing."""
        map_dir = world.map.path
        map_png = map_dir / 'map.png'
        map_yaml = map_dir / 'map.yaml'
        if map_png.exists() and map_yaml.exists():
            return

        os.makedirs(map_dir, exist_ok=True)
        png_bytes, origin = description.render(resolution=resolution)
        if not map_png.exists():
            map_png.write_bytes(png_bytes)
        if not map_yaml.exists():
            map_yaml.write_text(MapTree.generate_map_yaml(resolution=resolution, filename='map.png', origin=origin))

    async def apply_world(self, world_name: str) -> bool:
        """Synchronously swap to `world_name`. Must be called inside `_run_reset_cycle`'s hold."""
        self._logger.info(f'World change requested: {world_name}')

        if world_name == self._world_name:
            return True

        world = await World.WorldIdentifier(world_name).resolve()
        description = world.load()
        floors = list(description.all_floors)
        extent = arena_runtime_msgs.msg.WorldExtent()
        if floors:
            extent.x_min = float(min(f.pos.x - f.x_length / 2 for f in floors))
            extent.y_min = float(min(f.pos.y - f.y_length / 2 for f in floors))
            extent.x_max = float(max(f.pos.x + f.x_length / 2 for f in floors))
            extent.y_max = float(max(f.pos.y + f.y_length / 2 for f in floors))

        req = arena_runtime_msgs.srv.ConfirmWorld.Request()
        req.env_id = self.node._env_id
        req.extent = extent
        confirm = await self._cli_confirm_world.call_timeout(req)
        if confirm is None:
            self._logger.error(f'confirm_world timed out for world {world_name!r}; aborting world change')
            return False
        if not confirm.success:
            self._logger.error(f'confirm_world rejected world {world_name!r}: {confirm.error_msg}')
            return False

        if confirm.reallocated:
            ref_x = float(confirm.reference[0])
            ref_y = float(confirm.reference[1])
            self.node._reference = (ref_x, ref_y)
            self.node._prespawn_offset = (
                float(confirm.prespawn[0]) - ref_x,
                float(confirm.prespawn[1]) - ref_y,
            )
            self.node._realizer.set_origin(ref_x, ref_y)
            self._publish_anchor_tf(ref_x, ref_y)

        self._logger.warn(f'Loading World {world_name}')

        world_map = WorldMap.from_world_description(description, resolution=_DEFAULT_RESOLUTION, time=self.node.sim_time)
        DynamicPaths.WORLD.path = world.path
        self.update_world(world_map=world_map, world_description=description)

        self._world_name = world_name
        self.node.rosparam[str].set('world', world_name)

        if self._map_server_present:
            await self._push_world_to_map_server(world, description)

        await self._environment_manager.reset(purge=ObstacleLayer.WORLD)
        await self._environment_manager.spawn_world_obstacles(self._world)

        return True

    async def _push_world_to_map_server(self, world: World.World, description: World.WorldDescription) -> None:
        """Render+shift+LoadMap. Caller guarantees map_server is present."""
        self._ensure_world_map_files(world, description, resolution=_DEFAULT_RESOLUTION)
        tmp_map = self._shift_map(world.map.path)
        try:
            map_yaml = os.path.join(tmp_map.name, 'map.yaml')
            assert self._cli is not None
            response = await self._cli.call_timeout(nav2_msgs.srv.LoadMap.Request(map_url=f'{map_yaml}'))
        finally:
            tmp_map.cleanup()
        if response is None:
            raise RuntimeError(f'failed to load map for world {self._world_name}: service timed out')
        if response.result > 0:
            raise RuntimeError(f'failed to load map for world {self._world_name}: status code {response.result}')

    async def require_map_server(self) -> None:
        """Idempotent: lazy-launch map_server and push the current world. Safe to call concurrently."""
        async with self._map_server_lock:
            if self._map_server_present:
                return
            await self.node.do_launch(
                launch.LaunchDescription(
                    [
                        launch.actions.GroupAction(
                            [
                                launch_ros.actions.PushRosNamespace(self.node.get_fully_qualified_name()),
                                launch.actions.IncludeLaunchDescription(launch.launch_description_sources.PythonLaunchDescriptionSource(os.path.join(get_package_share_directory('arena_bringup'), 'launch/utils/map_server.launch.py'))),
                            ]
                        ),
                    ]
                )
            )
            self._cli = self.node.create_client_wrapper(
                nav2_msgs.srv.LoadMap,
                self.node.service_namespace('map_server', 'load_map'),
            )
            await self._cli.ensure()
            await self.ensure_map_server()
            self._map_server_present = True
            if self._world_name:
                world = await World.WorldIdentifier(self._world_name).resolve()
                await self._push_world_to_map_server(world, world.load())

    def __init__(self, *args: object, environment_manager: EnvironmentManager, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._environment_manager = environment_manager

        self.update_world(
            world_map=WorldMap(
                occupancy=WorldLayers(walls=WorldOccupancy(np.full((1, 1), WorldOccupancy.EMPTY, dtype=np.uint8))),
                origin=Position(x=0.0, y=0.0),
                resolution=_DEFAULT_RESOLUTION,
                time=self.node.sim_time,
            ),
            world_description=World.WorldDescription(),
        )
        self._world_name = ''
        self._cli = None
        self._map_server_present = False
        self._map_server_lock = asyncio.Lock()

    async def start(self):
        """Start the world manager."""
        self._logger.info("starting")

        self._cli_confirm_world = self.node.create_client_wrapper(
            arena_runtime_msgs.srv.ConfirmWorld,
            "/arena/confirm_world",
        )
        await self._cli_confirm_world.ensure()

        initial_world = self.node.conf.Arena.WORLD.value
        if initial_world:
            await self.apply_world(initial_world)

    @property
    def loaded_world(self) -> str:
        """Currently loaded world. Read `node._episodes.current.world` for the intended next-episode world (the two diverge briefly during a reset cycle)."""
        return self._world_name

    async def sync(self, timeout: float = -1) -> bool:
        """Wait until at least one world has been applied. Used by external lifecycle callers."""
        start_time = self.node.get_clock().now().seconds_nanoseconds()[0]
        while not self._world_name:
            await asyncio.sleep(0.01)
            if timeout >= 0:
                elapsed = self.node.get_clock().now().seconds_nanoseconds()[0] - start_time
                if elapsed >= timeout:
                    return False
        return True
