"""Python feature groups, used only while the script they mirror is unchanged."""

import hashlib
import importlib
from collections.abc import Callable

import click
from common import _reg_add, _reg_has, _reg_pull, _reg_remove, _reg_resolve


def load(name: str) -> click.Group | None:
    """Return the feature's Python group, or None to fall back to its script."""
    try:
        mod = importlib.import_module(f"features.{name}")
    except ImportError:
        return None
    path = _reg_resolve(name)
    if path is None:
        return None
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != mod.SCRIPT_SHA256:
        return None
    return mod.group


def default_install(name: str, update: Callable[[], int]) -> int:
    """Pull repos, register, run update, rolling back the registration on failure."""
    if _reg_has(name):
        click.echo(f"{name} is already installed.")
        return 0
    _reg_pull(name)
    _reg_add(name)
    if update() == 0:
        click.echo(f"Installed {name} successfully.")
        return 0
    _reg_remove(name)
    click.echo(f"Install of {name} failed during update.", err=True)
    return 1
