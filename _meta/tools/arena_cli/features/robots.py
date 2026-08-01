"""robots feature: per-robot submodule management."""

import os
import sys

import click
import common

SCRIPT_SHA256: str = "2e04ebf682574ff4d851917fb2fdacff3bc5ca270174c55714309e0b4191e4d7"

_NAME = "robots"


def _payload() -> str:
    path = common._reg_resolve(_NAME)
    if path is None:
        raise click.ClickException(f"unknown feature '{_NAME}'")
    return os.path.join(os.path.dirname(path), f"{_NAME}.py")


def _deps_build() -> int:
    import shlex

    src = common._env("SOURCE_FILE")
    return common._run(os.environ.get("SHELL", "/bin/bash"), "-c", f"source {shlex.quote(src)} > /dev/null 2>&1 && arena deps && arena build")

_HELP = (
    "Per-robot submodule management (mesh assets + upstream deps).\n\n"
    "\b\n"
    "  add <name...>        clone robot's submodules (alias: install)\n"
    "  rm <name...|--all>   deinit robot's submodules (alias: uninstall <name...>)\n"
    "  ls                   list robots, [x] ready, [ ] pending\n"
    "  check [--all]        verify all package://arena_robots/... URIs resolve\n"
    "  update               refresh initialized robot submodules\n"
    "  uninstall            deinit all robot submodules\n"
    "  drive [opts]         run a random-goal episode per ready robot, report success/total"
)


def _forward(verb: str, args: tuple[str, ...]) -> int:
    import subprocess

    return subprocess.run(["python3", _payload(), verb, *args], check=False).returncode


@click.group(name=_NAME, no_args_is_help=True, context_settings=common.HELP_NAMES, help=_HELP)
def group() -> None:
    pass


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="clone robot's submodules (alias: install)")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def add(args: tuple[str, ...]) -> None:
    rc = _forward("add", args)
    sys.exit(rc if rc else _deps_build())


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="Update the feature to the latest state.")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def update(args: tuple[str, ...]) -> None:
    if not common._reg_has(_NAME):
        raise click.ClickException(f"{_NAME} is not installed, run 'arena feature {_NAME} install' first")
    rc = _forward("update", args)
    sys.exit(rc if rc else _deps_build())


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="deinit robot's submodules (alias: uninstall <name...>)")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def rm(args: tuple[str, ...]) -> None:
    sys.exit(_forward("rm", args))


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="list robots, [x] ready, [ ] pending")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def ls(args: tuple[str, ...]) -> None:
    sys.exit(_forward("ls", args))


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="verify all package://arena_robots/... URIs resolve")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def check(args: tuple[str, ...]) -> None:
    sys.exit(_forward("check", args))


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="run a random-goal episode per ready robot, report success/total")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def drive(args: tuple[str, ...]) -> None:
    sys.exit(_forward("drive", args))


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="clone robot's submodules (alias for add)")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def install(args: tuple[str, ...]) -> None:
    rc = _forward("add", args)
    sys.exit(rc if rc else _deps_build())


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="Uninstall and unregister the feature.")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def uninstall(args: tuple[str, ...]) -> None:
    if args:
        sys.exit(_forward("rm", args))
    _forward("uninstall", ())
    common._reg_remove(_NAME)
    sys.exit(0)
