import enum
import uuid
from arena_rclpy_mixins.ROSParamServer import ROSParamT

from task_generator.shared import CustomDynamicObstacle, DynamicObstacle, Obstacle, Pose
from task_generator.tasks.mode import TaskMode
from task_generator.tasks.obstacles._placement import random_placement

from . import environment, parametrized, prompt, random, scenario

Obstacles = tuple[list[Obstacle], list[DynamicObstacle]]
CustomObstacles = tuple[list[Obstacle], list[CustomDynamicObstacle]]


@enum.unique
class ObstacleKind(enum.Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"


class TM_Obstacles(TaskMode):
    _floor_id: ROSParamT[str]
    _floor_id_mode: ROSParamT[str]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._floor_id = self.node.ROSParam[str](self.namespace('floor_id'), "")
        self._floor_id_mode = self.node.ROSParam[str](self.namespace('floor_id_mode'), "default")

    def _resolve_floor_id(self, floor_id: str | None = None) -> str:
        if floor_id:
            return floor_id
        mode = (self._floor_id_mode.value or "default").lower()
        if mode == "random":
            floor_ids = list(self._ctx.world_manager.world.floor_ids)
            if not floor_ids:
                return ""
            return str(self.node.conf.General.RNG.value.choice(floor_ids))
        if mode == "explicit":
            return self._floor_id.value or ""
        return self._floor_id.value or ""

    async def reset(self, **kwargs: object) -> Obstacles:
        return [], []

    async def extend(self, kind: ObstacleKind, model: str, pose: Pose | None = None, floor_id: str = "") -> str:
        floor_id = self._resolve_floor_id(floor_id)
        resolved_pose = pose if pose is not None else await random_placement(self._ctx, floor_id=floor_id)
        name = f"ext_{model}_{uuid.uuid4().hex[:6]}"

        if kind is ObstacleKind.STATIC:
            obstacle: Obstacle | DynamicObstacle = Obstacle(name=name, model=model, pose=resolved_pose, floor_id=floor_id)
            await self._ctx.environment_manager.spawn_obstacles([obstacle])
        else:
            waypoints = self._ctx.world_manager.get_positions_on_map(n=2, safe_dist=1, level_id=floor_id)
            obstacle = DynamicObstacle(name=name, model=model, waypoints=waypoints, pose=resolved_pose)
            await self._ctx.environment_manager.spawn_dynamic_obstacles([obstacle])
        return obstacle.sim_path


__all__ = ["TM_Obstacles", "ObstacleKind", "Obstacles", "CustomObstacles", "environment", "parametrized", "prompt", "random", "scenario"]
