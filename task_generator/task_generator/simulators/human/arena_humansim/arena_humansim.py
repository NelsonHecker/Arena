"""Task generator adapter for arena_humansim."""

import asyncio
import math
import traceback
from collections.abc import Sequence

import numpy as np
import yaml
from arena_humansim_msgs.msg import (
    AgentState as AgentStateMsg,
)
from arena_humansim_msgs.msg import (
    AgentStates as AgentStatesMsg,
)
from arena_humansim_msgs.msg import (
    AgentTemplate as AgentTemplateMsg,
)
from arena_humansim_msgs.msg import (
    FlowConfig as FlowConfigMsg,
)
from arena_humansim_msgs.msg import (
    ObstacleConfig as ObstacleConfigMsg,
)
from arena_humansim_msgs.msg import (
    RateKeyframe as RateKeyframeMsg,
)
from arena_humansim_msgs.msg import (
    Shape as ShapeMsg,
)
from arena_humansim_msgs.msg import (
    SinkAffinity as SinkAffinityMsg,
)
from arena_humansim_msgs.msg import (
    SinkConfig as SinkConfigMsg,
)
from arena_humansim_msgs.msg import (
    SourceConfig as SourceConfigMsg,
)
from arena_humansim_msgs.msg import (
    Waypoint as WaypointMsg,
)
from arena_humansim_msgs.msg import (
    Waypoints as WaypointsMsg,
)
from arena_humansim_msgs.srv import (
    AddObstacles,
    AddSink,
    AddSource,
    AddWalls,
    RemoveAgents,
    RemoveObstacles,
    RemoveSink,
    RemoveSource,
    RemoveWalls,
    SetFlow,
    SpawnAgents,
)
from arena_people_msgs.msg import Pedestrian, Pedestrians
from arena_rclpy_mixins.Async import ClientWrapper
from arena_rclpy_mixins.shared import Namespace
from geometry_msgs.msg import (
    Point,
    Point32,
    Pose,
    Quaternion,
    Twist,
    Vector3,
)
from geometry_msgs.msg import (
    Pose2D as Pose2DMsg,
)
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from visualization_msgs.msg import MarkerArray

from task_generator.constants import Constants
from task_generator.shared import DynamicObstacle, Obstacle, Robot
from task_generator.simulators.human import BaseHumanSimulator
from task_generator.simulators.human.arena_humansim import ArenaHumanDynamicObstacle
from task_generator.simulators.sim import BaseSim


class ArenaHumanSimulator(BaseHumanSimulator):
    @classmethod
    def _register_task_modes(cls):
        from task_generator.tasks.task import _TaskRegistry

        @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.PROMPT)
        def _prompt():
            from task_generator.tasks.obstacles.prompt.arena import TM_Prompt

            return TM_Prompt

    SERVICE_SPAWN_AGENTS = "spawn_agents"
    SERVICE_REMOVE_AGENTS = "remove_agents"
    SERVICE_SET_FLOW = "set_flow"
    SERVICE_ADD_SOURCE = "add_source"
    SERVICE_REMOVE_SOURCE = "remove_source"
    SERVICE_ADD_SINK = "add_sink"
    SERVICE_REMOVE_SINK = "remove_sink"
    SERVICE_ADD_WALLS = "add_walls"
    SERVICE_REMOVE_WALLS = "remove_walls"
    SERVICE_ADD_OBSTACLES = "add_obstacles"
    SERVICE_REMOVE_OBSTACLES = "remove_obstacles"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._spawn_client: ClientWrapper = self.node.create_client_wrapper(
            SpawnAgents,
            self.node.service_namespace(self.SERVICE_SPAWN_AGENTS),
        )
        self._remove_client: ClientWrapper = self.node.create_client_wrapper(
            RemoveAgents,
            self.node.service_namespace(self.SERVICE_REMOVE_AGENTS),
        )
        self._set_flow_client: ClientWrapper = self.node.create_client_wrapper(
            SetFlow,
            self.node.service_namespace(self.SERVICE_SET_FLOW),
        )
        self._add_source_client: ClientWrapper = self.node.create_client_wrapper(
            AddSource,
            self.node.service_namespace(self.SERVICE_ADD_SOURCE),
        )
        self._remove_source_client: ClientWrapper = self.node.create_client_wrapper(
            RemoveSource,
            self.node.service_namespace(self.SERVICE_REMOVE_SOURCE),
        )
        self._add_sink_client: ClientWrapper = self.node.create_client_wrapper(
            AddSink,
            self.node.service_namespace(self.SERVICE_ADD_SINK),
        )
        self._remove_sink_client: ClientWrapper = self.node.create_client_wrapper(
            RemoveSink,
            self.node.service_namespace(self.SERVICE_REMOVE_SINK),
        )
        self._add_walls_client: ClientWrapper = self.node.create_client_wrapper(
            AddWalls,
            self.node.service_namespace(self.SERVICE_ADD_WALLS),
        )
        self._remove_walls_client: ClientWrapper = self.node.create_client_wrapper(
            RemoveWalls,
            self.node.service_namespace(self.SERVICE_REMOVE_WALLS),
        )
        self._add_obstacles_client: ClientWrapper = self.node.create_client_wrapper(
            AddObstacles,
            self.node.service_namespace(self.SERVICE_ADD_OBSTACLES),
        )
        self._remove_obstacles_client: ClientWrapper = self.node.create_client_wrapper(
            RemoveObstacles,
            self.node.service_namespace(self.SERVICE_REMOVE_OBSTACLES),
        )

        self._next_id: int = 1
        self._rng: np.random.Generator = np.random.default_rng(42)

        self._agents_lock: asyncio.Lock = asyncio.Lock()
        self._prev_agent_states: AgentStatesMsg | None = None
        self._curr_agent_states: AgentStatesMsg | None = None
        self._arena_pedestrians: Pedestrians = Pedestrians()
        self._arena_pedestrians.header.frame_id = "map"
        self._dirty_robots: dict[str, Robot] = {}

        # Publish robot poses on world_state topic (consumed by arena_humansim)
        self._world_state_pub = self.node.create_publisher(
            AgentStatesMsg,
            self.node.service_namespace("world_state"),
            10,
        )

        # Subscribe to agent_states topic from arena_humansim
        self.node.create_subscription(
            AgentStatesMsg,
            self.node.service_namespace("agent_states"),
            self._agent_states_callback,
            10,
        )

        # Forward arena_humansim debug visualization markers
        self.node.create_subscription(
            MarkerArray,
            self.node.service_namespace("viz"),
            self._forward_debug_markers,
            QoSProfile(
                reliability=QoSReliabilityPolicy.BEST_EFFORT,
                durability=QoSDurabilityPolicy.VOLATILE,
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=5,
            ),
        )

    def _forward_debug_markers(self, msg: MarkerArray):
        self.publish_markers(msg)

    def _agent_states_callback(self, msg: AgentStatesMsg):
        """Cache prev/curr snapshots from arena_humansim for local interpolation."""
        self._prev_agent_states = self._curr_agent_states
        self._curr_agent_states = msg

    def _interpolate_agent_states(self, now_ns: int) -> AgentStatesMsg | None:
        """Lerp between prev and curr agent states at the given timestamp."""
        curr = self._curr_agent_states
        if curr is None:
            return None
        prev = self._prev_agent_states
        if prev is None:
            return curr

        prev_ns = prev.header.stamp.sec * int(1e9) + prev.header.stamp.nanosec
        curr_ns = curr.header.stamp.sec * int(1e9) + curr.header.stamp.nanosec
        dt_ns = curr_ns - prev_ns
        if dt_ns <= 0:
            return curr

        alpha = max(0.0, min(1.0, (now_ns - prev_ns) / dt_ns))
        inv = 1.0 - alpha
        prev_by_id = {a.agent_id: a for a in prev.agents}

        msg = AgentStatesMsg()
        msg.header.stamp.sec = int(now_ns // int(1e9))
        msg.header.stamp.nanosec = int(now_ns % int(1e9))
        msg.header.frame_id = "map"

        for curr_a in curr.agents:
            prev_a = prev_by_id.get(curr_a.agent_id)
            if prev_a is None:
                msg.agents.append(curr_a)
                continue
            a = AgentStateMsg()
            a.agent_id = curr_a.agent_id
            d_theta = math.atan2(
                math.sin(curr_a.pose.theta - prev_a.pose.theta),
                math.cos(curr_a.pose.theta - prev_a.pose.theta),
            )
            a.pose = Pose2DMsg(
                x=inv * prev_a.pose.x + alpha * curr_a.pose.x,
                y=inv * prev_a.pose.y + alpha * curr_a.pose.y,
                theta=prev_a.pose.theta + alpha * d_theta,
            )
            a.velocity = Vector3(
                x=inv * prev_a.velocity.x + alpha * curr_a.velocity.x,
                y=inv * prev_a.velocity.y + alpha * curr_a.velocity.y,
                z=0.0,
            )
            a.desired_velocity = curr_a.desired_velocity
            a.radius = curr_a.radius
            msg.agents.append(a)
        return msg

    async def setup(self):
        self._tick_loop_task: asyncio.Task | None = None
        self._update_loop_task: asyncio.Task | None = None
        self._feedback_loop_task: asyncio.Task | None = None

        await asyncio.gather(
            *(
                client.ensure()
                for client in (
                    self._spawn_client,
                    self._remove_client,
                    self._set_flow_client,
                    self._add_source_client,
                    self._remove_source_client,
                    self._add_sink_client,
                    self._remove_sink_client,
                    self._add_walls_client,
                    self._remove_walls_client,
                    self._add_obstacles_client,
                    self._remove_obstacles_client,
                )
            )
        )
        self._logger.info("All arena_humansim services available")

        await self.unpause()

    @classmethod
    async def create(cls, *args, namespace: Namespace, simulator: BaseSim, **kwargs):
        self = cls(*args, namespace=namespace, simulator=simulator, **kwargs)
        await self.setup()
        return self

    async def pause(self):
        for attr in ("_tick_loop_task", "_update_loop_task", "_feedback_loop_task"):
            task = getattr(self, attr, None)
            if task is not None:
                task.cancel()
                setattr(self, attr, None)

    async def unpause(self):
        await self.pause()
        self._tick_loop_task = asyncio.create_task(self._interpolation_loop())
        self._update_loop_task = asyncio.create_task(self._pedestrian_update_loop())
        self._feedback_loop_task = asyncio.create_task(self._feedback_loop())

    @property
    def agent_states(self):
        return self._curr_agent_states

    TICK_RATE = 50.0  # Hz — local interpolation rate
    FEEDBACK_RATE = 10.0  # Hz — rate for sending feedback to arena_humansim

    async def _interpolation_loop(self):
        """Interpolate agent states locally at TICK_RATE and publish pedestrians."""
        try:
            with self.node.sim_time_rate(self.TICK_RATE) as (done, rate):
                while not done.is_set():
                    await rate.get()
                    now = self.node.sim_time
                    render_ns = now.sec * int(1e9) + now.nanosec
                    states = self._interpolate_agent_states(render_ns)
                    if states is None:
                        continue
                    peds = self._agent_states_to_pedestrians(states)
                    async with self._agents_lock:
                        self._arena_pedestrians = peds
                    self.publish_arena_peds(peds)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(
                f"Error in interpolation loop: {e}\n{traceback.format_exc()}"
            )

    async def _pedestrian_update_loop(self):
        """Push latest pedestrian positions to the underlying simulator (e.g. flatland)."""
        try:
            with self.node.sim_time_rate(self.TICK_RATE) as (done, rate):
                while not done.is_set():
                    await rate.get()
                    async with self._agents_lock:
                        peds = self._arena_pedestrians
                    if peds.pedestrians:
                        await self._simulator.pedestrian_update(peds)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(
                f"Error in pedestrian update loop: {e}\n{traceback.format_exc()}"
            )

    async def _feedback_loop(self):
        """Publish dirty robot poses on world_state topic."""
        try:
            with self.node.sim_time_rate(self.FEEDBACK_RATE) as (done, rate):
                while not done.is_set():
                    await rate.get()
                    if not self._dirty_robots:
                        continue
                    self._publish_world_state()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(f"Error in feedback loop: {e}\n{traceback.format_exc()}")

    def _publish_world_state(self):
        """Publish robot poses as AgentStates on world_state topic."""
        msg = AgentStatesMsg()
        msg.header.stamp = self.node.sim_time.to_msg()
        msg.header.frame_id = "map"
        for robot in self._dirty_robots.values():
            a = AgentStateMsg()
            a.agent_id = hash(robot.name) & 0x7FFFFFFF
            yaw = robot.pose.orientation.to_yaw()
            a.pose = Pose2DMsg(
                x=robot.pose.position.x,
                y=robot.pose.position.y,
                theta=yaw,
            )
            a.radius = 0.3
            msg.agents.append(a)
        self._dirty_robots.clear()
        self._world_state_pub.publish(msg)

    @classmethod
    def _agent_states_to_pedestrians(cls, msg: AgentStatesMsg) -> Pedestrians:
        peds = Pedestrians()
        peds.header = msg.header
        for agent in msg.agents:
            ped = Pedestrian()
            ped.id = agent.agent_id
            ped.name = str(agent.agent_id)

            yaw = agent.pose.theta
            ped.pose = Pose(
                position=Point(x=agent.pose.x, y=agent.pose.y, z=0.0),
                orientation=Quaternion(
                    z=math.sin(yaw / 2.0),
                    w=math.cos(yaw / 2.0),
                ),
            )
            ped.twist = Twist(linear=agent.velocity)

            speed = math.hypot(agent.velocity.x, agent.velocity.y)
            if speed > 1.5:
                ped.animation_state = Pedestrian.RUNNING
            elif speed > 0.05:
                ped.animation_state = Pedestrian.WALKING
            else:
                ped.animation_state = Pedestrian.IDLE

            peds.pedestrians.append(ped)
        return peds

    def _polygon_to_shape_msg(
        self, polygon, centroid: tuple[float, float] | None = None
    ) -> ShapeMsg:
        """Convert a polygon (list of Position) to a Shape msg with POLYGON type.

        Vertices are stored relative to *centroid* (the pose sent alongside
        the shape), because the arena_humansim manager and visualisation
        interpret shape vertices as local offsets from the pose.
        """
        cx, cy = centroid if centroid is not None else self._polygon_centroid(polygon)
        shape = ShapeMsg()
        shape.type = ShapeMsg.POLYGON  # = 2
        shape.vertices = [
            Point32(x=float(p.x - cx), y=float(p.y - cy), z=0.0) for p in polygon
        ]
        return shape

    def _polygon_centroid(self, polygon) -> tuple[float, float]:
        """Compute centroid of a polygon."""
        if not polygon:
            return 0.0, 0.0
        cx = sum(p.x for p in polygon) / len(polygon)
        cy = sum(p.y for p in polygon) / len(polygon)
        return cx, cy

    async def _add_regions_impl(self, regions) -> bool:
        results = await asyncio.gather(
            *(self._add_region_single(r) for r in regions),
        )
        return all(results) if results else True

    async def _add_region_single(self, region) -> bool:
        if region.type == "source":
            return await self._add_source_region(region)
        elif region.type == "sink":
            return await self._add_sink_region(region)
        else:
            self._logger.error(f"Unknown region type: {region.type}")
            return False

    async def _add_source_region(self, region) -> bool:
        request = AddSource.Request()
        src_msg = SourceConfigMsg()
        src_msg.name = region.name
        centroid = self._polygon_centroid(region.polygon)
        src_msg.pose = Pose2DMsg(x=centroid[0], y=centroid[1], theta=0.0)
        src_msg.shape = self._polygon_to_shape_msg(region.polygon, centroid)

        cfg = region.config
        for kf in cfg.get("rate_profile", []):
            src_msg.rate_profile.append(
                RateKeyframeMsg(t=kf.get("t", 0.0), rate=kf.get("rate", 0.0))
            )
        src_msg.max_concurrent = cfg.get("max_concurrent", -1)
        src_msg.max_total = cfg.get("max_total", -1)

        raw_tmpl = cfg.get("agent", {})
        tmpl = AgentTemplateMsg()
        vel = raw_tmpl.get("desired_velocity", {})
        tmpl.desired_velocity_min = (
            vel.get("min", 1.0) if isinstance(vel, dict) else float(vel)
        )
        tmpl.desired_velocity_max = (
            vel.get("max", 1.5) if isinstance(vel, dict) else float(vel)
        )
        tmpl.agent_radius = raw_tmpl.get("agent_radius", 0.35)
        tmpl.behavior_tree = raw_tmpl.get("behavior_tree", "default")
        tmpl.agent_type = raw_tmpl.get("agent_type", "adult")
        for sa in raw_tmpl.get("sink_affinity", []):
            tmpl.sink_affinity.append(
                SinkAffinityMsg(
                    sink_name=sa.get("sink", ""), weight=sa.get("weight", 1.0)
                )
            )
        src_msg.agent = tmpl

        request.source = src_msg
        try:
            response = await self._add_source_client.call_timeout(request)
            if response.success:
                return True
            self._logger.error(f"AddSource failed: {response.message}")
            return False
        except Exception as e:
            self._logger.error(f"AddSource call failed: {e}")
            return False

    async def _add_sink_region(self, region) -> bool:
        request = AddSink.Request()
        sink_msg = SinkConfigMsg()
        sink_msg.name = region.name
        centroid = self._polygon_centroid(region.polygon)
        sink_msg.pose = Pose2DMsg(x=centroid[0], y=centroid[1], theta=0.0)
        sink_msg.shape = self._polygon_to_shape_msg(region.polygon, centroid)

        cfg = region.config
        sink_msg.absorption_radius = cfg.get("absorption_radius", 0.5)
        sink_msg.capacity = cfg.get("capacity", -1)

        request.sink = sink_msg
        try:
            response = await self._add_sink_client.call_timeout(request)
            if response.success:
                return True
            self._logger.error(f"AddSink failed: {response.message}")
            return False
        except Exception as e:
            self._logger.error(f"AddSink call failed: {e}")
            return False

    async def _remove_regions_impl(self, regions) -> bool:
        sources = [r.name for r in regions if r.type == "source"]
        sinks = [r.name for r in regions if r.type == "sink"]
        results = await asyncio.gather(
            *(self._remove_source_by_name(name) for name in sources),
            *(self._remove_sink_by_name(name) for name in sinks),
        )
        return all(results) if results else True

    async def _remove_source_by_name(self, name: str) -> bool:
        request = RemoveSource.Request()
        request.name = name
        try:
            response = await self._remove_source_client.call_timeout(request)
            if response.success:
                return True
            self._logger.error(f"RemoveSource failed: {response.message}")
            return False
        except Exception as e:
            self._logger.error(f"RemoveSource call failed: {e}")
            return False

    async def _remove_sink_by_name(self, name: str) -> bool:
        request = RemoveSink.Request()
        request.name = name
        try:
            response = await self._remove_sink_client.call_timeout(request)
            if response.success:
                return True
            self._logger.error(f"RemoveSink failed: {response.message}")
            return False
        except Exception as e:
            self._logger.error(f"RemoveSink call failed: {e}")
            return False

    async def _spawn_obstacles_impl(self, obstacles) -> Sequence[Obstacle | None]:
        """Send obstacle configs (pose + bounding box + metadata) to arena_humansim."""
        if not obstacles:
            return obstacles

        # Resolve all asset paths concurrently so the NetResolver can batch them
        resolved_paths = await asyncio.gather(
            *(obstacle.model.resolve_path() for obstacle in obstacles),
            return_exceptions=True,
        )

        request = AddObstacles.Request()
        for obstacle, resolved in zip(obstacles, resolved_paths):
            try:
                if isinstance(resolved, BaseException):
                    raise resolved
                annotation_path = resolved / "annotation.yaml"
                with open(annotation_path, "r") as f:
                    annotation: dict = yaml.safe_load(f.read())

                (x_min, x_max), (y_min, y_max), (z_min, z_max) = annotation[
                    "bounding_box"
                ]

                msg = ObstacleConfigMsg()
                msg.name = obstacle.name
                msg.pose = Pose2DMsg(
                    x=obstacle.pose.position.x,
                    y=obstacle.pose.position.y,
                    theta=obstacle.pose.orientation.to_yaw(),
                )
                msg.bb_x_min = float(x_min)
                msg.bb_x_max = float(x_max)
                msg.bb_y_min = float(y_min)
                msg.bb_y_max = float(y_max)
                msg.bb_z_min = float(z_min)
                msg.bb_z_max = float(z_max)
                msg.interaction_types = [str(h) for h in annotation.get("hoi", [])]
                msg.obstacle_type = annotation.get("name", "") or annotation.get(
                    "desc", ""
                )
                request.obstacles.append(msg)
            except Exception as e:
                self._logger.warning(
                    f"Failed to build obstacle config for '{obstacle.name}': {e}"
                )

        if request.obstacles:
            try:
                response = await self._add_obstacles_client.call_timeout(request)
                if response.success:
                    self._logger.info(response.message)
                else:
                    self._logger.error(f"AddObstacles failed: {response.message}")
            except Exception as e:
                self._logger.error(f"AddObstacles call failed: {e}")

        return obstacles

    async def _spawn_dynamic_obstacles_impl(
        self, obstacles
    ) -> Sequence[DynamicObstacle | None]:
        """Forward dynamic obstacles to arena_humansim AgentManager via SpawnAgents."""
        if not obstacles:
            return obstacles

        request = SpawnAgents.Request()
        for obstacle in obstacles:
            agent_msg = AgentStateMsg()
            agent_msg.agent_id = self._next_id
            self._next_id += 1

            agent_msg.pose = Pose2DMsg(
                x=obstacle.pose.position.x,
                y=obstacle.pose.position.y,
                theta=obstacle.pose.orientation.to_yaw(),
            )
            agent_msg.velocity = Vector3(x=0.0, y=0.0, z=0.0)

            parsed = ArenaHumanDynamicObstacle.from_dynamic_obstacle(obstacle)
            params = parsed.sample_params(self._rng) if parsed is not None else None

            if params is not None:
                agent_msg.desired_velocity = params.desired_velocity
                agent_msg.radius = params.agent_radius
                agent_msg.vision_range = params.perception.vision_range
                agent_msg.vision_fov = params.perception.vision_fov
                agent_msg.relaxation_time = params.local_planner_params.relaxation_time
                agent_msg.repulsion_strength = (
                    params.local_planner_params.repulsion_strength
                )
                agent_msg.repulsion_range = params.local_planner_params.repulsion_range
                agent_msg.agent_type = params.name
            else:
                agent_msg.desired_velocity = float(obstacle.velocity)
                agent_msg.radius = 0.35
                agent_msg.vision_range = 0.0
                agent_msg.vision_fov = 0.0
                agent_msg.relaxation_time = 0.0
                agent_msg.repulsion_strength = 0.0
                agent_msg.repulsion_range = 0.0
                agent_msg.agent_type = ""

            if parsed is not None:
                agent_msg.waypoints = parsed.waypoints_msg
            else:
                wp_msg = WaypointsMsg()
                wp_msg.mode = WaypointsMsg.MODE_REPEAT
                for wp in obstacle.waypoints:
                    wp_msg.points.append(
                        WaypointMsg(pose=Pose2DMsg(x=wp.x, y=wp.y, theta=0.0))
                    )
                agent_msg.waypoints = wp_msg
            request.agents.append(agent_msg)

        try:
            response = await self._spawn_client.call_timeout(request)
            if response.success:
                self._logger.info(f"Spawned {len(response.spawned_ids)} agents")
                return obstacles
            else:
                self._logger.error(f"SpawnAgents failed: {response.message}")
                return [None] * len(obstacles)
        except Exception as e:
            self._logger.error(f"SpawnAgents call failed: {e}")
            return [None] * len(obstacles)

    async def _remove_obstacles_impl(self, names) -> bool:
        """Remove static obstacles from arena_humansim."""
        if not names:
            return True
        try:
            request = RemoveObstacles.Request()
            request.names = list(names)
            response = await self._remove_obstacles_client.call_timeout(request)
            if response.success:
                return True
            self._logger.error(f"RemoveObstacles failed: {response.message}")
            return False
        except Exception as e:
            self._logger.warning(f"RemoveObstacles call failed: {e}")
            return False

    async def _remove_pedestrians_impl(self) -> bool:
        """Remove all dynamic agents from arena_humansim."""
        request = RemoveAgents.Request()
        request.agent_ids = [-1]  # -1 = remove all

        try:
            response = await self._remove_client.call_timeout(request)
            self._next_id = 1
            if response.success:
                self._logger.info(response.message)
                return True
            else:
                self._logger.error(f"RemoveAgents failed: {response.message}")
                return False
        except Exception as e:
            self._logger.error(f"RemoveAgents call failed: {e}")
            return False

    async def _spawn_walls_impl(self, walls) -> bool:
        return await self._add_walls(walls)

    async def _spawn_doors_impl(self, doors) -> bool:
        return await self._add_walls(doors)

    async def _remove_walls_impl(self, names) -> bool:
        return await self._remove_walls(names)

    async def _remove_doors_impl(self, names) -> bool:
        return await self._remove_walls(names)

    async def _add_walls(self, walls) -> bool:
        """Send wall/door segments to arena_humansim via AddWalls."""
        if not walls:
            return True

        request = AddWalls.Request()
        for name, wall in walls.items():
            request.names.append(name)
            request.starts.append(
                Point32(x=float(wall.start.x), y=float(wall.start.y), z=0.0)
            )
            request.ends.append(
                Point32(x=float(wall.end.x), y=float(wall.end.y), z=0.0)
            )

        try:
            response = await self._add_walls_client.call_timeout(request)
            if response.success:
                return True
            self._logger.error(f"AddWalls failed: {response.message}")
            return False
        except Exception as e:
            self._logger.error(f"AddWalls call failed: {e}")
            return False

    async def _remove_walls(self, names) -> bool:
        """Remove wall/door segments from arena_humansim via RemoveWalls."""
        if not names:
            return True

        request = RemoveWalls.Request()
        request.names = list(names)

        try:
            response = await self._remove_walls_client.call_timeout(request)
            if response.success:
                return True
            self._logger.error(f"RemoveWalls failed: {response.message}")
            return False
        except Exception as e:
            self._logger.error(f"RemoveWalls call failed: {e}")
            return False

    async def _spawn_robot_impl(self, robots) -> Sequence[bool]:
        """Register robot poses — published to arena_humansim via world_state topic."""
        for robot in robots:
            self._dirty_robots[robot.name] = robot
        self._publish_world_state()
        return (True,) * len(robots)

    async def _remove_robot_impl(self, robots) -> Sequence[bool]:
        for robot in robots:
            self._dirty_robots.pop(robot.name, None)
        return (True,) * len(robots)

    async def _move_robot_impl(self, robots) -> Sequence[bool]:
        """Update tracked robot poses (sent to arena_humansim each tick)."""
        for robot in robots:
            self._dirty_robots[robot.name] = robot
        return (True,) * len(robots)
