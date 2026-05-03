import asyncio
import os
import tempfile
import traceback
import typing
from pathlib import Path

import arena_runtime_msgs.msg
import arena_runtime_msgs.srv
import arena_simulation_setup.tree.World as World
import geometry_msgs.msg
import launch
import launch.actions
import launch.launch_description_sources
import lifecycle_msgs.msg
import nav2_msgs.srv
import nav_msgs.msg
import numpy as np
import yaml
from ament_index_python.packages import get_package_share_directory
from arena_rclpy_mixins.Async import ClientWrapper
from arena_rclpy_mixins.shared import FrameNamespace
from arena_rclpy_mixins.Time import Time
from arena_runtime._node import NodeInterface
from arena_simulation_setup.shared import Position
from arena_simulation_setup.tree import DynamicPaths

from task_generator.manager.environment_manager import EnvironmentManager

from .utils import WorldMap
from .world_manager import WorldManager

_DUMMY_MAP_SHAPE = (1, 1)
_DUMMY_MAP_PADDING = 1
_DUMMY_MAP = nav_msgs.msg.OccupancyGrid(
    info=nav_msgs.msg.MapMetaData(
        height=_DUMMY_MAP_SHAPE[0] + 2 * _DUMMY_MAP_PADDING,
        width=_DUMMY_MAP_SHAPE[1] + 2 * _DUMMY_MAP_PADDING,
        resolution=0.1,
        map_load_time=Time(-1, 0).to_msg(),
    ),
    data=list(
        np.pad(
            np.zeros(
                (_DUMMY_MAP_SHAPE[0], _DUMMY_MAP_SHAPE[1]),
                dtype=int,
            ),
            ((_DUMMY_MAP_PADDING, _DUMMY_MAP_PADDING), (_DUMMY_MAP_PADDING, _DUMMY_MAP_PADDING)),
            mode='constant',
            constant_values=1,
        ).flat
    ),
)


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

    _cli: ClientWrapper
    _cli_confirm_world: ClientWrapper
    _world_name: str
    _origin: Position | None
    _map_name: str | None
    _callbacks: list[typing.Callable[[], typing.Awaitable[None]]]

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
        self._origin = Position(
            x=origin[0],
            y=origin[1],
        )
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
        t.child_frame_id = FrameNamespace(prefix)('map').sanitize()
        t.transform.translation.x = ref_x
        t.transform.translation.y = ref_y
        t.transform.translation.z = 0.0
        t.transform.rotation.w = 1.0
        self.node._static_tf_broadcaster.sendTransform(t)

    def _world_callback(self, value: object) -> bool:
        """Handle world change events.

        Args:
            value (typing.Any): The new world value.

        Raises:
            RuntimeError: If the world cannot be changed.
            RuntimeError: If the world is not valid.

        Returns:
            bool: True if the world was changed successfully, False otherwise.
        """
        world_name = str(value)
        self._logger.info(f'World change requested: {world_name}')

        # if world_name != self._world_name and \
        #         (simulator := self.node.conf.Arena.SIM.value) in (Constants.Simulator.GAZEBO,):
        #     raise RuntimeError(
        #         f'Simulator {simulator.value} does not support world reloading.')

        if world_name == self._world_name:
            return True  # no change

        world = World.WorldIdentifier(world_name).resolve_sync()
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
        confirm = self._cli_confirm_world.call_timeout_sync(req)
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
        self._world_name = world_name

        tmp_map = self._shift_map(world.map.path)
        map_yaml = os.path.join(
            tmp_map.name,
            'map.yaml',
        )

        response = self._cli.call_timeout_sync(nav2_msgs.srv.LoadMap.Request(map_url=f'{map_yaml}'))

        tmp_map.cleanup()

        if response is None:
            raise RuntimeError(f'failed to load map for world {world_name}: service timed out')

        if response.result > 0:
            raise RuntimeError(f'failed to load map for world {world_name}: status code {response.result}')

        return True

    async def _map_callback(self, costmap: nav_msgs.msg.OccupancyGrid):
        """Handle incoming map updates.

        Args:
            costmap (nav_msgs.msg.OccupancyGrid): The updated costmap.
        """
        if self._map.time <= costmap.info.map_load_time:
            world = await World.WorldIdentifier(self.world_name).resolve()
            world_map = WorldMap.from_costmap(costmap)

            if self._origin is not None:
                world_map.origin = self._origin
                self._origin = None

            DynamicPaths.WORLD.path = world.path
            self.update_world(world_map=world_map, world_description=world.load())

            self._map_name = self.world_name
            try:
                await asyncio.gather(*(callback() for callback in self._callbacks))
            except Exception as e:
                self._logger.warning(f'encountered exception in world callback: {e}\n{traceback.format_exc()}')

    def on_world_change(self, callback: typing.Callable[[], typing.Awaitable[None]]):
        """Register a callback to be called when the world changes.

        Args:
            callback (typing.Callable[[], None]): The callback to register.
        """
        self._callbacks.append(callback)

    def __init__(self, *args: object, environment_manager: EnvironmentManager, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._environment_manager = environment_manager

        self._callbacks = []
        self.update_world(world_map=WorldMap.from_costmap(_DUMMY_MAP), world_description=World.WorldDescription())
        self._world_name = ''
        self._origin = None
        self._map_name = None

    async def start(self):
        """Start the world manager."""
        self._logger.info("starting")

        # retrieving map from map_server
        self.node.create_subscription(
            nav_msgs.msg.OccupancyGrid,
            self.node.service_namespace('map'),
            self._map_callback,
            1,
        )

        await self.ensure_map_server()

        # publishing map to map_server
        self._cli = self.node.create_client_wrapper(
            nav2_msgs.srv.LoadMap,
            self.node.service_namespace('map_server', 'load_map'),
        )
        await self._cli.ensure()

        self._cli_confirm_world = self.node.create_client_wrapper(
            arena_runtime_msgs.srv.ConfirmWorld,
            "/arena/confirm_world",
        )
        await self._cli_confirm_world.ensure()

        self.node.rosparam.callback(
            'world',
            self._world_callback,
        )

    async def sync(self, timeout: float = -1) -> bool:
        """Synchronize the world and map names.

        Args:
            timeout (float, optional): The maximum time to wait for synchronization. Defaults to -1.

        Returns:
            bool: True if synchronization was successful, False otherwise.
        """
        start_time = self.node.get_clock().now().seconds_nanoseconds()[0]
        while self._map_name != self._world_name:
            await asyncio.sleep(0.01)
            if timeout >= 0:
                elapsed = self.node.get_clock().now().seconds_nanoseconds()[0] - start_time
                if elapsed >= timeout:
                    return False
        return True

    @property
    def world_name(self) -> str:
        """Get the current world name.

        Returns:
            str: The current world name.
        """
        return self._world_name

    @property
    def world(self) -> World.WorldDescription:
        """Get the current world description.

        Returns:
            World.WorldDescription: The current world description.
        """
        return self._world
