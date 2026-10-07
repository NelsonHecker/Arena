from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    pytest.importorskip("rclpy")
    pytest.importorskip("arena_auditory")
    pytest.importorskip("arena_auditory_msgs.msg")
    pytest.importorskip("task_generator_msgs.msg")


def _with_module(body):
    from arena_rclpy_mixins.Async import AsyncNode
    from arena_rclpy_mixins.ServiceNamespace import ServiceNamespace
    from arena_rclpy_mixins.shared import Namespace
    from arena_runtime.sim.dummy_simulator import DummySimulator
    from task_generator.manager.realizer import Realizer
    from task_generator.tasks.modules.sounds.impl import Mod_Sounds

    class _Node(ServiceNamespace, AsyncNode):
        pass

    suffix = f"t_{uuid.uuid4().hex[:8]}"
    ns = Namespace(f"/test/{suffix}")

    async def main():
        node = _Node(f"sounds_volume_{suffix}", namespace=str(ns))
        try:
            realizer = Realizer(Realizer._Configuration(x=0.0, y=0.0, prefix=""))
            node._simulator = DummySimulator(node=node, namespace=ns, realizer=realizer)
            return await body(node, Mod_Sounds(node=node, ctx=None, namespace=ns, task=None))
        finally:
            node.destroy_node()

    return asyncio.run(main())


def _launch_sound(entry: str):
    import yaml
    from arena_simulation_setup.shared import Sound
    from arena_simulation_setup.utils.cattrs import converter
    from task_generator.tasks.modules.sounds.impl import _sounding_by_default

    return _sounding_by_default(converter.structure(yaml.safe_load(entry), list[Sound])[0])


def _published_volume(entry: str) -> float:
    from geometry_msgs.msg import Point

    async def body(node, module) -> float:
        sound = _launch_sound(entry)
        module._sounds = {sound.name: module._build_resolved(sound, module._library.asset(sound.asset_id), sound.name, Point(), 0.0, "map")}
        node._simulator.attach_semantics("sound", sound.name, sound.semantics)
        (msg,) = await module._source_msgs()
        assert msg.source.active
        return float(msg.source.level_db)

    return _with_module(body)


def test_configured_static_sound_without_a_volume_emits_at_the_catalog_reference_level(rclpy_context) -> None:
    from arena_auditory.api import SoundLibrary

    assert _published_volume("[{name: radio, asset_id: radio_loop, position: {x: 1.0, y: 2.0}}]") == pytest.approx(SoundLibrary.default().asset("radio_loop").level_db)


@pytest.mark.parametrize(
    "manifest",
    [
        {"version": 2, "kind": "music", "normalize_dbfs": -12.5, "variants": [{"id": "broken_01", "file": "broken.wav"}]},
        {"version": 2, "kind": "music", "level_db": 62.0, "normalize_dbfs": -12.5, "variants": [{"id": "broken_01", "file": "broken.wav"}]},
    ],
    ids=["missing_level_db", "missing_wav"],
)
def test_sound_with_an_unresolvable_asset_stays_silent(rclpy_context, tmp_path: Path, manifest: dict) -> None:
    import yaml

    directory = tmp_path / "world" / "assets" / "Common" / "Sound" / "tmp_broken"
    directory.mkdir(parents=True)
    (directory / "tmp_broken.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    async def body(_node, module):
        module._library.use_world(tmp_path / "world")
        try:
            sound = _launch_sound("[{name: broken, asset_id: tmp_broken, position: {x: 1.0, y: 2.0}}]")
            return module._resolve_and_build(sound, SimpleNamespace(levels={}), {}, None, sound.name)
        finally:
            module._library.use_world(None)

    assert _with_module(body) is None
