from task_generator.shared import DynamicObstacle, Obstacle, CustomDynamicObstacle
from task_generator.tasks import TaskMode

Obstacles = tuple[list[Obstacle], list[DynamicObstacle]]
CustomObstacles = tuple[list[Obstacle], list[CustomDynamicObstacle]]


class TM_Obstacles(TaskMode):

    async def reset(self, **kwargs) -> Obstacles:
        return [], []
