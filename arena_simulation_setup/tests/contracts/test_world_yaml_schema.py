from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from arena_simulation_setup.tree.World.World import LevelDescription
from arena_simulation_setup.utils.cattrs import converter

_WORLD_YAML = Path(__file__).resolve().parents[2] / 'worlds' / 'three_storied_residential' / '1' / 'world.yaml'


@pytest.fixture(scope='module')
def _raw_world_data() -> dict:
    if not _WORLD_YAML.exists():
        pytest.skip(f'fixture world not found: {_WORLD_YAML}')
    with open(_WORLD_YAML, encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_existing_world_loads_unchanged(_raw_world_data):
    level_desc = converter.structure(_raw_world_data, LevelDescription)
    for zone in level_desc.zones:
        assert zone.semantics == []
        for door in zone.doors:
            assert door.semantics == []
        for elevator in zone.elevators:
            assert elevator.semantics == []


def test_existing_world_semantics_omitted_on_unstructure(_raw_world_data):
    level_desc = converter.structure(_raw_world_data, LevelDescription)
    unstructured = converter.unstructure(level_desc)
    for zone in unstructured['zones']:
        assert zone['semantics'] == []
        for door in zone.get('doors', []):
            assert 'semantics' not in door
        for elevator in zone.get('elevators', []):
            assert 'semantics' not in elevator


def test_existing_world_reparse_is_stable(_raw_world_data):
    level_desc = converter.structure(_raw_world_data, LevelDescription)
    unstructured = converter.unstructure(level_desc)
    reparsed = converter.structure(unstructured, LevelDescription)
    assert [zone.name for zone in reparsed.zones] == [zone.name for zone in level_desc.zones]
    assert [door.name for door in reparsed.all_doors] == [door.name for door in level_desc.all_doors]
    assert [elevator.name for elevator in reparsed.all_elevators] == [elevator.name for elevator in level_desc.all_elevators]
    for zone in reparsed.zones:
        assert zone.semantics == []
        for door in zone.doors:
            assert door.semantics == []
        for elevator in zone.elevators:
            assert elevator.semantics == []
