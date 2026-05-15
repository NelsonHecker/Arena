from task_generator.tasks.robots.adapters import ADAPTERS, Adapter


@ADAPTERS["arm"].register("moveit")
def _load_moveit() -> type[Adapter]:
    from .moveit import MoveItArmAdapter

    return MoveItArmAdapter


@ADAPTERS["arm"].register("none")
def _load_none() -> type[Adapter]:
    from .none import NoneArmAdapter

    return NoneArmAdapter
