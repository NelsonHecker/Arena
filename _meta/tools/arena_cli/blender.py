"""arena blender: 3D Blender visualization pipeline."""

from __future__ import annotations

import sys

from common import make_verb
from complete import Sub


def cmd(argv: list[str]) -> None:
    """3D Blender visualization pipeline (build, render, hud).

    \b
    Usage:
      arena blender build --world <world> [options]
      arena blender render --blend <path.blend> --output <path.png> [options]
      arena blender hud --benchmark <bench> --episode <ep> [options]
    """
    from arena_blender_viz import cli as viz_cli

    sys.argv = ["arena blender", *argv]
    viz_cli.main()


VERB = make_verb(
    "blender",
    cmd,
    passthrough=True,
    complete=Sub(
        {
            "build": None,
            "render": None,
            "hud": None,
        }
    ),
)
