from arena_rclpy_mixins.ROSParamServer import ROSParamT
from arena_simulation_setup.tree.World import WorldIdentifier
from arena_simulation_setup.tree.World.Scenario import RobotGoal, ScenarioGesturePhase, ScenarioGotoPhase

from task_generator.shared import PositionRadius
from task_generator.tasks.robots import TM_Robots
from task_generator.tasks.robots.request import GoToPhase, PlayGesturePhase, TaskRequest


class TM_Scenario(TM_Robots):
    """Scenario task mode for robots."""

    _config: ROSParamT[list[RobotGoal]]

    def _parse_scenario(self, scenario: str) -> list[RobotGoal]:
        return WorldIdentifier(self._ctx.world_manager.loaded_world).resolve_sync().scenario(scenario).resolve_sync().load().robots

    async def reset(self, **kwargs: object) -> None:
        await super().reset(**kwargs)

        SCENARIO_ROBOTS = self._config.value

        managed_robots = list(self._ctx.robots.values())

        scenario_robots_length = len(SCENARIO_ROBOTS)
        setup_robot_length = len(managed_robots)

        if setup_robot_length > scenario_robots_length:
            managed_robots = managed_robots[:scenario_robots_length]
            self._logger.warn("Robot setup contains more robots than the scenario file.", once=True)

        if scenario_robots_length > setup_robot_length:
            SCENARIO_ROBOTS = SCENARIO_ROBOTS[:setup_robot_length]
            self._logger.warn("Scenario file contains more robots than setup.", once=True)

        for robot, config in zip(managed_robots, SCENARIO_ROBOTS, strict=False):
            self._start_poses[robot.name] = config.start

            phases: list[GoToPhase | PlayGesturePhase] = []
            forbidden: list[PositionRadius] = [
                PositionRadius(x=config.start.position.x, y=config.start.position.y, radius=robot.safe_distance),
            ]
            for phase in config.phase_list():
                if isinstance(phase, ScenarioGotoPhase):
                    phases.append(GoToPhase(pose=phase.goto))
                    forbidden.append(PositionRadius(x=phase.goto.position.x, y=phase.goto.position.y, radius=robot.safe_distance))
                elif isinstance(phase, ScenarioGesturePhase):
                    phases.append(PlayGesturePhase(gesture=None if phase.gesture in ("", "random") else phase.gesture))

            await robot.submit_task(TaskRequest(phases=phases))
            self._ctx.world_manager.forbid(forbidden)

    def __init__(self, **kwargs: object) -> None:
        TM_Robots.__init__(self, **kwargs)

        self._config = self.node.ROSParam[list[RobotGoal]](
            self.namespace('file'),
            'default.json',
            parse=self._parse_scenario,
        )
