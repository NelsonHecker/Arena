from __future__ import annotations

import logging


def _make_context():
    import launch
    return launch.LaunchContext()


class TestNodeLogLevelExtension:
    def test_prepare_for_execute_with_log_level_set(self) -> None:
        import launch
        import launch.substitutions
        from arena_bringup.extensions.NodeLogLevelExtension import NodeLogLevelExtension

        ctx = _make_context()
        ctx.launch_configurations["NodeLogLevelExtension_log_level"] = "debug"

        ext = NodeLogLevelExtension()
        args, ros_specific = ext.prepare_for_execute(ctx, {}, None)

        assert len(args) == 2
        assert any(
            isinstance(a, list) and len(a) == 1 and isinstance(a[0], launch.substitutions.TextSubstitution) and a[0].text == "--log-level"
            for a in args
        )
        assert any(
            isinstance(a, list) and len(a) == 1 and isinstance(a[0], launch.substitutions.TextSubstitution) and a[0].text == "debug"
            for a in args
        )

    def test_prepare_for_execute_without_log_level(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import NodeLogLevelExtension

        ctx = _make_context()
        ext = NodeLogLevelExtension()
        args, ros_specific = ext.prepare_for_execute(ctx, {}, None)
        assert args == []

    def test_prepare_for_execute_returns_ros_specific_unchanged(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import NodeLogLevelExtension

        ctx = _make_context()
        ctx.launch_configurations["NodeLogLevelExtension_log_level"] = "info"
        extra = {"custom_key": "custom_value"}
        ext = NodeLogLevelExtension()
        _, ros_specific = ext.prepare_for_execute(ctx, extra, None)
        assert ros_specific == extra

    def test_prepare_for_execute_log_level_in_text_substitution(self) -> None:
        import launch.substitutions
        from arena_bringup.extensions.NodeLogLevelExtension import NodeLogLevelExtension

        ctx = _make_context()
        ctx.launch_configurations["NodeLogLevelExtension_log_level"] = "warn"
        ext = NodeLogLevelExtension()
        args, _ = ext.prepare_for_execute(ctx, {}, None)
        level_arg = args[1]
        assert level_arg[0].text == "warn"

    def test_prepare_for_execute_args_are_pairs_of_text_substitutions(self) -> None:
        import launch.substitutions
        from arena_bringup.extensions.NodeLogLevelExtension import NodeLogLevelExtension

        ctx = _make_context()
        ctx.launch_configurations["NodeLogLevelExtension_log_level"] = "error"
        ext = NodeLogLevelExtension()
        args, _ = ext.prepare_for_execute(ctx, {}, None)
        for arg in args:
            assert isinstance(arg, list)
            assert all(isinstance(s, launch.substitutions.TextSubstitution) for s in arg)


class TestSetGlobalLogLevelAction:
    def test_str_to_level_debug(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
        assert SetGlobalLogLevelAction.str_to_level("debug") == logging.DEBUG

    def test_str_to_level_info(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
        assert SetGlobalLogLevelAction.str_to_level("info") == logging.INFO

    def test_str_to_level_warn(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
        assert SetGlobalLogLevelAction.str_to_level("warn") == logging.WARN

    def test_str_to_level_error(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
        assert SetGlobalLogLevelAction.str_to_level("error") == logging.ERROR

    def test_str_to_level_fatal(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
        assert SetGlobalLogLevelAction.str_to_level("fatal") == logging.FATAL

    def test_str_to_level_unknown_returns_notset(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
        assert SetGlobalLogLevelAction.str_to_level("unknown_level") == logging.NOTSET

    def test_execute_sets_launch_configuration(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction

        ctx = _make_context()
        action = SetGlobalLogLevelAction("info")
        action.execute(ctx)
        assert ctx.launch_configurations.get("NodeLogLevelExtension_log_level") == "info"

    def test_execute_sets_debug_level(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction

        ctx = _make_context()
        action = SetGlobalLogLevelAction("debug")
        action.execute(ctx)
        assert ctx.launch_configurations["NodeLogLevelExtension_log_level"] == "debug"

    def test_execute_sets_warn_level(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction

        ctx = _make_context()
        action = SetGlobalLogLevelAction("warn")
        action.execute(ctx)
        assert ctx.launch_configurations["NodeLogLevelExtension_log_level"] == "warn"

    def test_execute_sets_error_level(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction

        ctx = _make_context()
        action = SetGlobalLogLevelAction("error")
        action.execute(ctx)
        assert ctx.launch_configurations["NodeLogLevelExtension_log_level"] == "error"

    def test_execute_sets_fatal_level(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction

        ctx = _make_context()
        action = SetGlobalLogLevelAction("fatal")
        action.execute(ctx)
        assert ctx.launch_configurations["NodeLogLevelExtension_log_level"] == "fatal"

    def test_execute_overwrites_existing_level(self) -> None:
        from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction

        ctx = _make_context()
        ctx.launch_configurations["NodeLogLevelExtension_log_level"] = "debug"
        action = SetGlobalLogLevelAction("error")
        action.execute(ctx)
        assert ctx.launch_configurations["NodeLogLevelExtension_log_level"] == "error"
