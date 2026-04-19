from __future__ import annotations

import os
import tempfile

import pytest
import yaml


def _make_context():
    import launch
    return launch.LaunchContext()


def _write_yaml(path: str, data: object) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f)


class TestLaunchArgument:
    def test_substitution_returns_launch_configuration(self) -> None:
        import launch.substitutions
        from arena_bringup.substitutions import LaunchArgument

        arg = LaunchArgument("my_arg", default_value="default")
        sub = arg.substitution
        assert isinstance(sub, launch.substitutions.LaunchConfiguration)
        ctx = _make_context()
        ctx.launch_configurations["my_arg"] = "value"
        assert sub.perform(ctx) == "value"

    def test_dict_returns_name_to_substitution(self) -> None:
        from arena_bringup.substitutions import LaunchArgument

        arg = LaunchArgument("foo", default_value="bar")
        d = arg.dict
        assert "foo" in d

    def test_auto_append_off_by_default(self) -> None:
        from arena_bringup.substitutions import LaunchArgument

        LaunchArgument._auto_append = None
        target = []
        LaunchArgument("standalone_arg", default_value="v")
        assert target == []

    def test_auto_append_on_appends_to_list(self) -> None:
        from arena_bringup.substitutions import LaunchArgument

        target: list = []
        LaunchArgument.auto_append(target)
        arg = LaunchArgument("appended_arg", default_value="v")
        LaunchArgument.auto_append(None)
        assert arg in target

    def test_auto_append_none_stops_appending(self) -> None:
        from arena_bringup.substitutions import LaunchArgument

        target: list = []
        LaunchArgument.auto_append(target)
        LaunchArgument.auto_append(None)
        LaunchArgument("not_appended", default_value="v")
        assert len(target) == 0

    def test_param_value_wraps_substitution(self) -> None:
        import launch_ros.parameter_descriptions
        from arena_bringup.substitutions import LaunchArgument

        arg = LaunchArgument("typed_arg", default_value="42")
        pv = arg.param_value(int)
        assert isinstance(pv, launch_ros.parameter_descriptions.ParameterValue)

    def test_param_returns_dict_with_name_key(self) -> None:
        from arena_bringup.substitutions import LaunchArgument

        arg = LaunchArgument("param_arg", default_value="1")
        p = arg.param(bool)
        assert "param_arg" in p

    def test_str_param_uses_str_type(self) -> None:
        import launch_ros.parameter_descriptions
        from arena_bringup.substitutions import LaunchArgument

        arg = LaunchArgument("str_arg", default_value="hello")
        sp = arg.str_param
        assert "str_arg" in sp
        assert isinstance(sp["str_arg"], launch_ros.parameter_descriptions.ParameterValue)


class TestSelectAction:
    def test_execute_returns_matching_actions(self) -> None:
        import launch
        import launch.actions
        from arena_bringup.substitutions import SelectAction

        ctx = _make_context()
        ctx.launch_configurations["selector_key"] = "foo"

        action = SelectAction(launch.substitutions.LaunchConfiguration("selector_key"))
        inner = launch.actions.LogInfo(msg="matched")
        action.add("foo", inner)
        action.add("bar", launch.actions.LogInfo(msg="other"))

        result = action.execute(ctx)
        assert inner in result

    def test_execute_returns_empty_for_missing_key(self) -> None:
        import launch
        from arena_bringup.substitutions import SelectAction

        ctx = _make_context()
        ctx.launch_configurations["sel"] = "unknown"
        action = SelectAction(launch.substitutions.LaunchConfiguration("sel"))
        assert action.execute(ctx) == []

    def test_keys_lists_registered_keys(self) -> None:
        import launch
        from arena_bringup.substitutions import SelectAction

        action = SelectAction("foo")
        action.add("a", launch.actions.LogInfo(msg="x"))
        action.add("b", launch.actions.LogInfo(msg="y"))
        assert set(action.keys) == {"a", "b"}

    def test_add_multiple_actions_to_same_key(self) -> None:
        import launch
        import launch.actions
        from arena_bringup.substitutions import SelectAction

        ctx = _make_context()
        ctx.launch_configurations["k"] = "x"
        action = SelectAction(launch.substitutions.LaunchConfiguration("k"))
        a1 = launch.actions.LogInfo(msg="first")
        a2 = launch.actions.LogInfo(msg="second")
        action.add("x", a1)
        action.add("x", a2)
        result = action.execute(ctx)
        assert a1 in result
        assert a2 in result


class TestYAMLFileSubstitution:
    def test_perform_loads_yaml_file(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution

        data = {"key": "value"}
        f = tmp_path / "test.yaml"
        _write_yaml(str(f), data)

        ctx = _make_context()
        sub = YAMLFileSubstitution(str(f))
        result_path = sub.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded == data
        os.unlink(result_path)

    def test_perform_uses_default_on_file_not_found(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution

        ctx = _make_context()
        default = {"fallback": True}
        sub = YAMLFileSubstitution("/nonexistent/path.yaml", default=default)
        result_path = sub.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded == default
        os.unlink(result_path)

    def test_perform_raises_without_default_on_missing_file(self) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution

        ctx = _make_context()
        sub = YAMLFileSubstitution("/nonexistent/path.yaml")
        with pytest.raises(Exception):
            sub.perform(ctx)

    def test_from_dict_classmethod(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution

        ctx = _make_context()
        data = {"a": 1, "b": 2}
        sub = YAMLFileSubstitution.from_dict(data)
        result_path = sub.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded == data
        os.unlink(result_path)

    def test_perform_load_returns_dict(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution

        data = {"x": 42}
        f = tmp_path / "data.yaml"
        _write_yaml(str(f), data)
        ctx = _make_context()
        sub = YAMLFileSubstitution(str(f))
        loaded = sub.perform_load(ctx)
        assert isinstance(loaded, dict)
        assert loaded == data

    def test_perform_load_raises_on_non_dict(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution

        f = tmp_path / "list.yaml"
        _write_yaml(str(f), [1, 2, 3])
        ctx = _make_context()
        sub = YAMLFileSubstitution(str(f))
        with pytest.raises(yaml.YAMLError):
            sub.perform_load(ctx)

    def test_default_yamlfilesubstitution_instance(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution

        default_data = {"default_key": "default_val"}
        default_f = tmp_path / "default.yaml"
        _write_yaml(str(default_f), default_data)

        ctx = _make_context()
        default_sub = YAMLFileSubstitution(str(default_f))
        sub = YAMLFileSubstitution("/nonexistent.yaml", default=default_sub)
        result_path = sub.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded == default_data
        os.unlink(result_path)


class TestYAMLRetrieveSubstitution:
    def test_retrieve_top_level_key(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLRetrieveSubstitution

        data = {"top": "value"}
        f = tmp_path / "r.yaml"
        _write_yaml(str(f), data)
        ctx = _make_context()
        file_sub = YAMLFileSubstitution(str(f))
        retrieve = YAMLRetrieveSubstitution(file_sub, "top")
        assert retrieve.perform(ctx) == "value"

    def test_retrieve_nested_key_with_path_separator(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLRetrieveSubstitution

        data = {"outer": {"inner": "nested_value"}}
        f = tmp_path / "nested.yaml"
        _write_yaml(str(f), data)
        ctx = _make_context()
        file_sub = YAMLFileSubstitution(str(f))
        retrieve = YAMLRetrieveSubstitution(file_sub, f"outer{os.sep}inner")
        assert retrieve.perform(ctx) == "nested_value"

    def test_retrieve_array_index(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLRetrieveSubstitution

        data = {"items": ["a", "b", "c"]}
        f = tmp_path / "arr.yaml"
        _write_yaml(str(f), data)
        ctx = _make_context()
        file_sub = YAMLFileSubstitution(str(f))
        retrieve = YAMLRetrieveSubstitution(file_sub, f"items{os.sep}1")
        assert retrieve.perform(ctx) == "b"

    def test_retrieve_missing_key_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLRetrieveSubstitution

        data = {"exists": True}
        f = tmp_path / "missing.yaml"
        _write_yaml(str(f), data)
        ctx = _make_context()
        file_sub = YAMLFileSubstitution(str(f))
        retrieve = YAMLRetrieveSubstitution(file_sub, "does_not_exist")
        with pytest.raises(Exception):
            retrieve.perform(ctx)


class TestYAMLMergeSubstitution:
    def test_merge_two_yamls_later_wins(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLMergeSubstitution

        base = {"a": 1, "b": 2}
        overlay = {"b": 99, "c": 3}
        f1 = tmp_path / "base.yaml"
        f2 = tmp_path / "overlay.yaml"
        _write_yaml(str(f1), base)
        _write_yaml(str(f2), overlay)

        ctx = _make_context()
        base_sub = YAMLFileSubstitution(str(f1))
        overlay_sub = YAMLFileSubstitution(str(f2))
        merge = YAMLMergeSubstitution(base_sub, overlay_sub)
        result_path = merge.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded["a"] == 1
        assert loaded["b"] == 99
        assert loaded["c"] == 3
        os.unlink(result_path)

    def test_merge_recursive_dict(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLMergeSubstitution

        base = {"outer": {"x": 1, "y": 2}}
        overlay = {"outer": {"y": 99, "z": 3}}
        f1 = tmp_path / "rec_base.yaml"
        f2 = tmp_path / "rec_overlay.yaml"
        _write_yaml(str(f1), base)
        _write_yaml(str(f2), overlay)

        ctx = _make_context()
        merge = YAMLMergeSubstitution(
            YAMLFileSubstitution(str(f1)),
            YAMLFileSubstitution(str(f2)),
        )
        result_path = merge.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded["outer"]["x"] == 1
        assert loaded["outer"]["y"] == 99
        assert loaded["outer"]["z"] == 3
        os.unlink(result_path)

    def test_recursive_merge_standalone(self) -> None:
        from arena_bringup.substitutions import YAMLMergeSubstitution

        result = YAMLMergeSubstitution._recursive_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_recursive_merge_override_scalar(self) -> None:
        from arena_bringup.substitutions import YAMLMergeSubstitution

        result = YAMLMergeSubstitution._recursive_merge({"a": 1}, {"a": 2})
        assert result["a"] == 2

    def test_recursive_merge_nested_dict(self) -> None:
        from arena_bringup.substitutions import YAMLMergeSubstitution

        result = YAMLMergeSubstitution._recursive_merge(
            {"nested": {"x": 1}},
            {"nested": {"y": 2}},
        )
        assert result["nested"]["x"] == 1
        assert result["nested"]["y"] == 2


class TestYAMLReplaceSubstitution:
    def test_simple_key_substitution(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLReplaceSubstitution

        subs_data = {"NAME": "world"}
        obj_data = {"greeting": "${NAME}"}
        subs_f = tmp_path / "subs.yaml"
        obj_f = tmp_path / "obj.yaml"
        _write_yaml(str(subs_f), subs_data)
        _write_yaml(str(obj_f), obj_data)

        ctx = _make_context()
        replace = YAMLReplaceSubstitution(
            substitutions=YAMLFileSubstitution(str(subs_f)),
            obj=YAMLFileSubstitution(str(obj_f)),
        )
        result_path = replace.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded["greeting"] == "world"
        os.unlink(result_path)

    def test_default_syntax(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLReplaceSubstitution

        subs_data = {}
        obj_data = {"val": "${MISSING:-default_val}"}
        subs_f = tmp_path / "subs2.yaml"
        obj_f = tmp_path / "obj2.yaml"
        _write_yaml(str(subs_f), subs_data)
        _write_yaml(str(obj_f), obj_data)

        ctx = _make_context()
        replace = YAMLReplaceSubstitution(
            substitutions=YAMLFileSubstitution(str(subs_f)),
            obj=YAMLFileSubstitution(str(obj_f)),
        )
        result_path = replace.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded["val"] == "default_val"
        os.unlink(result_path)

    def test_list_spread(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLReplaceSubstitution

        subs_data = {"ITEMS": ["x", "y"]}
        obj_data = {"items": ["${*ITEMS}"]}
        subs_f = tmp_path / "subs_list.yaml"
        obj_f = tmp_path / "obj_list.yaml"
        _write_yaml(str(subs_f), subs_data)
        _write_yaml(str(obj_f), obj_data)

        ctx = _make_context()
        replace = YAMLReplaceSubstitution(
            substitutions=YAMLFileSubstitution(str(subs_f)),
            obj=YAMLFileSubstitution(str(obj_f)),
        )
        result_path = replace.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded["items"] == ["x", "y"]
        os.unlink(result_path)

    def test_dict_spread(self, tmp_path: pytest.TempPathFactory) -> None:
        from arena_bringup.substitutions import YAMLFileSubstitution, YAMLReplaceSubstitution

        subs_data = {"EXTRA": {"foo": "bar"}}
        obj_data = {"${**EXTRA}": None}
        subs_f = tmp_path / "subs_dict.yaml"
        obj_f = tmp_path / "obj_dict.yaml"
        _write_yaml(str(subs_f), subs_data)
        _write_yaml(str(obj_f), obj_data)

        ctx = _make_context()
        replace = YAMLReplaceSubstitution(
            substitutions=YAMLFileSubstitution(str(subs_f)),
            obj=YAMLFileSubstitution(str(obj_f)),
        )
        result_path = replace.perform(ctx)
        with open(result_path) as fp:
            loaded = yaml.safe_load(fp)
        assert loaded["foo"] == "bar"
        os.unlink(result_path)


class TestCurrentNamespaceSubstitution:
    def test_returns_root_when_not_set(self) -> None:
        from arena_bringup.substitutions import CurrentNamespaceSubstitution

        ctx = _make_context()
        sub = CurrentNamespaceSubstitution()
        assert sub.perform(ctx) == "/"

    def test_returns_configured_namespace(self) -> None:
        from arena_bringup.substitutions import CurrentNamespaceSubstitution

        ctx = _make_context()
        ctx.launch_configurations["ros_namespace"] = "/robot1"
        sub = CurrentNamespaceSubstitution()
        assert sub.perform(ctx) == "/robot1"

    def test_returns_custom_namespace(self) -> None:
        from arena_bringup.substitutions import CurrentNamespaceSubstitution

        ctx = _make_context()
        ctx.launch_configurations["ros_namespace"] = "/my/namespace"
        sub = CurrentNamespaceSubstitution()
        assert sub.perform(ctx) == "/my/namespace"
