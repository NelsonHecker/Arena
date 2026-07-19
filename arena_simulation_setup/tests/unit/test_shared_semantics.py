from __future__ import annotations

import pytest

from arena_simulation_setup.shared.semantics import SemanticCfg, parse_semantics
from arena_simulation_setup.utils.cattrs import converter

# ---------------------------------------------------------------------------
# SemanticCfg.parse / serialize
# ---------------------------------------------------------------------------


def test_parse_state_primitive():
    cfg = SemanticCfg.parse({'state': 'progress', 'value': 0.4})
    assert cfg.role == 'state'
    assert cfg.name == 'progress'
    assert cfg.value == 0.4


def test_parse_predicate_primitive():
    cfg = SemanticCfg.parse({'predicate': 'quiet', 'value': True})
    assert cfg.role == 'predicate'
    assert cfg.name == 'quiet'
    assert cfg.value is True


def test_parse_defaults():
    cfg = SemanticCfg.parse({'state': 'state'})
    assert cfg.value is None
    assert cfg.binding == 'kinematic'
    assert cfg.trigger == 'proximity'
    assert cfg.distance == -1.0


def test_parse_requires_state_or_predicate_key():
    with pytest.raises(ValueError):
        SemanticCfg.parse({'value': 1.0})


def test_parse_rejects_unknown_keys():
    with pytest.raises(ValueError):
        SemanticCfg.parse({'state': 'state', 'bogus': 1})


def test_parse_binding_joint_rejected():
    with pytest.raises(ValueError):
        SemanticCfg.parse({'state': 'state', 'binding': 'joint'})


def test_parse_trigger_contact_rejected():
    with pytest.raises(ValueError):
        SemanticCfg.parse({'predicate': 'open', 'trigger': 'contact'})


def test_serialize_omits_defaults():
    cfg = SemanticCfg.parse({'state': 'state'})
    assert cfg.serialize() == {'state': 'state'}


def test_serialize_includes_non_default_distance():
    cfg = SemanticCfg.parse({'predicate': 'quiet', 'value': True, 'distance': 2.0})
    assert cfg.serialize() == {'predicate': 'quiet', 'value': True, 'distance': 2.0}


# ---------------------------------------------------------------------------
# parse_semantics: presets and passthrough
# ---------------------------------------------------------------------------


def test_parse_semantics_door_preset_expands():
    cfgs = parse_semantics([{'preset': 'door', 'distance': 2.0}])
    assert [(c.role, c.name) for c in cfgs] == [
        ('state', 'state'),
        ('state', 'progress'),
        ('predicate', 'open'),
        ('predicate', 'in_transit'),
        ('predicate', 'triggered'),
    ]
    assert all(c.distance == 2.0 for c in cfgs)


def test_parse_semantics_elevator_preset_expands():
    cfgs = parse_semantics([{'preset': 'elevator'}])
    assert [(c.role, c.name) for c in cfgs] == [
        ('state', 'arriving_eta'),
        ('state', 'occupants'),
        ('predicate', 'departing'),
        ('predicate', 'in_transit'),
        ('predicate', 'dispatched'),
        ('predicate', 'just_arrived'),
    ]


def test_parse_semantics_unknown_preset_rejected():
    with pytest.raises(ValueError):
        parse_semantics([{'preset': 'bogus'}])


def test_parse_semantics_primitive_passthrough():
    cfgs = parse_semantics([{'state': 'max_speed', 'value': 1.5}, {'predicate': 'quiet', 'value': True}])
    assert len(cfgs) == 2
    assert cfgs[0].name == 'max_speed'
    assert cfgs[1].name == 'quiet'


def test_parse_semantics_idempotent_on_existing_cfgs():
    cfgs = parse_semantics([{'state': 'state'}])
    assert parse_semantics(cfgs) == cfgs


def test_parse_semantics_empty_list():
    assert parse_semantics([]) == []


# ---------------------------------------------------------------------------
# cattrs structure/unstructure of list[SemanticCfg] (as used on Door/Elevator/Zone)
# ---------------------------------------------------------------------------


def test_structure_list_of_semanticcfg_expands_preset():
    cfgs = converter.structure([{'preset': 'door'}], list[SemanticCfg])
    assert len(cfgs) == 5


def test_structure_list_of_semanticcfg_rejects_joint_binding():
    with pytest.raises(Exception):
        converter.structure([{'state': 'state', 'binding': 'joint'}], list[SemanticCfg])


def test_unstructure_semanticcfg_round_trip():
    cfgs = parse_semantics([{'preset': 'door', 'distance': 2.0}])
    raw = converter.unstructure(cfgs)
    restructured = converter.structure(raw, list[SemanticCfg])
    assert restructured == cfgs
