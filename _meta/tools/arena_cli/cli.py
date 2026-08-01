"""arena CLI, invoked by the shell shim in _meta/tools/source."""

import os
import sys

import click
import features as _features
import human as _human_mod
import robot as _robot_mod
import viz as _viz_mod
from common import (
    HELP_NAMES,
    PASSTHROUGH,
    _env,
    _exec,
    _feature_dispatch,
    _reg_add,
    _reg_has,
    _reg_list,
    _reg_pull,
    _reg_remove,
    _reg_resolve,
    _run,
    _script_desc,
    _script_help,
)


def _select_args(args: tuple[str, ...]) -> list[str]:
    argv = list(args)
    if argv and not argv[0].startswith("--"):
        argv = ["--packages-select", *argv]
    return argv


def _supervisor(*argv: str) -> None:
    _exec("python3", "-m", "arena_bringup.supervisor", *argv)


SECTIONS = {
    "Simulation": ["runtime", "env", "viz", "cleanup", "launch", "train", "demo"],
    "Attach": ["human", "robot", "cam"],
    "Workspace": ["build", "rebuild", "test", "deps", "update", "preload"],
    "Features": ["feature", "registry"],
    "Shell": ["deactivate", "resource", "repair"],
}


class SectionedGroup(click.Group):
    """Top-level group with the command listing rendered in sections."""

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        listed: set[str] = set()
        sections = dict(SECTIONS)
        sections["Other"] = [n for n in self.list_commands(ctx) if not any(n in names for names in SECTIONS.values())]
        limit = formatter.width - 6 - max(len(n) for n in self.list_commands(ctx))
        for title, names in sections.items():
            rows = []
            for name in names:
                cmd = self.get_command(ctx, name)
                if cmd is None or cmd.hidden or name in listed:
                    continue
                listed.add(name)
                rows.append((name, cmd.get_short_help_str(limit)))
            if rows:
                with formatter.section(title):
                    formatter.write_dl(rows)


@click.group(cls=SectionedGroup, context_settings=HELP_NAMES)
def main() -> None:
    """Arena workspace CLI.

    Sim launching, fleet control, builds, and feature management for the
    arena_ws workspace. Most verbs forward KEY:=VALUE tokens verbatim to
    the underlying launch file or tool.
    """
    os.chdir(_env("ARENA_WS_DIR"))


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def launch(args: tuple[str, ...]) -> None:
    """Start a full simulation (runtime, envs, viz).

    Attaches additively if a runtime is already up, spawning env_n more
    envs against it (errors on sim:= mismatch). Otherwise starts
    arena_runtime.launch.py, spawns N envs, and attaches rviz unless
    headless:=true.
    """
    _supervisor(*args)


DEMO_DEFAULTS = ("tm_robots:=demo", "world:=demo", "sim:=isaac", "viz.view:=robot3p")


@main.command(
    context_settings=PASSTHROUGH | HELP_NAMES,
    help=f"Launch a demo.\n\nSame as `arena launch` with defaults {' '.join(DEMO_DEFAULTS)}, any KEY:=VALUE you pass overrides the corresponding default.",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def demo(args: tuple[str, ...]) -> None:
    given = {a.split(":=", 1)[0] for a in args if ":=" in a}
    merged = [d for d in DEMO_DEFAULTS if d.split(":=", 1)[0] not in given]
    _supervisor(*merged, *args)


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def runtime(args: tuple[str, ...]) -> None:
    """Start the runtime only (sim + arena_node, no envs).

    Fails if another /arena node is already up. Attach envs afterwards
    with `arena env`.
    """
    _exec("ros2", "launch", "arena_bringup", "arena_runtime.launch.py", *args)


@main.command(name="env", context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def env_(args: tuple[str, ...]) -> None:
    """Attach one task-generator env to a running runtime.

    Waits forever (10s warning cadence) for /arena/register_env if the
    runtime is not up yet.
    """
    _exec("ros2", "launch", "task_generator", "task_generator.launch.py", *args)


main.add_command(_viz_mod.cmd)
main.add_command(_human_mod.cmd)
main.add_command(_robot_mod.cmd)


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def cam(args: tuple[str, ...]) -> None:
    """Control the simulator viewport camera."""
    _exec("ros2", "run", "arena_runtime", "cam", *args)


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("world")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def preload(world: str, args: tuple[str, ...]) -> None:
    """Preload a world's assets ahead of launch.

    `arena preload <world_name> [--no-scenarios] [-v]`.
    """
    _exec("ros2", "run", "arena_simulation_setup", "preload_world", world, *args)


@main.command()
@click.argument("env_id", type=click.IntRange(min=0))
def cleanup(env_id: int) -> None:
    """Tear down one env by id via /arena/cleanup_env."""
    _exec("ros2", "service", "call", "/arena/cleanup_env", "arena_runtime_msgs/srv/CleanupEnv", f"{{env_id: {env_id}}}")


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def build(args: tuple[str, ...]) -> None:
    """Build the workspace (or selected packages) with colcon.

    Bare package names are shorthand for --packages-select. The shell
    shim re-sources the environment afterwards.
    """
    from build import build_main

    sys.exit(build_main(_select_args(args)))


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED, required=True)
def rebuild(args: tuple[str, ...]) -> None:
    """Clean and rebuild selected packages.

    Accepts bare package names or colcon selection flags, e.g.
    `arena rebuild foo bar` or `arena rebuild --packages-select-regex 'arena_.*'`.
    """
    import shutil
    import subprocess

    argv = _select_args(args)
    listing = subprocess.run(
        ["colcon", "list", "--names-only", "--base-paths", os.path.join(_env("ARENA_WS_DIR"), "src"), *argv],
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode:
        raise click.ClickException("colcon list rejected the arguments, aborting before clean")
    pkgs = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    if not pkgs:
        raise click.ClickException("no packages matched")
    click.echo(f"arena rebuild: resolved {len(pkgs)} package(s): {' '.join(pkgs)}")
    for pkg in pkgs:
        for tree in (os.path.join("build", pkg), os.path.join("install", pkg)):
            if os.path.isdir(tree):
                click.echo(f"  rm -rf {tree}")
                shutil.rmtree(tree)
    click.echo("arena rebuild: clean done, invoking build")
    from build import build_main

    sys.exit(build_main(argv))


TEST_DEFAULT_SELECT = ("--packages-select-regex", "^arena_", "^task_generator$")


@main.command(
    context_settings=PASSTHROUGH | HELP_NAMES,
    help=f"Run colcon test and print a summary.\n\nDefaults to `{' '.join(TEST_DEFAULT_SELECT)}` unless a selection flag is given. Bare package names are shorthand for --packages-select.",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def test(args: tuple[str, ...]) -> None:
    import re
    import subprocess

    argv = _select_args(args)
    if not any(re.match(r"^--packages-(select|select-regex|up-to|above|ignore)", a) for a in argv):
        argv = [*TEST_DEFAULT_SELECT, *argv]
    listing = subprocess.run(
        ["colcon", "list", "--names-only", "--base-paths", os.path.join(_env("ARENA_WS_DIR"), "src"), *argv],
        capture_output=True,
        text=True,
        check=False,
    )
    pkgs = [line.strip() for line in listing.stdout.splitlines() if line.strip()] if listing.returncode == 0 else []
    test_rc = _run("colcon", "test", "--event-handlers", "console_direct+", *argv)
    from testsum import summarize

    summary = [os.path.join(_env("ARENA_WS_DIR"), "build")]
    if pkgs:
        summary += ["--packages", *pkgs]
    summary_rc = summarize(summary)
    sys.exit(test_rc or summary_rc)


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def deps(args: tuple[str, ...]) -> None:
    """Install ROS dependencies for the workspace via rosdep."""
    excludes = os.environ.get("ROSDEP_EXCLUDES", "libignition-gazebo6-dev gazebo_dev gazebo_ros gazebo_plugins gazebo_ros2_control flir_ptu_description")
    _exec("rosdep", "install", "--ignore-src", "-r", "-y", "--rosdistro", _env("ARENA_ROS_DISTRO"), "--from-paths", "src", "--skip-keys", excludes, *args)


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def update(args: tuple[str, ...]) -> None:
    """Pull the Arena repos and refresh the python env."""
    import subprocess

    from pull import pull_main

    rc = pull_main(list(args))
    probe = subprocess.run(["python", "-c", "import pip.__main__"], capture_output=True, check=False)
    if probe.returncode:
        subprocess.run(["python", "-m", "ensurepip", "--upgrade"], stdout=subprocess.DEVNULL, check=False)
    sys.exit(rc)


UNIVERSAL_VERBS = {
    "install": "Install the feature (pull repos, register, run its update).",
    "update": "Update the feature to the latest state.",
    "uninstall": "Uninstall and unregister the feature.",
    "launch": "Launch the feature's runtime component.",
}


def _feature_verb_command(feature_name: str, path: str, verb: str) -> click.Command:
    def callback(args: tuple[str, ...]) -> None:
        if verb in ("update", "launch") and not _reg_has(feature_name):
            raise click.ClickException(f"{feature_name} is not installed, run 'arena feature {feature_name} install' first")
        sys.exit(_feature_dispatch(feature_name, (verb, *args)))

    return click.Command(
        name=verb,
        params=[click.Argument(["args"], nargs=-1, type=click.UNPROCESSED)],
        callback=callback,
        help=UNIVERSAL_VERBS.get(verb, f"Forwarded to the {feature_name} feature script."),
        short_help=UNIVERSAL_VERBS.get(verb, f"forwarded to the {feature_name} script"),
        context_settings=PASSTHROUGH | HELP_NAMES,
    )


class FeatureSubGroup(click.Group):
    """One feature's verbs, unknown verbs are forwarded to its script."""

    def __init__(self, feature_name: str, path: str) -> None:
        super().__init__(
            name=feature_name,
            help=f"The {feature_name} feature.",
            short_help=_script_desc(path),
            no_args_is_help=True,
            context_settings=HELP_NAMES,
        )
        self.feature_name = feature_name
        self.path = path

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(UNIVERSAL_VERBS)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command:
        return _feature_verb_command(self.feature_name, self.path, cmd_name)

    def format_epilog(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        text = _script_help(self.path)
        if not text:
            return
        formatter.write_paragraph()
        formatter.write_text("Feature script help:")
        for line in text.splitlines():
            formatter.write(f"  {line}\n")


class FeatureGroup(click.Group):
    """Features discovered from ARENA_FEATURES_DIR as subcommands."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        try:
            entries = sorted(os.listdir(_env("ARENA_FEATURES_DIR")))
        except OSError:
            return []
        return [e for e in entries if _reg_resolve(e)]

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        path = _reg_resolve(cmd_name)
        if path is None:
            return None
        group = _features.load(cmd_name)
        if group is not None:
            return group
        return FeatureSubGroup(cmd_name, path)


@main.group(cls=FeatureGroup)
def feature() -> None:
    """Manage optional features.

    install, update, uninstall, and launch are common verbs. Any other
    verb is forwarded to the feature script, see each feature's help
    page for its full verb list.
    """


@main.group(cls=FeatureGroup, name="ft", hidden=True)
def ft() -> None:
    """Alias for feature."""


@main.command(context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def train(args: tuple[str, ...]) -> None:
    """Run DRL training (requires the training feature).

    `arena train train_config:=<yaml> [launch args]`.
    """
    sys.exit(_feature_dispatch("training", ("launch", *args)))


@main.command(hidden=True, context_settings=PASSTHROUGH | HELP_NAMES)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def evaluation(args: tuple[str, ...]) -> None:
    """Alias for feature evaluation."""
    sys.exit(_feature_dispatch("evaluation", args))


@main.command()
@click.argument("verb", type=click.Choice(["has", "require", "add", "remove", "list", "pull", "resolve"]))
@click.argument("name", required=False)
def registry(verb: str, name: str | None) -> None:
    """Query or mutate the installed-features registry."""
    if verb == "list":
        for n in _reg_list():
            click.echo(n)
        return
    if not name:
        raise click.ClickException(f"'registry {verb}' needs a feature name")
    if verb == "has":
        sys.exit(0 if _reg_has(name) else 1)
    elif verb == "require":
        if not _reg_has(name):
            click.echo(f"{name} is not installed; run 'arena feature {name} install' first.", err=True)
            sys.exit(1)
    elif verb == "add":
        _reg_add(name)
    elif verb == "remove":
        _reg_remove(name)
    elif verb == "pull":
        _reg_pull(name)
    elif verb == "resolve":
        path = _reg_resolve(name)
        if path is None:
            sys.exit(1)
        click.echo(path)


@main.command()
def deactivate() -> None:
    """Leave the arena environment."""
    raise click.ClickException("shell-level verb, handled by the arena shell function")


@main.command()
def repair() -> None:
    """Repair the python venv (in-container only)."""
    raise click.ClickException("shell-level verb, handled by the arena shell function")


@main.command()
def resource() -> None:
    """Re-source the arena environment."""
    raise click.ClickException("shell-level verb, handled by the arena shell function")
