import asyncio
import contextlib
import os
import re
import typing
from collections.abc import Callable

import arena_robots.SetupFile as robot_setup
import attrs
import rclpy
import task_generator_msgs.msg
from arena_rclpy_mixins.ROSParamServer import ROSParamT
from arena_rclpy_mixins.shared import Namespace
from arena_runtime._node import NodeInterface

from task_generator.manager.environment_manager import EnvironmentManager
from task_generator.shared import Pose, Position, Robot

from .robot_manager import RobotManager

_AUTO_TOKEN = "auto"
_ARENA_DEFAULT_ROBOT = "jackal"


@attrs.define(frozen=True)
class _Readiness:
    """Per-robot submodule readiness from the source-tree arena_robots/.gitmodules."""

    ready: frozenset[str]
    pending: dict[str, frozenset[str]]  # robot -> uninitialized submodule paths


_READINESS_CACHE: _Readiness | None = None


def _autoselect_dispatch() -> dict[str, str]:
    """Map mobile.kind -> ROS param key holding the planner name. Today only drl."""
    return {"drl": "robot.mobile.planner"}


def _robot_readiness() -> _Readiness | None:
    """Per-robot submodule readiness, or None when detection isn't possible
    (no git, no .gitmodules); callers treat None as "don't filter" so out-of-tree
    workflows still resolve. The robot -> submodule tags live in the SDK's
    arena_robots/.gitmodules with SDK-relative paths; we prefix arena_robots/ so
    they match the Arena-root-relative paths from `git submodule status --recursive`."""
    global _READINESS_CACHE
    if _READINESS_CACHE is not None:
        return _READINESS_CACHE
    import configparser  # noqa: PLC0415
    import pathlib  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    here = pathlib.Path(__file__).resolve()
    arena = next((p for p in here.parents if (p / "arena_robots").is_dir() and (p / ".gitmodules").is_file()), None)
    if arena is None:
        return None
    gitmodules = arena / "arena_robots" / ".gitmodules"
    if not gitmodules.is_file():
        return None
    status = subprocess.run(
        ["git", "submodule", "status", "--recursive"],
        cwd=arena,
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode != 0:
        return None
    uninit_paths = {line[1:].split()[1] for line in status.stdout.splitlines() if line.startswith("-")}
    cp = configparser.ConfigParser()
    cp.read(gitmodules)
    robot_to_paths: dict[str, set[str]] = {}
    for section in cp.sections():
        path = cp[section].get("path")
        robot = cp[section].get("robot")
        if not (path and robot):
            continue
        full_path = f"arena_robots/{path}"
        for name in robot.split():
            robot_to_paths.setdefault(name, set()).add(full_path)
    all_robots = {p.name for p in (arena / "arena_robots" / "arena_robots" / "robots").iterdir() if p.is_dir()}
    ready: set[str] = set()
    pending: dict[str, frozenset[str]] = {}
    for r in all_robots:
        missing = {p for p in robot_to_paths.get(r, ()) if p in uninit_paths}
        if missing:
            pending[r] = frozenset(missing)
        else:
            ready.add(r)
    _READINESS_CACHE = _Readiness(ready=frozenset(ready), pending=pending)
    return _READINESS_CACHE


def _ready_robot_names() -> frozenset[str] | None:
    """Robot names whose submodules are all initialized, or None when undetectable."""
    readiness = _robot_readiness()
    return readiness.ready if readiness is not None else None


def _initialpose_generator(x: float, y: float, d: float):
    """Generate initial poses for the robot.

    Args:
        x (float): The initial x position.
        y (float): The initial y position.
        d (float): The distance between poses.

    Yields:
        Pose: The initial pose for the robot.
    """
    while True:
        yield Pose(Position(x=x, y=y))
        y += d


@attrs.frozen
class _RobotDiff:
    """Change to robot configurations to execute."""

    to_remove: list[str] = attrs.field(factory=list)
    to_add: dict[str, Robot] = attrs.field(factory=dict)
    to_update: dict[str, Robot] = attrs.field(factory=dict)


class RobotsManager(NodeInterface):
    """Dynamically loads and manages multiple robots via ROS.

    Args:
        environment_manager (EnvironmentManager): The environment manager.
    """

    _initialpose: typing.Generator
    _robot_configurations: ROSParamT[_RobotDiff]
    _diff: _RobotDiff

    @property
    def managers(self) -> dict[str, RobotManager]:
        """Get the robot managers.

        Returns:
            dict[str, RobotManager]: The robot managers.
        """
        return self._managers

    @contextlib.contextmanager
    def provide_node_paths(self, paths: set[str]):
        """Context manager to provide node paths.

        Args:
            paths (set[str]): The set to populate with node paths.

        Yields:
            asyncio.Task: The task that populates the node paths.
        """
        t: asyncio.Task | None = None
        try:

            async def task():
                while True:
                    latest = self.node.get_node_names_and_namespaces()
                    paths.update(os.path.join(ns, name) for name, ns in latest)
                    await asyncio.sleep(1.0)

            t = asyncio.create_task(task())
            yield t
        except asyncio.CancelledError:
            pass
        except Exception:
            self._logger.error('Error while providing node paths {e}\n{traceback.format_exc()}')
        finally:
            if t and not t.done():
                t.cancel()

    def _resolve_auto(self) -> str:
        dispatch = _autoselect_dispatch()
        log = self.node.get_logger()

        mobile_kind = str(self.node.rosparam[str].get("robot.mobile_adapter", ""))
        if not mobile_kind or mobile_kind not in dispatch:
            log.warn(f"arena: auto-robot fallback={_ARENA_DEFAULT_ROBOT!r}: mobile_adapter={mobile_kind!r} not in dispatch {sorted(dispatch)}")
            return _ARENA_DEFAULT_ROBOT

        planner_param_key = dispatch[mobile_kind]
        planner_name = str(self.node.rosparam[str].get(planner_param_key, ""))
        if not planner_name:
            log.warn(f"arena: auto-robot fallback={_ARENA_DEFAULT_ROBOT!r}: {planner_param_key!r} is empty")
            return _ARENA_DEFAULT_ROBOT

        from arena_planners.resolver import load_manifest  # noqa: PLC0415

        manifest = load_manifest(planner_name)
        action_type: str | None = manifest.get("action_type")
        sensor_needs: list[str] = manifest.get("sensor_needs") or []

        if action_type is None:
            log.warn(f"arena: auto-robot fallback={_ARENA_DEFAULT_ROBOT!r}: planner={planner_name!r} manifest has no action_type")
            return _ARENA_DEFAULT_ROBOT

        want_holonomic = action_type == "omnidirectional"

        from arena_robots.Robot import RobotIdentifier  # noqa: PLC0415

        ready = _ready_robot_names()
        candidates: list[tuple[int, str]] = []
        for robot_id in RobotIdentifier.listall():
            name = robot_id.shortname
            if ready is not None and name not in ready:
                continue
            view = robot_id.resolve_sync()
            mobile = view.mobile
            if mobile is None:
                continue
            if mobile.is_holonomic != want_holonomic:
                continue
            robot_sensors = {s.type for s in view.model_params.sensors}
            if not set(sensor_needs) <= robot_sensors:
                continue
            candidates.append((-view.model_params.priority, name))

        if not candidates:
            log.warn(f"arena: auto-robot fallback={_ARENA_DEFAULT_ROBOT!r}: no robot matched action_type={action_type!r} sensor_needs={sensor_needs!r}")
            return _ARENA_DEFAULT_ROBOT

        candidates.sort(key=lambda t: (t[0], t[1]))
        chosen = candidates[0][1]
        log.info(f"arena: auto -> planner={planner_name!r} robot={chosen!r} [action_type={action_type!r}, sensor_needs={sensor_needs!r}]")
        return chosen

    def _parse_robot_configurations(self, v: object) -> _RobotDiff:
        """Parse robot configurations from the given value.

        Args:
            v (typing.Any): The value to parse.

        Raises:
            RuntimeError: If the parsing fails.

        Returns:
            _RobotDiff: The RobotDiff to execute.
        """

        robot_arg: list[str] = list(filter(len, str(v).split(',')))

        parsed_explicit: dict[str, Robot] = {}
        parsed_anonymous: dict[str, list[Robot]] = {}

        def add(base: robot_setup.Config):
            readiness = _robot_readiness()
            if readiness is not None and base.robot in readiness.pending:
                paths = ", ".join(sorted(readiness.pending[base.robot]))
                raise RuntimeError(f"robot {base.robot!r} is not installed (submodule(s) not checked out: {paths}). run: arena feature robots add {base.robot}")
            name = base.name
            config = Robot.from_setup(base, node=self.node)

            if name is None:  # anon
                parsed_anonymous.setdefault(config.model.name, []).append(config)

            else:  # explicit name
                if name in parsed_explicit:
                    raise RuntimeError(f'naming conflict for robots with name {name}')

                parsed_explicit[name] = config

        for arg in robot_arg:
            if arg.endswith('.yaml'):
                for addition in robot_setup.RobotSetupIdentifier(arg).resolve_sync():
                    add(addition)
            elif match := re.match(r'(.*)\[(\d+)\]', arg):
                # multi-instantiations via model[count]
                base = match.group(1)
                if base == _AUTO_TOKEN:
                    base = self._resolve_auto()
                for _ in range(int(match.group(2))):
                    add(robot_setup.Config(robot=base))
            else:
                resolved = self._resolve_auto() if arg == _AUTO_TOKEN else arg
                add(robot_setup.Config(robot=resolved))

        existing = {k: v.robot for k, v in self.managers.items()}

        existing_keys = set(existing.keys())
        matchable_keys = set(existing_keys)

        to_add: dict[str, Robot] = {}
        to_update: dict[str, Robot] = {}

        # explicit naming first
        for prefix, config in parsed_explicit.items():
            match = next((key for key in matchable_keys if existing[key] == config), None)

            if match is None:  # no matches
                to_add[prefix] = config
            else:  # exact match
                matchable_keys.remove(match)

        # anonymous naming
        for prefix, configs in parsed_anonymous.items():
            unassigned: list[Robot] = []

            for config in configs:
                match = next((key for key in matchable_keys if existing[key].compatible(config)), None)

                if match is None:  # no similar robot found
                    unassigned.append(config)
                else:  # similar robot found, update
                    to_update[match] = config
                    matchable_keys.remove(match)

            i: int = 0
            for anon in unassigned:
                suffixed_key = prefix

                if len(configs) > 1:
                    suffixed_key = f'{prefix}_{i}'

                while suffixed_key in existing_keys:
                    i += 1
                    suffixed_key = f'{prefix}_{i}'

                to_add[suffixed_key] = anon
                existing_keys.add(suffixed_key)

        self._diff = _RobotDiff(
            to_remove=list(matchable_keys),
            to_add=to_add,
            to_update=to_update,
        )
        return self._diff

    async def set_up(self):
        """Set up the robot managers."""
        futures: list[typing.Awaitable] = []
        for robot_name in self._diff.to_remove:
            futures.append(self.managers.pop(robot_name).destroy())
        self._diff.to_remove.clear()

        for robot_name in self._diff.to_update:
            futures.append(self.managers[robot_name].update())
            # TODO
        self._diff.to_update.clear()

        # Re-seed staging poses from the latest prespawn anchor; placement may
        # have changed since the previous reset.
        prespawn_x, prespawn_y = self.node._prespawn_offset
        self._initialpose = _initialpose_generator(prespawn_x, prespawn_y, -5)

        for robot_name, config in self._diff.to_add.items():
            config = attrs.evolve(config)
            config.name = robot_name
            config.pose = next(self._initialpose)
            manager = RobotManager(
                node=self.node,
                namespace=Namespace(self.node.get_namespace())(
                    self.node.get_name(),
                ),
                environment_manager=self._environment_manager,
                robot=config,
            )
            if self._abort_episode is not None:
                manager.bind_abort(self._abort_episode)
            futures.append(manager.set_up_robot())
            self.managers[robot_name] = manager
            self._pending_launch.append(manager)

        await asyncio.gather(*futures)
        self._diff.to_add.clear()

        self.node.rosparam[list[str]].set('robot_names', [robot.name for robot in self.managers.values()])

        fleet = task_generator_msgs.msg.RobotFleet(
            robots=[
                task_generator_msgs.msg.RobotDescriptor(
                    name=mgr.name,
                    model=mgr.model_name,
                    ns=str(mgr.namespace),
                    frame=mgr.frame.raw().lstrip("/"),
                )
                for mgr in self.managers.values()
            ]
        )
        self.node._pub_state_robots.publish(fleet)

    def bind_abort(self, fn: Callable[[str], None]) -> None:
        """Propagate an abort callable to all current and future RobotManagers."""
        self._abort_episode = fn
        for mgr in self._managers.values():
            mgr.bind_abort(fn)

    def __init__(self, *args: object, environment_manager: EnvironmentManager, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._environment_manager: EnvironmentManager = environment_manager
        self._managers: dict[str, RobotManager] = {}
        self._initialpose = _initialpose_generator(0.0, 0.0, -5)
        self._diff = _RobotDiff()
        self._pending_launch: list[RobotManager] = []
        self._abort_episode: Callable[[str], None] | None = None

        self._robot_configurations = self.node.ROSParam[_RobotDiff](
            'robot',
            type_=rclpy.Parameter.Type.STRING,
            parse=self._parse_robot_configurations,
        )

    async def launch_pending(self) -> None:
        """Bring up navstacks for managers queued by set_up. Caller controls when this fires
        so LaunchService.run_async()'s main-loop block doesn't starve concurrent work
        (e.g. spawn_world_obstacles)."""
        if not self._pending_launch:
            return
        pending = self._pending_launch
        self._pending_launch = []
        node_paths: set[str] = set()
        with self.provide_node_paths(node_paths) as fetch_task:
            await asyncio.wait(
                (
                    fetch_task,
                    asyncio.gather(*(m.launch(node_paths) for m in pending)),
                ),
                return_when=asyncio.FIRST_COMPLETED,
            )

    def add_pending(self, name: str, robot: Robot) -> None:
        """Queue a robot for full set_up_robot on the next reset_cycle."""
        if name in self._managers or name in self._diff.to_add:
            raise ValueError(f"robot {name!r} already exists")
        self._diff.to_add[name] = robot
