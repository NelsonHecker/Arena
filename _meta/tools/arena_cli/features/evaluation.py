"""evaluation feature: recording, metrics, benchmarking."""

import os
import sys

import click
import common

SCRIPT_SHA256 = "cd5e8276c1a82d186e77767a0081594de5b60b885cdf0ddecae7b5d824655d6f"

NAME = "evaluation"


def _require() -> None:
    if not common._reg_has(NAME):
        raise click.ClickException(f"{NAME} is not installed; run 'arena feature {NAME} install' first.")


def _update() -> int:
    """Pull the arena_evaluation submodule and rebuild."""
    import shlex
    import subprocess

    arena_dir = common._env("ARENA_DIR")
    arena_ws_dir = common._env("ARENA_WS_DIR")

    rc = subprocess.run(
        ["git", "submodule", "update", "--init", "--rebase", "--depth", "1", "arena_evaluation"],
        cwd=arena_dir,
        check=False,
    ).returncode
    if rc:
        return rc

    src = common._env("SOURCE_FILE")
    cmd = f"source {shlex.quote(src)} > /dev/null 2>&1 && arena build"
    return subprocess.run(
        [os.environ.get("SHELL", "/bin/bash"), "-c", cmd],
        cwd=arena_ws_dir,
        check=False,
    ).returncode


@click.group(
    name="evaluation",
    no_args_is_help=True,
    context_settings=common.HELP_NAMES,
    help="arena_evaluation for recording, metrics, and benchmarking.",
)
def group() -> None:
    pass


@group.command()
def install() -> None:
    """register feature, pull arena_evaluation submodule and rebuild"""
    from features import default_install

    sys.exit(default_install(NAME, _update))


@group.command()
def update() -> None:
    """pull arena_evaluation submodule and rebuild"""
    if not common._reg_has(NAME):
        raise click.ClickException(f"{NAME} is not installed, run 'arena feature {NAME} install' first")
    sys.exit(_update())


@group.command()
def uninstall() -> None:
    """deinit arena_evaluation and remove from registry"""
    import subprocess

    arena_dir = common._env("ARENA_DIR")
    subprocess.run(["git", "submodule", "deinit", "-f", "arena_evaluation"], cwd=arena_dir, check=False)
    common._reg_remove(NAME)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def benchmark(args: tuple[str, ...]) -> None:
    """run a benchmark suite (ros2 run arena_evaluation benchmark)"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "benchmark", *args)


@group.command(name="list", context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def list_(args: tuple[str, ...]) -> None:
    """list available evaluations"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation_cli", "list", *args)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def status(args: tuple[str, ...]) -> None:
    """show status of a running or completed evaluation"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation_cli", "status", *args)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def tail(args: tuple[str, ...]) -> None:
    """stream live output of a running evaluation"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation_cli", "tail", *args)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def extract(args: tuple[str, ...]) -> None:
    """extract MCAP topics into the Parquet cache"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation", "extract", *args)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(args: tuple[str, ...]) -> None:
    """process recording and generate HTML report"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation", "run", *args)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def process(args: tuple[str, ...]) -> None:
    """process recording to generate metrics.parquet"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation", "process", *args)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def report(args: tuple[str, ...]) -> None:
    """generate HTML report from processed metrics"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation", "report", *args)


@group.command(context_settings=common.PASSTHROUGH | common.HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def plot(args: tuple[str, ...]) -> None:
    """generate static PNG plots from processed metrics"""
    _require()
    common._exec("ros2", "run", "arena_evaluation", "evaluation", "plot", *args)
