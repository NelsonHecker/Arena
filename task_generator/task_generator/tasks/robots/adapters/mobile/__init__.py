from task_generator.tasks.robots.adapters import ADAPTERS, Adapter


@ADAPTERS["mobile"].register("nav2")
def _load_nav2() -> type[Adapter]:
    from .nav2 import Nav2Adapter

    return Nav2Adapter


@ADAPTERS["mobile"].register("external")
def _load_external() -> type[Adapter]:
    from .external import ExternalAdapter

    return ExternalAdapter


@ADAPTERS["mobile"].register("none")
def _load_none() -> type[Adapter]:
    from .none import NoneAdapter

    return NoneAdapter


@ADAPTERS["mobile"].register("test-collision")
def _load_test_collision() -> type[Adapter]:
    from .test_collision import TestCollisionAdapter

    return TestCollisionAdapter
