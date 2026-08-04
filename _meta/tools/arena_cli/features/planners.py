"""planners feature: per-planner submodule management."""

import os
import sys

import click
import common

SCRIPT_SHA256: str = "9ec049d7d266aa4c448747ccb4a141174e8b11c59b2766c27e7757e52b5dc3f8"

_NAME = "planners"


def _payload() -> str:
    path = common._reg_resolve(_NAME)
    if path is None:
        raise click.ClickException(f"unknown feature '{_NAME}'")
    return os.path.join(os.path.dirname(path), f"{_NAME}.py")


def _deps_build() -> int:
    import shlex

    src = common._env("SOURCE_FILE")
    return common._run(os.environ.get("SHELL", "/bin/bash"), "-c", f"source {shlex.quote(src)} > /dev/null 2>&1 && arena deps && arena build --executor sequential")

_HELP = (
    "Per-planner submodule management.\n\n"
    "\b\n"
    "  add <name...>        clone planner's submodules (alias: install)\n"
    "  rm <name...|--all>   deinit planner's submodules (alias: uninstall <name...>)\n"
    "  ls                   list planners, [x] ready, [ ] pending\n"
    "  check [--all]        verify planner submodules are initialized\n"
    "  update               refresh initialized planner submodules\n"
    "  uninstall            deinit all planner submodules"
)


def _forward(verb: str, args: tuple[str, ...]) -> int:
    import subprocess

    return subprocess.run(["python3", _payload(), verb, *args], check=False).returncode


@click.group(name=_NAME, no_args_is_help=True, context_settings=common.HELP_NAMES, help=_HELP)
def group() -> None:
    pass


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="clone planner's submodules (alias: install)")
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


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="deinit planner's submodules (alias: uninstall <name...>)")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def rm(args: tuple[str, ...]) -> None:
    sys.exit(_forward("rm", args))


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="list planners, [x] ready, [ ] pending")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def ls(args: tuple[str, ...]) -> None:
    sys.exit(_forward("ls", args))


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="verify planner submodules are initialized")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def check(args: tuple[str, ...]) -> None:
    sys.exit(_forward("check", args))


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES, help="clone planner's submodules (alias for add)")
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
