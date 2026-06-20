"""Unified CLI for Arena viewport-camera scripting.

One command shape for everything:

    arena cam <name> [key=value ...] [--ns NS]   # name is a verb, a shot, or a .yaml file
    arena cam <name> ... record=<dir> [fps=30] [-f]   # render to a PPM frame sequence instead
    arena cam list                               # catalog of verbs and shots
    arena cam show <name>                        # parameters of a verb or shot

A verb and a shot launch identically; the caller need not know which a name is.
Params are bare `key=value` (coerced: number / x,y,z tuple / bool / string);
launcher options are `--flags`. Nested or list-valued params live in a shot file.
The reserved params `record` (output dir) and `fps` switch from live playback to
deterministic capture.
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys

import yaml

from arena_runtime.cam import Camera, load_shot
from arena_runtime.cam.registry import PRIMITIVES
from arena_runtime.cam.shots import SHOTS


def _coerce(token: str) -> object:
    low = token.lower()
    if low in ("true", "false"):
        return low == "true"
    if "," in token:
        return tuple(_coerce(part) for part in token.split(","))
    try:
        return float(token)
    except ValueError:
        return token


def _parse_params(tokens: list[str]) -> dict:
    params: dict = {}
    for token in tokens:
        if "=" not in token:
            raise SystemExit(f"expected key=value, got {token!r}")
        key, _, value = token.partition("=")
        params[key] = _coerce(value)
    return params


def _is_path(name: str) -> bool:
    return name.endswith((".yaml", ".yml")) or "/" in name or os.path.exists(name)


def _print_catalog() -> None:
    print("verbs:")
    for verb in sorted(PRIMITIVES):
        print(f"  {verb}")
    print("shots:")
    for shot in sorted(SHOTS):
        print(f"  {shot}")
    if not SHOTS:
        print("  (none installed)")


def _show(name: str) -> None:
    if name in PRIMITIVES:
        cls = PRIMITIVES[name]
        print(f"{name} (verb)")
        for param in inspect.signature(cls.__init__).parameters.values():
            if param.name == "self":
                continue
            default = "" if param.default is inspect.Parameter.empty else f" = {param.default!r}"
            print(f"  {param.name}{default}")
        if cls.__doc__:
            print(f"  -- {cls.__doc__.strip().splitlines()[0]}")
    elif name in SHOTS:
        print(f"{name} (shot)")
        print(yaml.safe_dump(SHOTS[name], sort_keys=False, default_flow_style=False).rstrip())
    else:
        raise SystemExit(f"unknown name: {name!r} (try 'arena cam list')")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="arena cam", description="Arena viewport-camera CLI")
    parser.add_argument("name", nargs="?", help="verb, shot, or .yaml file (or 'list' / 'show')")
    parser.add_argument("params", nargs="*", metavar="key=value", help="verb or shot parameters")
    parser.add_argument("--ns", default="/arena", metavar="NS", help="arena namespace")
    parser.add_argument("-f", "--force", action="store_true", help="overwrite a non-empty record dir")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.name is None or args.name == "list":
        _print_catalog()
        return
    if args.name == "show":
        if not args.params:
            parser.error("show needs a name: arena cam show <verb|shot>")
        _show(args.params[0])
        return
    params = _parse_params(args.params)
    record = params.pop("record", None)
    fps = float(params.pop("fps", 30.0))

    cam = load_shot(args.name, arena_ns=args.ns) if _is_path(args.name) else Camera(args.ns).add(args.name, params)
    if record is not None:
        try:
            cam.record(str(record), fps=fps, force=args.force)
        except FileExistsError as e:
            raise SystemExit(str(e)) from e
    else:
        cam.play()


if __name__ == "__main__":
    main()
