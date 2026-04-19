"""Hypothesis property tests for arena_robots.bringup registry invariants."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


def _make_bringup_class(kind: str) -> type:
    from arena_robots.bringup import Bringup

    class _TestBringup(Bringup):
        pass

    _TestBringup.kind = kind
    _TestBringup.requires = frozenset()
    _TestBringup._launch_actions = lambda self, **kw: []
    return _TestBringup


@given(
    kinds=st.lists(
        st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), min_codepoint=65), min_size=1, max_size=20),
        min_size=1,
        max_size=10,
        unique=True,
    ).map(lambda ks: [f"__prop_{k}__" for k in ks])
)
@settings(max_examples=30)
def test_all_registered_kinds_are_retrievable(kinds: list[str]) -> None:
    """After registering N unique kinds, all are retrievable exactly once."""
    from arena_robots.bringup import _BRINGUPS, get_bringup, register_bringup

    registered = []
    try:
        for kind in kinds:
            if kind in _BRINGUPS:
                continue
            cls = _make_bringup_class(kind)
            register_bringup(cls)
            registered.append(kind)

        for kind in registered:
            result = get_bringup(kind)
            assert result is not None
            assert result.kind == kind
    finally:
        for kind in registered:
            _BRINGUPS.pop(kind, None)


@given(
    kind=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), min_codepoint=65),
        min_size=1,
        max_size=20,
    ).map(lambda k: f"__propdup_{k}__")
)
@settings(max_examples=20)
def test_duplicate_registration_always_raises(kind: str) -> None:
    """Registering the same kind twice always raises."""
    from arena_robots.bringup import _BRINGUPS, register_bringup

    old = _BRINGUPS.pop(kind, None)
    cls1 = _make_bringup_class(kind)
    cls2 = _make_bringup_class(kind)
    try:
        register_bringup(cls1)
        with pytest.raises(Exception):
            register_bringup(cls2)
    finally:
        _BRINGUPS.pop(kind, None)
        if old is not None:
            _BRINGUPS[kind] = old


@given(
    kind=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",), min_codepoint=97),
        min_size=3,
        max_size=20,
    ).map(lambda k: f"__propget_{k}__")
)
@settings(max_examples=20)
def test_get_unregistered_always_raises(kind: str) -> None:
    """Getting an unregistered kind always raises KeyError."""
    from arena_robots.bringup import _BRINGUPS, get_bringup

    _BRINGUPS.pop(kind, None)
    with pytest.raises(KeyError):
        get_bringup(kind)
