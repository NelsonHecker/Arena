
import os
import tempfile
import time
import typing
from pathlib import Path

import arena_simulation_setup.tree.World as World
import launch.actions
import lifecycle_msgs.msg
import nav2_msgs.srv
import nav_msgs.msg
import numpy as np
import rclpy
import rclpy.callback_groups
import rclpy.client
import yaml
from ament_index_python.packages import get_package_share_directory
from arena_simulation_setup.shared import Position
from arena_simulation_setup.tree import Resolvers

import launch
from task_generator import NodeInterface
from task_generator.manager.environment_manager import EnvironmentManager
from task_generator.utils.time import Time

from .utils import WorldMap
from .world_manager import WorldManager

_DUMMY_MAP_SHAPE = (1, 1)
_DUMMY_MAP_PADDING = 1
_DUMMY_MAP = nav_msgs.msg.OccupancyGrid(
    info=nav_msgs.msg.MapMetaData(
        height=_DUMMY_MAP_SHAPE[0] + 2 * _DUMMY_MAP_PADDING,
        width=_DUMMY_MAP_SHAPE[1] + 2 * _DUMMY_MAP_PADDING,
        resolution=0.1,
        map_load_time=Time(-1, 0).to_time(),
    ),
    data=list(
        np.pad(
            np.zeros(
                (_DUMMY_MAP_SHAPE[0], _DUMMY_MAP_SHAPE[1]),
                dtype=int,
            ),
            ((_DUMMY_MAP_PADDING, _DUMMY_MAP_PADDING), (_DUMMY_MAP_PADDING, _DUMMY_MAP_PADDING)),
            mode='constant',
            constant_values=1
        ).flat
    )
)


class MapServerHandler(NodeInterface):
    """Handler functions for the map server lifecycle.
    """

    def restart_map_server(self):
        """Restart the map server if it is not active.
        """
        self._logger.warn('shutting down map server...')

        change_state_client = self.node.create_client(
            lifecycle_msgs.srv.ChangeState,
            self.node.service_namespace('map_server', 'change_state')
        )
        while not change_state_client.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().warn('ChangeState service not available, waiting again...')

        request = lifecycle_msgs.srv.ChangeState.Request()
        request.transition.id = lifecycle_msgs.msg.Transition.TRANSITION_DESTROY
        change_state_client.call(request)

        self._logger.warn('map server shut down.')
        self._logger.warn('relaunching map server...')

        self.node.do_launch(
            launch.LaunchDescription([
                launch.actions.IncludeLaunchDescription(
                    launch.launch_description_sources.PythonLaunchDescriptionSource(
                        os.path.join(
                            get_package_share_directory('arena_bringup'),
                            'launch/utils/map_server.launch.py'
                        )
                    )
                )
            ])
        )

        self._logger.warn('map server relaunched.')

    def check_map_server(self, timeout: float = 10.0, period: float = 1.0) -> bool:
        """Check if the map server is active.

        Args:
            timeout (float, optional): Time to wait for the map server to become active. Defaults to 10.0.
            period (float, optional): Time to wait between checks. Defaults to 1.0.

        Returns:
            bool: True if the map server is active, False otherwise.
        """
        while self.node.get_lifecycle_state(
            self.node.service_namespace('map_server'),
            callback_group=rclpy.callback_groups.ReentrantCallbackGroup(),
        ).id != lifecycle_msgs.msg.State.PRIMARY_STATE_ACTIVE:
            self.node.get_logger().warn('map_server is not active, waiting again...')
            time.sleep(period if timeout > period else timeout)
            timeout -= period
            if timeout <= 0:
                return False
        return True


class WorldManagerROS(MapServerHandler, WorldManager):
    """Initialize the WorldManager.

    Args:
        environment_manager (EnvironmentManager): The environment manager instance.
    """

    _environment_manager: EnvironmentManager

    _cli: rclpy.client.Client
    _world_name: str
    _map_name: str | None
    _callbacks: list[typing.Callable[[], None]]

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
        with open(target, 'r') as f:
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

    def _world_callback(self, value: typing.Any) -> bool:
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

        # if world_name != self._world_name and \
        #         (simulator := self.node.conf.Arena.SIM.value) in (Constants.Simulator.GAZEBO,):
        #     raise RuntimeError(
        #         f'Simulator {simulator.value} does not support world reloading.')

        self._logger.warn(f'LOADING WORLD {world_name}')
        self._world_name = world_name

        tmp_map = self._shift_map(
            World.World(world_name).map.path
        )
        map_yaml = os.path.join(
            tmp_map.name,
            'map.yaml',
        )
        response = self._cli.call(
            nav2_msgs.srv.LoadMap.Request(
                map_url=f'{map_yaml}'
            )
        )

        tmp_map.cleanup()

        if response is None:
            raise RuntimeError(
                f'failed to load map for world {world_name}: service timed out')

        if response.result > 0:
            raise RuntimeError(
                f'failed to load map for world {world_name}: status code {response.result}')

        return True

    def _map_callback(self, costmap: nav_msgs.msg.OccupancyGrid):
        """Handle incoming map updates.

        Args:
            costmap (nav_msgs.msg.OccupancyGrid): The updated costmap.
        """
        if self._map.time <= costmap.info.map_load_time:

            world = World.World(self.world_name)

            Resolvers.set_world_dir(world.path)
            self.update_world(
                world_map=WorldMap.from_costmap(costmap),
                world_description=world.load()
            )

            self._map_name = self.world_name

            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    self._logger.warning(f'encountered exception in world callback: {repr(e)}')
                    import sys
                    import traceback
                    traceback.print_exc(file=sys.stderr)

    def _setup_world_callbacks(self):
        """Set up callbacks for world events.
        """

        # retrieving map from map_server
        self.node.create_subscription(
            nav_msgs.msg.OccupancyGrid,
            self.node.service_namespace('map'),
            self._map_callback,
            1,
        )

        while not self.check_map_server():
            self.restart_map_server()

        # publishing map to map_server
        self._cli = self.node.create_client(
            nav2_msgs.srv.LoadMap,
            self.node.service_namespace('map_server', 'load_map'),
        )
        while not self._cli.wait_for_service(timeout_sec=1.0):
            self._logger.warn('LoadMap service not available, waiting again...')

        self.node.rosparam.callback(
            'world',
            self._world_callback,
        )

    def on_world_change(self, callback: typing.Callable[[], None]):
        """Register a callback to be called when the world changes.

        Args:
            callback (typing.Callable[[], None]): The callback to register.
        """
        self._callbacks.append(callback)

    def __init__(self, environment_manager: EnvironmentManager) -> None:
        WorldManager.__init__(self)
        self._environment_manager = environment_manager

        self._callbacks = []
        self.update_world(world_map=WorldMap.from_costmap(_DUMMY_MAP), world_description=World.WorldDescription())
        self._world_name = ''
        self._map_name = None

    def start(self):
        """Start the world manager.
        """
        self._setup_world_callbacks()

    def sync(self, timeout: float = -1) -> bool:
        """Synchronize the world and map names.

        Args:
            timeout (float, optional): The maximum time to wait for synchronization. Defaults to -1.

        Returns:
            bool: True if synchronization was successful, False otherwise.
        """
        if timeout < 0:
            timeout = float('inf')
        while self._map_name != self._world_name:
            time.sleep(dt := 1)
            timeout -= dt
            if timeout < 0:
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
