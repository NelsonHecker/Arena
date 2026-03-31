from arena_rclpy_mixins.ROSParamServer import ROSParamT
from arena_simulation_setup.tree.World import WorldIdentifier

from task_generator.shared import Region
from task_generator.tasks import identifier_to_available
from task_generator.tasks.obstacles import Obstacles, TM_Obstacles


class TM_Scenario(TM_Obstacles):
    _config: ROSParamT[str]

    def _get_scenario_view(self, scenario_name: str):
        return (
            WorldIdentifier(self.node._world_manager.world_name)
            .resolve_sync()
            .scenario(scenario_name)
            .resolve_sync()
        )

    async def reset(self, **kwargs) -> Obstacles:
        scenario_name = self._config.value
        world_description = self._PROPS.world_manager.world

        # Build a converter that resolves zone refs to concrete geometry
        zone_conv = world_description.zone_converter(self.node.conf.General.RNG.value)

        # Load and structure the scenario with zone-aware conversion
        scenario = self._get_scenario_view(scenario_name).load(converter=zone_conv)

        # Set up regions
        regions = [
            Region(
                name=name,
                type=r.type,
                polygon=list(r.polygon),
                config=r.config,
            )
            for name, r in scenario.regions.items()
        ]
        await self._PROPS.environment_manager.setup_regions(regions)

        return scenario.static, scenario.dynamic

    def __init__(self, **kwargs):
        TM_Obstacles.__init__(self, **kwargs)

        default_scenario: str | None = "default"
        if default_scenario not in (
            scenarios := list(
                identifier_to_available(
                    WorldIdentifier(self.node._world_manager.world_name)
                    .resolve_sync()
                    .scenario
                )
            )
        ):
            default_scenario = next(iter(scenarios), None)
        if default_scenario is None:
            raise ValueError(
                f"No scenarios found in world {self.node._world_manager.world_name}"
            )

        self._config = self.node.ROSParam[str](
            self.namespace("file"),
            default_scenario,
        )
