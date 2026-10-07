from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

pytest.importorskip("rclpy")
pytest.importorskip("arena_auditory")

from arena_auditory.api import AgentKind, SoundAsset, SoundLibrary
from arena_auditory.assets import Variant
from arena_simulation_setup.shared import Position, Sound
from arena_simulation_setup.shared.semantics import parse_semantics
from geometry_msgs.msg import Point
from task_generator.tasks.modules.sounds.impl import (
    Mod_Sounds,
    _has_initial_sounding,
    _index_static_entities,
    _merge_params,
    _realize_frame,
    _resolve_sound_placement,
    _sound_group_id,
    _sounding_by_default,
)


def _entity(name: str, x: float, y: float, z: float, yaw: float) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        pose=SimpleNamespace(
            position=SimpleNamespace(x=x, y=y, z=z),
            orientation=SimpleNamespace(to_yaw=lambda: yaw),
        ),
    )


def _level(static: list) -> SimpleNamespace:
    return SimpleNamespace(all_static_entities=static)


def _world(**levels: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(levels=levels)


# ---------------------------------------------------------------------------
# static entity indexing
# ---------------------------------------------------------------------------


def test_index_static_entities_indexes_by_level() -> None:
    desk = _entity("desk", 1.0, 2.0, 0.0, 0.0)
    world = _world(a=_level([desk]), b=_level([]))
    indexed = _index_static_entities(world)
    assert indexed == {"desk": [("a", desk)]}


def test_index_static_entities_includes_scenario_statics() -> None:
    desk = _entity("desk", 1.0, 2.0, 0.0, 0.0)
    crate = _entity("crate", 3.0, 3.0, 0.0, 0.0)
    crate.level_id = "a"
    loose = _entity("loose", 0.0, 0.0, 0.0, 0.0)
    loose.level_id = None
    indexed = _index_static_entities(_world(a=_level([desk])), [crate, loose])
    assert indexed == {"desk": [("a", desk)], "crate": [("a", crate)], "loose": [("", loose)]}


def test_index_static_entities_tracks_duplicate_names_across_levels() -> None:
    desk_a = _entity("desk", 0.0, 0.0, 0.0, 0.0)
    desk_b = _entity("desk", 5.0, 5.0, 0.0, 0.0)
    world = _world(a=_level([desk_a]), b=_level([desk_b]))
    indexed = _index_static_entities(world)
    assert indexed["desk"] == [("a", desk_a), ("b", desk_b)]


# ---------------------------------------------------------------------------
# sound placement resolution
# ---------------------------------------------------------------------------


def test_resolve_sound_placement_entity_ref_rotates_offset_by_entity_yaw() -> None:
    desk = _entity("desk", 1.0, 2.0, 0.5, math.pi / 2)
    indexed = {"desk": [("a", desk)]}
    sound = Sound(name="chime", asset_id="radio_loop", entity_ref="desk", offset=Position(1.0, 0.0, 0.25))
    world = _world(a=_level([desk]))

    position, yaw, level_id = _resolve_sound_placement(sound, world, indexed, "a")

    assert level_id == "a"
    assert yaw == pytest.approx(math.pi / 2)
    assert position.x == pytest.approx(1.0)
    assert position.y == pytest.approx(3.0)
    assert position.z == pytest.approx(0.75)


def test_resolve_sound_placement_entity_ref_unknown_raises() -> None:
    sound = Sound(name="chime", asset_id="radio_loop", entity_ref="missing")
    world = _world(a=_level([]))
    with pytest.raises(ValueError, match="unknown static entity"):
        _resolve_sound_placement(sound, world, {}, "a")


def test_resolve_sound_placement_entity_ref_ambiguous_raises() -> None:
    desk_a = _entity("desk", 0.0, 0.0, 0.0, 0.0)
    desk_b = _entity("desk", 5.0, 5.0, 0.0, 0.0)
    indexed = {"desk": [("a", desk_a), ("b", desk_b)]}
    sound = Sound(name="chime", asset_id="radio_loop", entity_ref="desk")
    world = _world(a=_level([desk_a]), b=_level([desk_b]))
    with pytest.raises(ValueError, match="ambiguous static entity"):
        _resolve_sound_placement(sound, world, indexed, "a")


def test_resolve_sound_placement_position_uses_context_level() -> None:
    sound = Sound(name="alarm", asset_id="alarm_loop", position=Position(2.0, 3.0, 0.0), offset=Position(0.0, 0.0, 1.0))
    world = _world(a=_level([]), b=_level([]))

    position, yaw, level_id = _resolve_sound_placement(sound, world, {}, "b")

    assert level_id == "b"
    assert yaw == 0.0
    assert position.x == pytest.approx(2.0)
    assert position.y == pytest.approx(3.0)
    assert position.z == pytest.approx(1.0)


def test_resolve_sound_placement_position_infers_sole_level() -> None:
    sound = Sound(name="alarm", asset_id="alarm_loop", position=Position(0.0, 0.0, 0.0))
    world = _world(only=_level([]))

    _, _, level_id = _resolve_sound_placement(sound, world, {}, None)

    assert level_id == "only"


def test_resolve_sound_placement_position_requires_level_in_multi_level_world() -> None:
    sound = Sound(name="alarm", asset_id="alarm_loop", position=Position(0.0, 0.0, 0.0))
    world = _world(a=_level([]), b=_level([]))
    with pytest.raises(ValueError, match="requires level in a multi-level world"):
        _resolve_sound_placement(sound, world, {}, None)


def test_resolve_sound_placement_position_honors_sound_level_without_context() -> None:
    sound = Sound(name="alarm", asset_id="alarm_loop", position=Position(0.0, 0.0, 0.0), level="b")
    world = _world(a=_level([]), b=_level([]))

    _, _, level_id = _resolve_sound_placement(sound, world, {}, None)

    assert level_id == "b"


# ---------------------------------------------------------------------------
# frame realization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "frame", "expected"),
    [
        ("env_0", "jackal/base_link", "env_0/jackal/base_link"),
        ("env_0", "env_0/jackal/base_link", "env_0/jackal/base_link"),
        ("env_0", "env_0", "env_0"),
        ("/env_0/", "jackal/base_link", "env_0/jackal/base_link"),
        ("", "jackal/base_link", "jackal/base_link"),
        ("env_0", "env_01/jackal/base_link", "env_0/env_01/jackal/base_link"),
    ],
)
def test_realize_frame_prefixes_once(env: str, frame: str, expected: str) -> None:
    assert _realize_frame(env, frame) == expected


# ---------------------------------------------------------------------------
# group_id derivation
# ---------------------------------------------------------------------------


def test_merge_params_shallow_merges_across_cfgs() -> None:
    cfgs = parse_semantics(
        [
            {"predicate": "sounding", "params": {"sound_on": "fire_alarm"}},
            {"state": "volume_db", "params": {"regime": "fire_alarm"}},
        ],
    )
    assert _merge_params(cfgs) == {"sound_on": "fire_alarm", "regime": "fire_alarm"}


def test_sound_group_id_prefers_sound_on_regime() -> None:
    cfgs = parse_semantics([{"predicate": "sounding", "params": {"sound_on": "fire_alarm"}}])
    assert _sound_group_id(cfgs, "env_0/1_alarm") == "fire_alarm"


def test_sound_group_id_falls_back_to_realized_name() -> None:
    cfgs = parse_semantics([{"preset": "sound"}])
    assert _sound_group_id(cfgs, "env_0/1_alarm") == "env_0/1_alarm"


@pytest.mark.parametrize(
    ("semantics", "expected"),
    [
        ([{"preset": "sound"}], False),
        ([{"preset": "sound", "params": {"volume_db": 62.0}}], False),
        ([{"preset": "sound", "params": {"sounding": False}}], True),
        ([{"preset": "sound", "params": {"sounding": True}}], True),
        ([{"preset": "sound", "params": {"sound_on": "alarm"}}], True),
    ],
)
def test_has_initial_sounding(semantics: list, expected: bool) -> None:
    assert _has_initial_sounding(parse_semantics(semantics)) is expected


def _launch_sound(semantics: list) -> Sound:
    return Sound(name="radio", asset_id="radio_loop", position=Position(1.0, 2.0, 1.2), semantics=semantics)


def test_sounding_by_default_turns_on_a_bare_preset() -> None:
    snd = _sounding_by_default(_launch_sound([{"preset": "sound", "params": {"volume_db": 62.0}}]))
    values = {cfg.name: cfg.value for cfg in snd.semantics}
    assert values == {"sounding": True, "volume_db": 62.0}


def test_sounding_by_default_adds_the_predicate_when_missing() -> None:
    snd = _sounding_by_default(_launch_sound([{"state": "volume_db", "value": 62.0}]))
    assert [(cfg.role, cfg.name, cfg.value) for cfg in snd.semantics] == [("state", "volume_db", 62.0), ("predicate", "sounding", True)]


@pytest.mark.parametrize(
    "semantics",
    [
        [{"preset": "sound", "params": {"sounding": False}}],
        [{"preset": "sound", "params": {"sound_on": "alarm"}}],
    ],
)
def test_sounding_by_default_leaves_a_decided_entry_alone(semantics: list) -> None:
    snd = _launch_sound(semantics)
    before = [(cfg.name, cfg.value, dict(cfg.params)) for cfg in snd.semantics]
    _sounding_by_default(snd)
    assert [(cfg.name, cfg.value, dict(cfg.params)) for cfg in snd.semantics] == before


# ---------------------------------------------------------------------------
# asset resolution
# ---------------------------------------------------------------------------


def _build(snd: Sound, asset: SoundAsset):
    return Mod_Sounds._build_resolved(object.__new__(Mod_Sounds), snd, asset, "env_0/radio", Point(x=1.0, y=2.0, z=1.2), 0.5, "map")


def test_build_resolved_takes_kind_tags_and_level_from_the_asset() -> None:
    asset = SoundAsset(
        id="radio_loop",
        kind="music",
        tags=("loop",),
        level_db=62.0,
        normalize_dbfs=-12.5,
        variants=(Variant(id="radio_loop_01", model="wav", tags=("radio", "music")),),
    )
    resolved = _build(_launch_sound([{"preset": "sound"}]), asset)
    assert (resolved.asset_id, resolved.kind, resolved.variant_id, resolved.model) == ("radio_loop", "music", "radio_loop_01", "wav_loop")
    assert resolved.tags == ("radio", "music")
    assert resolved.level_db == 62.0


def test_build_resolved_known_catalog_asset() -> None:
    resolved = _build(_launch_sound([{"preset": "sound"}]), SoundLibrary.default().asset("radio_loop"))
    assert resolved.kind == "music"
    assert resolved.tags == ("radio", "music")


def test_default_asset_of_each_environment_kind() -> None:
    library = SoundLibrary.default()
    assert library.kinds_of(AgentKind.ENVIRONMENT) == ("music", "alarm")
    assert library.default_asset("music").id == "radio_loop"
    assert library.default_asset("alarm").id == "alarm_loop"
    with pytest.raises(KeyError, match="has no default asset"):
        library.default_asset("onset")
