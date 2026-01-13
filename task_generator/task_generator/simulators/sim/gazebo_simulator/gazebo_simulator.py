import asyncio
import itertools
import math
import time
import traceback
from pathlib import Path
import typing

import arena_robots.Robot
import launch_ros
from arena_simulation_setup.tree.assets.Object import ObjectIdentifier
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from ros_gz_interfaces.msg import Entity as EntityMsg
from ros_gz_interfaces.msg import EntityFactory, WorldControl
from ros_gz_interfaces.srv import ControlWorld, DeleteEntity, SetEntityPose, SpawnEntity

import launch
from task_generator.shared import (
    Entity,
    Model,
    ModelType,
    ModelWrapper,
    Pose,
    Robot,
    Wall,
    FrameNamespace,
)
from task_generator.simulators.sim import BaseSim

from .robot_bridge import BridgeConfiguration

# sanitize frames, gazebo does not support slashes
FrameNamespace.auto_sanitize()


class GazeboSimulator(BaseSim):

    def __init__(self, *args, namespace, **kwargs):
        super().__init__(*args, namespace=namespace, **kwargs)

        self._logger.info(f"Initializing GazeboSimulator with namespace: {namespace}")

        self._goal_pub = self.node.create_publisher(
            PoseStamped,
            self._namespace("goal"),
            10,
        )
        self.entities: dict[str, Entity] = {}
        self._walls_entities: list[str] = []
        self._wall_counter = itertools.count()

    async def before_reset_task(self):
        self._logger.info("Pausing simulation before reset")
        return bool(await self.pause_simulation())

    async def after_reset_task(self):
        self._logger.info("Unpausing simulation after reset")
        try:
            return await self.unpause_simulation()
        except Exception as e:
            self._logger.error(
                f"Error unpausing simulation: {str(e)}")
            traceback.print_exc()
            raise

    async def obstacle_spawn(self, obstacles):
        return await asyncio.gather(*map(self._spawn_entity, obstacles))

    async def pedestrian_spawn(self, pedestrians):
        return await asyncio.gather(*map(self._spawn_entity, pedestrians))

    async def robot_spawn(self, robots):

        async def impl(robot: Robot) -> bool:
            if not await self._spawn_entity(robot):
                return False
            model = await (await robot.model.resolve()).model.get(ModelType.URDF, loader_args=robot.asdict())
            if model.type is ModelType.UNKNOWN:
                return False
            model_description = model.description
            self._robot_initialpose(robot)
            await self._robot_bridge(robot, model_description)
            return True
        success = await asyncio.gather(*map(impl, robots))
        return success

    async def obstacle_move(self, obstacles):
        return await asyncio.gather(*map(self._move_entity, obstacles))

    async def pedestrian_move(self, pedestrians):
        # Gazebo does not support modifying actors after spawning
        return (True,) * len(pedestrians)

    async def robot_move(self, robots):
        async def impl(robot: Robot) -> bool:
            return (await self._move_entity(robot)) and (await self._robot_move(robot))
        return await asyncio.gather(*map(impl, robots))

    async def obstacle_delete(self, obstacles):
        return await asyncio.gather(*(self._delete_entity(o.name) for o in obstacles))

    async def pedestrian_delete(self, pedestrians):
        # Gazebo does not support deleting actors after spawning
        return (True,) * len(pedestrians)

    async def robot_delete(self, robots):
        return await asyncio.gather(*(self._delete_entity(robot.name) for robot in robots))

    async def pedestrian_update(self, pedestrians):
        # Gazebo does not support modifying actors after spawning
        return (True,) * len(pedestrians.pedestrians)

    async def spawn_floors(self, floors):
        # Gazebo does not support spawning floors
        del floors
        return True

    async def spawn_doors(self, doors):
        # Gazebo does not support spawning doors
        del doors
        return True

    async def spawn_elevators(self, elevators):
        # Gazebo does not support spawning elevators
        del elevators
        return True

    # IMPL

    async def _move_entity(self, entity: Entity):
        name = entity.sim_path
        pose = entity.pose
        self._logger.debug(f"Attempting to move entity: {name}")
        self._logger.debug(f"Moving entity {name} to position: {pose}")

        request = SetEntityPose.Request()
        request.entity = EntityMsg(
            name=name,
            type=EntityMsg.MODEL,
        )
        request.pose = pose.to_msg()

        try:
            await self._service_set_entity_pose.ensure()
            result = await self._service_set_entity_pose.call_timeout(request)

            if result is None:
                self._logger.error(f"Move service call failed for {name}")
                return False

            self._logger.info(f"Move result for {name}: {result.success}")

            return result.success

        except Exception as e:
            self._logger.error(f"Error moving entity {name}: {str(e)}")
            traceback.print_exc()
            return False

    async def _spawn_entity(self, entity: Entity) -> bool:
        try:
            # Create spawn request
            request = SpawnEntity.Request()
            request.entity_factory = EntityFactory()
            request.entity_factory.name = entity.sim_path

            # Get model description
            try:
                if isinstance(entity, Robot):
                    model = await (await entity.model.resolve()).model.get(ModelType.URDF, loader_args=entity.asdict())
                else:
                    model = await (await entity.model.resolve()).get(ModelType.SDF)
            except Exception as e:
                self._logger.error(f"Error resolving model for entity {entity.name}: {e}\n{traceback.format_exc()}")
                return False

            if model.type is ModelType.UNKNOWN:
                return False

            model_description = model.description
            request.entity_factory.sdf = model_description

            # Set pose
            request.entity_factory.pose = entity.pose.to_msg()

            self._logger.debug(
                f"Spawn position for {entity.name}: x={entity.pose.position.x}, y={entity.pose.position.y}")

            self._logger.debug(f"Sending spawn request for {entity.name}")
            result = await self._service_spawn_entity.call_timeout(request)

            if result is None:
                self._logger.error(
                    f"Spawn service call failed for {entity.name}")
                return False

            self._logger.debug(
                f"Spawn result for {entity.name}: {result.success}")

            self.entities[entity.name] = entity

            return result.success

        except Exception as e:
            self._logger.error(
                f"Error spawning entity {entity.name}: {str(e)}")
            traceback.print_exc()
            return False

    async def _delete_entity(self, name: str):
        name = name

        self._logger.debug(f"Attempting to delete entity: {name}")

        if name not in self.entities:
            return False

        self._logger.debug(f"Attempting to delete entity: {name}")
        request = DeleteEntity.Request()
        request.entity = EntityMsg(
            name=name,
            type=EntityMsg.MODEL,
        )

        try:
            result = await self._service_delete_entity.call_timeout(request)

            if result is None:
                self._logger.error(f"Delete service call failed for {name}")
                return False

            self._logger.debug(f"Delete result for {name}: {result.success}")

            if result.success:
                del self.entities[name]

            return result.success

        except Exception as e:
            self._logger.error(f"Error deleting entity {name}: {str(e)}")
            traceback.print_exc()
            return False

    async def pause_simulation(self):
        self._logger.debug("Attempting to pause simulation")
        request = ControlWorld.Request()
        request.world_control = WorldControl()
        request.world_control.pause = True

        try:
            result = await self._service_control_world.call_timeout(request)

            if result is None:
                self._logger.error("Pause service call failed")
                return False

            self._logger.debug(f"Pause result: {result.success}")
            return result.success

        except Exception as e:
            self._logger.error(f"Error pausing simulation: {str(e)}")
            traceback.print_exc()
            return False

    async def unpause_simulation(self):
        self._logger.debug("Attempting to unpause simulation")
        request = ControlWorld.Request()
        request.world_control = WorldControl()
        request.world_control.pause = False

        try:
            result = await self._service_control_world.call_timeout(request)

            if result is None:
                self._logger.error("Unpause service call failed")
                return False

            self._logger.debug(f"Unpause result: {result.success}")
            return result.success

        except Exception as e:
            self._logger.error(f"Error unpausing simulation: {str(e)}")
            traceback.print_exc()
            return False

    async def step_simulation(self, steps):
        self._logger.info(f"Stepping simulation by {steps} steps")
        request = ControlWorld.Request()
        request.world_control = WorldControl()
        request.world_control.multi_step = steps

        try:
            result = await self._service_control_world.call_timeout(request)

            if result is None:
                self._logger.error("Step service call failed")
                return False

            self._logger.debug(f"Step result: {result.success}")
            return result.success

        except Exception as e:
            self._logger.error(f"Error stepping simulation: {str(e)}")
            traceback.print_exc()
            return False

    def _publish_goal(self, goal: Pose):
        self._logger.info(f"Publishing goal: x={goal.position.x}, y={goal.position.y}, orientation={goal.orientation}")
        goal_msg = PoseStamped()
        goal_msg.header.stamp = self.node.sim_time.to_msg()
        goal_msg.header.frame_id = "map"
        goal_msg.pose = goal.to_msg()
        self._goal_pub.publish(goal_msg)
        self._logger.info("Goal published")

    async def spawn_walls(self, walls) -> bool:
        await self.remove_world()  # Clear existing walls
        for wall in walls:  # only walls, ignore obstacles
            wall_name = self.node._environment_manager.realize(f"wall_{next(self._wall_counter)}")
            wall_height = 2.0  # Wall height in meters
            wall_thickness = 0.05  # Wall thickness in meters
            base_position = (0, 0, 0)  # Offset the wall to (10, 10, 0)

            self._logger.info(f"Attempting to spawn wall: {wall_name} from {wall.start} to {wall.end}")

            # Generate the SDF string for walls
            wall_sdf = _generate_wall_sdf(
                name=wall_name,
                walls=[wall],
                height=wall_height,
                thickness=wall_thickness,
                base_position=base_position
            )

            if not wall_sdf:
                self._logger.error(f"Failed to generate SDF for wall: {wall_name}")
                continue

            entity = Entity(
                pose=Pose(),
                model=ObjectIdentifier.inline(
                    ModelWrapper.from_model(
                        Model(
                            type=ModelType.SDF,
                            name=wall_name,
                            description=wall_sdf,
                            path=Path(''),
                        )
                    )
                ),
                name=wall_name,
                extra={},
            )

            await self._spawn_entity(entity)
            self._walls_entities.append(wall_name)

        return True

    async def remove_world(self) -> bool:
        for entity in self._walls_entities:
            await self._delete_entity(entity)
        self._walls_entities = []
        self._wall_counter = itertools.count()
        return True

    async def _robot_bridge(self, robot: Robot, description: str):
        launch_description = launch.LaunchDescription()

        launch_description.add_action(
            launch_ros.actions.PushRosNamespace(
                namespace=self.node.service_namespace(robot.name)
            )
        )

        robot_config = arena_robots.Robot.RobotIdentifier(robot.model.name).resolve_sync()

        mappings = BridgeConfiguration.from_file(
            robot_config.mappings
        ).substitute({
            'robot_name': robot.sim_path,
            'world': '/world/default',
        })

        bridge_arguments = mappings.as_args()
        remappings = mappings.as_remappings()

        # Add parameter_bridge node
        launch_description.add_action(
            launch_ros.actions.Node(
                package='ros_gz_bridge',
                executable='parameter_bridge',
                output='screen',
                arguments=bridge_arguments,
                remappings=remappings,
                parameters=[{'use_sim_time': True}],
            )
        )
        launch_description.add_action(
            launch_ros.actions.Node(
                package='robot_state_publisher',
                executable='robot_state_publisher',
                name='robot_state_publisher',
                output='screen',
                parameters=[
                    {'use_sim_time': True},
                    {'robot_description': description},
                    {'frame_prefix': robot.frame + '/'}  # add trailing slash
                ],
            )
        )

        # launch_description.add_action(
        #     launch_ros.actions.Node(
        #         package='joint_state_publisher',
        #         executable='joint_state_publisher',
        #         output='screen',
        #         parameters=[
        #             {'use_sim_time': True},
        #             {'robot_description': description},  # Ensure URDF is passed here too
        #         ],
        #         remappings=[('/joint_states', '/joint_states')]
        #     )
        # )
        await self.node.do_launch(launch_description)

    def _robot_initialpose(self, robot: Robot):
        pose = PoseWithCovarianceStamped()
        pose.pose.pose = robot.pose.to_msg()
        pose.header.frame_id = "map"

        self.node.create_publisher(
            PoseWithCovarianceStamped,
            self.node.service_namespace(robot.name, "initialpose"),
            qos_profile=1,
        ).publish(pose)

    async def _robot_move(self, robot: Robot) -> bool:
        name = robot.name
        try:

            self._robot_initialpose(robot)

            max_attempts = 3
            attempt = 1
            initial_pose_triggered = False

            while attempt <= max_attempts and not initial_pose_triggered:
                self._logger.info(
                    f"Attempt {attempt}/{max_attempts}: Triggering initial pose update for robot {name}"
                )
                try:
                    self._robot_initialpose(robot)
                    initial_pose_triggered = True
                    self._logger.info(
                        f"Initial pose update for {name} succeeded on attempt {attempt}"
                    )
                except Exception as e:
                    self._logger.error(
                        f"Attempt {attempt}/{max_attempts} failed for {name}: {str(e)}"
                    )
                    traceback.print_exc()
                    if attempt < max_attempts:
                        self._logger.info("Waiting 1 second before retrying...")
                        time.sleep(1)
                    attempt += 1

            if not initial_pose_triggered:
                self._logger.error(
                    f"Failed to set initial pose for {name} after {max_attempts} attempts"
                )

            odom_frame = 'odom'

            odom_frame = arena_robots.Robot.RobotIdentifier(robot.model.name).resolve_sync().model_params.odom_frame

            qx, qy, qz, qw = robot.pose.orientation.x, robot.pose.orientation.y, robot.pose.orientation.z, robot.pose.orientation.w
            transform_pub_node = launch_ros.actions.Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="map_to_odomframe_publisher",
                arguments=[
                    str(robot.pose.position.x), str(robot.pose.position.y), str(robot.pose.position.z),
                    str(qx), str(qy), str(qz), str(qw),
                    "map",
                    robot.frame(odom_frame),
                ],
                parameters=[{'use_sim_time': True}],
            )
            await self.node.do_launch(launch.LaunchDescription([transform_pub_node]))
            # time.sleep(1)
            # self.node.get_logger().info("Destroying the static_transform_publisher node after 3 seconds.")
            # transform_pub_node.destroy_node() # won't work like this, a topic/service to trigger self-destruction

            return True

        except Exception as e:
            self._logger.error(f"Error moving robot {name}: {str(e)}")
            return False

    async def _set_up_services(self):
        futures: list[typing.Awaitable] = []
        futures.append(
            self.node.do_launch(
                launch.LaunchDescription([
                    launch_ros.actions.Node(
                        package='ros_gz_bridge',
                        executable='parameter_bridge',
                        name='gz_services_bridge',
                        output='screen',
                        arguments=[
                            '/world/default/create@ros_gz_interfaces/srv/SpawnEntity',
                            '/world/default/remove@ros_gz_interfaces/srv/DeleteEntity',
                            '/world/default/set_pose@ros_gz_interfaces/srv/SetEntityPose',
                            '/world/default/control@ros_gz_interfaces/srv/ControlWorld',
                        ],
                        parameters=[{'use_sim_time': True}],
                    )
                ])
            )
        )

        # Initialize service clients
        # https://gazebosim.org/api/sim/8/entity_creation.html
        self._service_spawn_entity = self.node.create_client_wrapper(
            SpawnEntity,
            '/world/default/create',
        )
        self._service_delete_entity = self.node.create_client_wrapper(
            DeleteEntity,
            '/world/default/remove',
        )
        self._service_set_entity_pose = self.node.create_client_wrapper(
            SetEntityPose,
            '/world/default/set_pose',
        )
        self._service_control_world = self.node.create_client_wrapper(
            ControlWorld,
            '/world/default/control',
        )

        self._logger.info("Waiting for gazebo services...")
        services = (
            (self._service_spawn_entity, "spawn entity"),
            (self._service_delete_entity, "delete entity"),
            (self._service_set_entity_pose, "set entity pose"),
            (self._service_control_world, "control world"),
        )

        for service, name in services:
            self._logger.info(f"Waiting for {name} service...")
            futures.append(service.ensure())

        await asyncio.gather(*futures)
        self._logger.info("All Gazebo services are available now.")

    @classmethod
    async def create(cls, *args, namespace, **kwargs) -> "GazeboSimulator":
        simulator = cls(*args, namespace=namespace, **kwargs)
        await simulator._set_up_services()
        return simulator


def _generate_wall_sdf(
    name: str,
    walls: list[Wall],
    height: float,
    thickness: float,
    base_position: tuple[float, float, float] = (0, 0, 0),


) -> str:
    """
    Generate an SDF string for a wall structure based on given parameters and base position.
    """
    sdf_template = """
        <sdf version="1.6">
            <model name="{name}">
                <pose>{base_x} {base_y} {base_z} 0 0 0</pose>
                {links}
                <static>true</static>
            </model>
        </sdf>
        """
    link_template = """
        <link name="wall_segment_{index}">
            <visual name="visual">
                <geometry>
                    <box>
                        <size>{length} {thickness} {height}</size>
                    </box>
                </geometry>
                <material>
                    <ambient>0.7 0.7 0.7 1</ambient>
                </material>
            </visual>
            <collision name="collision">
                <geometry>
                    <box>
                        <size>{length} {thickness} {height}</size>
                    </box>
                </geometry>
            </collision>
            <pose>{x} {y} {z} 0 0 {orientation}</pose>
        </link>
        """
    links = []
    base_x, base_y, base_z = base_position
    z = height / 2.0  # Center the wall height relative to the base

    for i, w in enumerate(walls):
        x1, y1, x2, y2 = w.start.x, w.start.y, w.end.x, w.end.y
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        orientation = math.atan2(y2 - y1, x2 - x1)
        x = (x1 + x2) / 2 + base_x
        y = (y1 + y2) / 2 + base_y

        links.append(
            link_template.format(
                index=i,
                length=length,
                thickness=thickness,
                height=height,
                x=x,
                y=y,
                z=z + base_z,
                orientation=orientation
            )
        )

    return sdf_template.format(
        name=name,
        base_x=base_x,
        base_y=base_y,
        base_z=base_z,
        links="\n".join(links)
    )
