# Benchmark Refactor: TM_Module → arena_evaluation runner

> This file captures the v1 design plan. For current operator docs see
> `arena_evaluation/configs/benchmark/README.md`.

## Context

`Mod_Benchmark` is a `TM_Module` inside the long-lived `task_generator_node` process. It steps through a (suite × contest) grid by mutating ROS params (`Arena.WORLD`, `TM_ROBOTS`, `TM_OBSTACLES`, `task.scenario.file`) on the live node and forcing resets. This is broken in three ways:

1. Mid-process world swaps don't reliably re-init the simulator.
2. The contest loop (per-planner config) is dead code — different planners need the nav stack relaunched, not just params swapped.
3. The `robot` field on the stage schema is parsed but never reapplied.

`arena_runtime` now exposes `/arena/spawn_env` and `/arena/despawn_env`, with the slot packer making concurrent envs safe and clean. Each `(stage × contestant)` cell becomes one fresh `spawn_env(launch_args=…)`, runs N episodes with the right config from the start, then despawns. Concurrency is capped by `env_n` (same arg name as `arena launch`).

**Outcome:** delete `Mod_Benchmark` (~485 lines of half-broken code), gain a real benchmark loop with working contest iteration, optional parallelism, and reuse of `arena_evaluation`'s recording/metrics pipeline downstream.

## Architecture

```
arena benchmark <args>
  → ros2 launch arena_evaluation benchmark.launch.py
       includes arena.launch.py with env_n:=0   (no auto-fleet)
       runs benchmark_runner_node               (the new orchestrator)

benchmark_runner_node (AsyncNode, in arena_evaluation):
  - loads suites/<name>.yaml, contests/<name>.yaml from arena_evaluation/configs/benchmark/
  - builds Cartesian grid of cells = (contestant × stage)
  - reads env_n / headless as CLI flags (passed from benchmark.launch.py)
  - subscribes to /arena/state/envs (TRANSIENT_LOCAL)
  - for each cell:
      1. /arena/spawn_env with stage-only launch args (no contestant fields);
         robot:= suppresses default autospawn; episodes:=N is the safety-net bound.
      2. resolves env namespace from EnvRecord.fqn on /arena/state/envs.
      3. <env_ns>/runtime/spawn_robot (SpawnRobot) with model=stage.robot and
         args=contestant.args as diagnostic_msgs/KeyValue[]; forwarded to Robot.parse.
      4. drives cell.episodes goals via RunEpisode action at
         <env_ns>/lifecycle/run_episode; per-episode EpisodeRecord rows from
         <env_ns>/state/episode are appended to progress.csv.
      5. /arena/despawn_env, frees slot.
  - persists progress to <run>/.benchmark_state.json + progress.csv after each cell
  - exits 0/1/2/130 depending on outcome

task_generator side:
  - DESIRED_EPISODES (ROS param `episodes`) is the safety-net: the env self-shuts
    down after N episodes if the runner crashes.
  - launch-arg passthroughs added: episodes, scenario_file, agent_name.
```

## Critical files

- `task_generator/launch/task_generator.launch.py` — add 3 launch args; append a SECOND parameters dict after `parameter_file.substitution` so overrides win
- `task_generator/task_generator/tasks/modules/benchmark/` — DELETE entire dir
- `task_generator/task_generator/tasks/modules/__init__.py` — drop benchmark import/`__all__` entry
- `task_generator/task_generator/constants/__init__.py:58` — drop `BENCHMARK = "benchmark"` enum
- `task_generator/tests/ros/test_benchmark_parse.py` — DELETE (moved)
- `task_generator/tests/ros/test_constants.py:108` — drop the `BENCHMARK` enum assertion
- `task_generator/tests/ros/test_tasks_registry.py:36` — drop `BENCHMARK in registry_module` assertion
- `arena_bringup/configs/benchmark/` — MOVE to `arena_evaluation/configs/benchmark/`
- `arena_evaluation/arena_evaluation/setup.py` — add data_files for configs, console script for `benchmark`
- `arena_evaluation/arena_evaluation/package.xml` — add deps (`arena_runtime_msgs`, `task_generator`)
- `arena_evaluation/arena_evaluation/arena_evaluation/benchmark/` — NEW package
- `arena_evaluation/arena_evaluation/launch/benchmark.launch.py` — NEW launch
- `arena_evaluation/arena_evaluation/test/test_benchmark_parse.py` — moved + reimported
- `_meta/tools/source` — add `benchmark)` case in `arena()` dispatch

## Run directory layout

Default root: `share/arena_evaluation/data/<run_id>/`. Override via `--data-root <path>`.

`<run_id>` defaults to `YYYYMMDD-HHMMSS-<short_git_sha>` (e.g. `20260503-153012-bfbe92c`); `--run-id <name>` overrides; `--resume <name>` reopens an existing one.

```
<data-root>/<run_id>/
├── manifest.yaml              # run-start snapshot, never overwritten (see fields below)
├── progress.csv               # append-only, one row per completed cell
├── runner.log                 # rclpy file-logger handler, tail -F friendly
├── .benchmark_state.json      # machine-readable resume state, atomic write
└── <contestant>/<stage>/<robot>/   # recorder output (CSVs, params.yaml)
```

`record_data_dir:=<run_id>/<contestant>/<stage>` is the per-cell launch arg passed to spawn_env. The data_recorder appends the robot subdir as it does today, giving the 3-level nesting `process_data.py` already walks.

**`manifest.yaml` fields:**

```yaml
run_id: 20260503-153012-bfbe92c
created_at: '2026-05-03T15:30:12+00:00'
arena_git:
  sha: bfbe92c...
  dirty: false                   # true if working tree had uncommitted changes
cli_args: [--suite, meta_suite, --contest, basic, --env-n, 4]
env_n: 4
headless_mode: 0
simulator: gazebo
scale_episodes: 1.0
config_hash: <sha1 of (suite_yaml + contest_yaml)>
suite_yaml: "..."
contest_yaml: "..."
cells:                            # resolved cartesian product, post scale_episodes
  - key: teb/map_empty_1_jackal
    contestant: { name: teb, args: {local_planner: teb} }
    stage:      { name: map_empty_1_jackal, episodes: 5, robot: jackal, ... }
    episodes_planned: 5
  - ...
```

**`progress.csv` schema** (header line written atomically with first row):

```
ts_iso,run_id,cell_key,contestant,stage,env_id,episode_id,world,seed,
tm_robots,tm_obstacles,tm_modules,robots,outcome_state,outcome_reason,
started_at,ended_at,runtime_s,robots_params_json,obstacles_params_json
```

One row per episode (pulled from EpisodeRecord on `<env_ns>/state/episode`).
Append-only; never rewritten.

**`.benchmark_state.json` schema:**

```json
{
  "run_id": "...",
  "config_hash": "...",
  "started_at": 1714710000.0,
  "cells": {
    "<contestant>/<stage>": {
      "status": "ok|failed|skipped|in_progress",
      "env_id": 3,
      "started_at": 1714710012.0,
      "ended_at": 1714710148.0,
      "error": null
    }
  }
}
```

Atomic write: write-to-tmp + os.replace, after every cell completion or status transition. A kill mid-cell leaves the cell as `in_progress` so resume retries it.

## Resume semantics

`arena benchmark --resume <run_id>` reopens `<data-root>/<run_id>/`:

1. Read `manifest.yaml` and `.benchmark_state.json`.
2. Compute current `config_hash`. If it differs from manifest's: refuse with a clear error unless `--force` is passed.
3. Build the pending list:
   - cells with `status: ok` → skip (silent).
   - cells with `status: failed` → skip by default (already attempted); add `--retry-failed` to redo.
   - cells with `status: in_progress` → retry (never finished).
   - cells absent from state → run.
4. Append a `# resumed at <ts>` marker comment to `progress.csv`, continue appending rows.
5. `runner.log` is appended to (not truncated).

## Reused utilities (do NOT reimplement)

- `arena_rclpy_mixins.AsyncNode` — node + asyncio loop
- `arena_rclpy_mixins.Async.ClientWrapper` — `call_timeout()`, `ensure()`
- `arena_rclpy_mixins.Async.await_ros` — ROS Future → asyncio Future
- `arena_runtime_msgs.srv.SpawnEnv`, `DespawnEnv`
- `arena_runtime_msgs.msg.EnvRegistry`, `EnvRecord`
- `task_generator/task_generator/constants/runtime.py:53` — `DESIRED_EPISODES` (param `episodes`) already self-shutdowns the env at count
- `task_generator/task_generator/constants/runtime.py:92` — `agent_name` ROS param (already read)
- `task_generator/task_generator/tasks/obstacles/scenario/impl.py:27` — `task.scenario.file` ROS param (already read)

## Step-by-step implementation

Each step is independent enough that one agent can execute it cold. Run in order.

### Step 1 — Add launch-arg passthroughs in task_generator (no runtime code change)

**File:** `task_generator/launch/task_generator.launch.py`

After the existing `task_config` LaunchArgument block (around line 125), add three new args:

```python
episodes = LaunchArgument(
    name='episodes',
    default_value='-1',
    description='Stop the env after N episodes (-1 = run forever).',
)
scenario_file = LaunchArgument(
    name='scenario_file',
    default_value='',
    description='Sets task.scenario.file ROS param (empty = use parameter_file default).',
)
agent_name = LaunchArgument(
    name='agent_name',
    default_value='',
    description='RL agent name; sets agent_name ROS param.',
)
```

**Critical: parameter ordering.** `parameter_file` (the YAML at `arena_bringup/configs/task_generator.yaml`) sets `task.scenario.file: default`. ROS 2 applies entries in `parameters=[...]` in order, last wins. So append the new overrides **as a second dict AFTER `parameter_file.substitution`** in the existing parameters list (around line 235-257):

```python
parameters=[
    { ... existing dict (use_sim_time, sim, robot, tm_robots, ...) ... },
    parameter_file.substitution,
    {                                                       # NEW dict, appended LAST
        **episodes.param(float),                            # → ROS param "episodes"
        'task.scenario.file': scenario_file.substitution,   # empty string is harmless
        **agent_name.str_param,                             # → ROS param "agent_name"
    },
],
```

Don't touch the existing dict's contents or the existing `parameter_file.substitution` position. The new dict-after-yaml is the entire mechanism.

Add `episodes`, `scenario_file`, `agent_name` to the LaunchDescription's `declare_arguments` list at the bottom of the file.

**Verification:** `ros2 launch task_generator task_generator.launch.py --show-args` lists the three new args. Spawn with `scenario_file:=foo` and inspect via `ros2 param get <ns>/task_generator_node task.scenario.file` → returns `foo`, not `default`.

### Step 2 — Move benchmark configs

```bash
git mv arena_bringup/configs/benchmark arena_evaluation/configs/benchmark
```

Update **all** references to the old path:

- `arena_bringup/configs/benchmark/README.md` — content moves with the dir; rewrite intro to point at `arena benchmark` flow (delete mentions of `tm_modules: [benchmark]`).
- Anywhere in `arena_bringup/launch/` that references `configs/benchmark/` → grep first, update.

### Step 3 — Move parsing classes; create runner package

Create `arena_evaluation/arena_evaluation/arena_evaluation/benchmark/`:

```
benchmark/
    __init__.py
    config.py        # _Config, Suite, Contest (parsing) — moved from impl.py
    cell.py          # Cell, CellResult dataclasses
    state.py         # .benchmark_state.json + progress.csv + manifest.yaml I/O
    runner.py        # BenchmarkRunner async class + cli_main()
```

**`config.py`** — copy `_Config`, `Suite`, `Contest` (NamedTuples + their `.parse()` classmethods + `_make_serializable` + `hash`) from `task_generator/task_generator/tasks/modules/benchmark/impl.py:20-174`. Replace the `Constants.TaskMode.TM_Robots`/`TM_Obstacles` imports with their canonical location: `from task_generator.constants import Constants` (keep this dep — only used at parse time, not runtime). Keep enum-resolution logic as-is.

**`cell.py`** —

```python
import attrs, pathlib, typing
from .config import Suite, Contest

@attrs.frozen
class Cell:
    contestant: Contest.Contestant
    stage: Suite.Stage
    episodes: int                         # stage.episodes * scale_episodes
    record_dir: pathlib.Path | None       # None = recording disabled

    @property
    def key(self) -> str:
        return f"{self.contestant.name}/{self.stage.name}"

@attrs.frozen
class CellResult:
    key: str
    status: typing.Literal["ok", "failed", "skipped", "in_progress"]
    env_id: int | None
    started_at: float
    ended_at: float | None
    error: str | None
```

**`state.py`** — owns `<run_id>/`:

- `RunDir.create(data_root, run_id, manifest)` — mkdir, write `manifest.yaml`, init empty `.benchmark_state.json`, attach `runner.log` file handler to the rclpy logger.
- `RunDir.open(data_root, run_id)` — for `--resume`. Read manifest + state.
- `StateFile` — atomic write of `.benchmark_state.json` (write-tmp + os.replace).
- `ProgressLog` — append-only CSV writer with the schema above. `append(result)` after each cell.
- Manifest dataclass — knows how to compute `config_hash = sha1(config_yaml_text + suite_yaml_text + contest_yaml_text)`, capture git sha via `subprocess.run(['git', '-C', workspace, 'rev-parse', 'HEAD'])` (best-effort; tolerate non-git environments by storing `null`).

**`runner.py`** — see spec below.

### Step 4 — Implement `BenchmarkRunner` (`runner.py`)

```python
import asyncio, hashlib, json, os, pathlib, signal, time, typing
import rclpy
from arena_rclpy_mixins import AsyncNode
from arena_rclpy_mixins.Async import ClientWrapper
from arena_runtime_msgs.srv import SpawnEnv, DespawnEnv
from arena_runtime_msgs.msg import EnvRegistry
from rclpy.qos import QoSDurabilityPolicy, QoSProfile, QoSReliabilityPolicy

from .config import _Config, Suite, Contest
from .cell import Cell, CellResult
from .state import StateFile

_LATCHED = QoSProfile(
    depth=1,
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
)

class BenchmarkRunner(AsyncNode):
    def __init__(self, config: _Config, suite: Suite, contest: Contest,
                 *, env_n: int, run_id: str, headless_mode: int,
                 state: StateFile):
        super().__init__("arena_benchmark_runner")
        self._config, self._suite, self._contest = config, suite, contest
        self._env_n = env_n
        self._run_id = run_id
        self._headless_mode = headless_mode  # -1/0/1/2, arena.launch.py convention
        self._state = state

        self._spawn = self.create_client_wrapper(SpawnEnv, "/arena/spawn_env")
        self._despawn = self.create_client_wrapper(DespawnEnv, "/arena/despawn_env")
        self._env_records: dict[int, "EnvRecord"] = {}
        self._env_gone_events: dict[int, asyncio.Event] = {}
        self.create_subscription(
            EnvRegistry, "/arena/state/envs", self._on_envs, _LATCHED)

    # build cells: contestants × stages, in stable order; drop ones already "ok"
    def _build_pending(self) -> list[Cell]: ...

    def _on_envs(self, msg: EnvRegistry) -> None:
        new_ids = {e.env_id for e in msg.envs}
        # set events for any env_id we were waiting on but is now gone
        for env_id in list(self._env_gone_events):
            if env_id not in new_ids:
                self._env_gone_events[env_id].set()
        self._env_records = {e.env_id: e for e in msg.envs}

    def _build_launch_args(self, cell: Cell) -> list[str]:
        s = cell.stage
        scenario_raw = (s.config.get("SCENARIO") or {}).get("file", "")
        scenario = pathlib.Path(str(scenario_raw)).stem if scenario_raw else ""
        args = [
            f"sim:={self._simulator}",
            "robot:=",                             # suppress default autospawn
            f"world:={s.map}",
            f"tm_robots:={s.tm_robots.value}",
            f"tm_obstacles:={s.tm_obstacles.value}",
            f"scenario_file:={scenario}",
            f"episodes:={cell.episodes}",          # safety-net upper bound
            f"run_seed:={s.seed}",
            "auto_reset:=false",
            "tm_modules:=",                        # explicit empty
        ]
        if cell.record_dir is not None:
            args.append(f"record_data_dir:={cell.record_dir}")
        return args
        # Contestant args (local_planner, inter_planner, etc.) are NOT in launch_args.
        # They go to Robot.parse via SpawnRobot.args (KeyValue[]).

    def _per_spawn_headless(self, env_index: int) -> bool:
        # Mirror arena_node._spawn_initial_envs convention exactly.
        # headless mode: -1 = show all, 0 = show env 0, 1 = rviz only on env 0,
        # 2 = hide all. env_index is the slot 0..env_n-1, NOT the SpawnEnv-assigned env_id.
        m = self._headless_mode
        return bool(m > 1) if env_index == 0 else bool(m > -1)

    async def _wait_env_gone(self, env_id: int, *, timeout: float | None) -> bool:
        ev = asyncio.Event()
        self._env_gone_events[env_id] = ev
        try:
            if env_id not in self._env_records:
                return True
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._env_gone_events.pop(env_id, None)

    async def _run_cell(self, cell: Cell) -> CellResult:
        started = time.time()
        env_id: int | None = None
        try:
            req = SpawnEnv.Request(
                ns="",
                headless=self._per_spawn_headless(slot_index),  # slot_index passed in by run()
                launch_args=self._build_launch_args(cell),
            )
            resp = await self._spawn.call_timeout(req, timeout_sec=300.0)
            if resp is None or not resp.success:
                msg = resp.error_msg if resp else "spawn timeout"
                return CellResult(cell.key, "failed", None, started, time.time(), msg)
            env_id = resp.env_id
            # Cell finishes when the env's lifecycle exits and arena_node drops it
            # from /arena/state/envs (driven by DESIRED_EPISODES self-shutdown).
            timeout = max(60.0, cell.episodes * float(cell.stage.timeout) * 1.5)
            ok = await self._wait_env_gone(env_id, timeout=timeout)
            if not ok:
                return CellResult(cell.key, "failed", env_id, started, time.time(),
                                  "cell timeout")
            return CellResult(cell.key, "ok", env_id, started, time.time(), None)
        except asyncio.CancelledError:
            return CellResult(cell.key, "skipped", env_id, started, time.time(),
                              "cancelled")
        except Exception as e:
            return CellResult(cell.key, "failed", env_id, started, time.time(), repr(e))
        finally:
            if env_id is not None and env_id in self._env_records:
                with contextlib.suppress(Exception):
                    await self._despawn.call_timeout(
                        DespawnEnv.Request(env_id=env_id), timeout_sec=30.0)
                with contextlib.suppress(asyncio.TimeoutError):
                    await self._wait_env_gone(env_id, timeout=30.0)

    async def run(self) -> int:
        await self._spawn.ensure(timeout_sec=15.0)
        await self._despawn.ensure(timeout_sec=15.0)
        pending = self._build_pending()
        in_flight: set[asyncio.Task] = set()
        results: dict[str, CellResult] = dict(self._state.cells)

        cap = max(1, min(self._env_n, len(pending) or 1))
        # Track which slot index each in-flight task occupies (0..cap-1)
        # so headless mapping is stable across the run. Free slots are reused.
        free_slots: list[int] = list(range(cap))
        try:
            while pending or in_flight:
                while pending and len(in_flight) < cap:
                    cell = pending.pop(0)
                    slot = free_slots.pop(0)  # smallest free slot wins env_index 0
                    results[cell.key] = CellResult(
                        cell.key, "in_progress", None, time.time(), None, None)
                    self._state.write(results)
                    task = asyncio.create_task(
                        self._run_cell(cell, slot_index=slot), name=cell.key)
                    task.add_done_callback(lambda _t, s=slot: free_slots.append(s))
                    in_flight.add(task)
                if not in_flight:
                    break
                done, in_flight = await asyncio.wait(
                    in_flight, return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    res: CellResult = t.result()
                    results[res.key] = res
                    self._state.write(results)
                    self.get_logger().info(
                        f"[{res.status}] {res.key} env={res.env_id} "
                        f"t={(res.ended_at or 0)-res.started_at:.1f}s")
        except asyncio.CancelledError:
            for t in in_flight:
                t.cancel()
            await asyncio.gather(*in_flight, return_exceptions=True)
            raise
        return 0 if all(r.status == "ok" for r in results.values()) else 1

def cli_main(argv: list[str] | None = None) -> int:
    import argparse, sys
    p = argparse.ArgumentParser(prog="benchmark")
    # Most knobs come from ROS launch args (env_n:=, headless:=, ...) read off
    # node parameters set by benchmark.launch.py. The CLI args below are only
    # the things that don't fit the launch-arg model (config path, resume).
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--run-id", default=None,
                   help="default: YYYYMMDD-HHMMSS-<short_git_sha>")
    p.add_argument("--data-root", default=None,
                   help="default: share/arena_evaluation/data/")
    p.add_argument("--resume", default=None, help="run-id of a prior run to resume")
    p.add_argument("--retry-failed", action="store_true",
                   help="when resuming, also retry cells with status=failed")
    p.add_argument("--force", action="store_true",
                   help="when resuming, allow config_hash mismatch")
    args = p.parse_args(argv)
    rclpy.init()
    try:
        # load configs from configs_dir = share/arena_evaluation/configs/benchmark/
        config, suite, contest = _load_all(args.config)
        run_id = args.resume or args.run_id or f"t{int(time.time())}"
        state = StateFile.open(run_id, config_hash=_hash(config, suite, contest),
                               resume=args.resume is not None)
        runner = BenchmarkRunner(
            config=config, suite=suite, contest=contest,
            benchmark_n=args.n, run_id=run_id, headless=args.headless, state=state)
        try:
            return asyncio.run(runner.run())
        except KeyboardInterrupt:
            return 130
    except SystemExit as e:
        return int(e.code or 0)
    except Exception as e:
        print(f"benchmark: {e}", file=sys.stderr)
        return 2
    finally:
        rclpy.try_shutdown()
```

`_load_all`, `_hash`, and `StateFile.open` are small helpers in `state.py` / a `loader.py` — straightforward, follow the existing `Mod_Benchmark._load_config/_load_suite/_load_contest` pattern.

**Stage timeout parsing** — `Suite.Stage.timeout` accepts either a numeric string (`"60"`, `"60.0"`) or a duration string (`"5m"`, `"1h30m"`, `"500ms"`). Implement a small helper in `config.py`:

```python
_DUR_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(ms|s|m|h)?')
def _parse_duration(s: str) -> float:
    """Returns seconds. Plain numbers parsed as seconds. Suffix-form sums all units."""
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    total = 0.0
    for n, unit in _DUR_RE.findall(s):
        total += float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "": 1}[unit]
    if total == 0:
        raise ValueError(f"unparseable duration: {s!r}")
    return total
```

Used both in `_run_cell`'s timeout calculation and at parse time to validate Stage.timeout fields.

### Step 5 — Launch + console-script + CLI plumbing

**`arena_evaluation/arena_evaluation/launch/benchmark.launch.py`** — new file. Mirror `arena_training/launch/training.launch.py`. Reuse `arena.launch.py`'s `headless` arg semantics (int -1/0/1/2) and `env_n` arg name. The launch file always includes `arena.launch.py` with `env_n:=0` (so arena_node does not auto-spawn) but **passes the user-provided `env_n` through to the runner script as `--env-n`** — the runner reads it as the parallelism cap.

```python
import launch
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            ExecuteProcess, Shutdown)
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from launch.launch_description_sources import PythonLaunchDescriptionSource

def generate_launch_description():
    config = LaunchConfiguration('config')
    env_n = LaunchConfiguration('env_n')
    headless = LaunchConfiguration('headless')

    arena = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare('arena_bringup'), 'launch', 'arena.launch.py'])),
        # Always 0 here so arena_node does not pre-spawn; the runner spawns.
        # `headless` IS forwarded so the simulator-window decision matches.
        launch_arguments={'env_n': '0', 'headless': headless}.items(),
    )
    runner = ExecuteProcess(
        cmd=['ros2', 'run', 'arena_evaluation', 'benchmark',
             '--config', config,
             '--env-n', env_n,
             '--headless-mode', headless],
        output='screen',
        on_exit=Shutdown(reason='benchmark finished'),
    )
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value='config.yaml'),
        DeclareLaunchArgument('env_n', default_value='1',
                              description='Parallel cells in flight; same name as arena.launch.py.'),
        DeclareLaunchArgument('headless', default_value='0',
                              description='-1=show all envs, 0=show env 0, 1=rviz only, 2=hide all.'),
        arena, runner,
    ])
```

CLI flags `--env-n` and `--headless-mode` are added to `cli_main` parser (alongside `--config`/`--run-id`/etc.). Resume flow uses `--resume <run_id>` directly via `arena benchmark`, not via the launch file.

**`arena_evaluation/arena_evaluation/setup.py`** — add to `entry_points['console_scripts']`:

```python
'benchmark = arena_evaluation.benchmark.runner:cli_main',
```

Add to `data_files`:

```python
(os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
(os.path.join('share', package_name, 'configs', 'benchmark'),
   glob('configs/benchmark/*.yaml')),
(os.path.join('share', package_name, 'configs', 'benchmark', 'suites'),
   glob('configs/benchmark/suites/*.yaml')),
(os.path.join('share', package_name, 'configs', 'benchmark', 'contests'),
   glob('configs/benchmark/contests/*.yaml')),
```

**`arena_evaluation/arena_evaluation/package.xml`** — add:

```xml
<exec_depend>arena_runtime_msgs</exec_depend>
<exec_depend>arena_rclpy_mixins</exec_depend>
<exec_depend>task_generator</exec_depend>
<exec_depend>arena_bringup</exec_depend>
```

**`_meta/tools/source`** — in the `arena()` function, after the `train)` case block (~line 389):

```bash
benchmark)
    ros2 launch arena_evaluation benchmark.launch.py "$@"
    result=$?
;;
```

Update the help/usage line below to include `benchmark`.

### Step 6 — Delete `Mod_Benchmark`

```bash
rm -rf task_generator/task_generator/tasks/modules/benchmark/
```

Edit **`task_generator/task_generator/tasks/modules/__init__.py`** — remove the line `from . import benchmark` (line 5) and any `benchmark` entry in `__all__` if present.

Edit **`task_generator/task_generator/constants/__init__.py:58`** — delete the line `BENCHMARK = "benchmark"` from the `TM_Module` enum.

Edit **`task_generator/task_generator/constants/README.md`** — remove the `benchmark` row from the TM_Module table.

Edit **`task_generator/task_generator/tasks/modules/README.md`** — drop the `benchmark` row from the table and the "Drives a multi-stage benchmark" section.

Edit **`task_generator/tests/ros/test_constants.py`** — delete line 108 (`assert TM.BENCHMARK.value == "benchmark"`).

Edit **`task_generator/tests/ros/test_tasks_registry.py`** — delete line 36 (`assert Constants.TaskMode.TM_Module.BENCHMARK in _TaskRegistry.registry_module`).

### Step 7 — Move parsing tests

```bash
git mv task_generator/tests/ros/test_benchmark_parse.py \
       arena_evaluation/arena_evaluation/test/test_benchmark_parse.py
```

Update imports in the moved file:
- `from task_generator.tasks.modules.benchmark.impl import _Config, Suite, Contest`
  → `from arena_evaluation.benchmark.config import _Config, Suite, Contest`
- Anything else from `task_generator.constants` stays as-is (still imported for `Constants.TaskMode.TM_Robots/TM_Obstacles` enums).

### Step 8 — Documentation

Update **`arena_evaluation/configs/benchmark/README.md`** (the moved file):
- Replace "`Mod_Benchmark` reads…" intro with: "The benchmark runner (`arena benchmark`) reads…"
- Drop the "How `Mod_Benchmark` ingests these files" section (lines 100-117 in the original); replace with a short "How the runner consumes these files" section describing the spawn/despawn loop.

Update **`CLAUDE.md`** if it references benchmark as a TM_Module (search "benchmark" in the file).

Update **`arena_bringup/configs/benchmark/`** references in any README — the dir no longer exists at that path.

Update **`arena_bringup/configs/tasks/README.md`** if it lists `benchmark` as a tm_module — drop it.

### Step 9 — Smoke tests (no actual sim work)

A pure-Python test that exercises the runner without running real envs. Put in `arena_evaluation/arena_evaluation/test/test_benchmark_runner.py`. Per memory rule "no mocking in tests": skip what can't be tested without mocks. Test only:

- `_build_launch_args` snapshot test against a known cell (pure function, no ROS).
- `StateFile` roundtrip: write → read → equality.
- `_build_pending` correctly drops cells whose state is `"ok"`.
- `Cell.key` collision detection at parse time.

The actual end-to-end (`arena benchmark suite:=basic contest:=basic sim:=dummy` against `dummy` sim) is a manual verification step, not a test.

## Future / out-of-scope

- **Recorder topic-namespace fix**: `/scenario_reset` global vs `<ns>/task_reset` mismatch. Benchmark output CSVs may have wrong per-episode segmentation; aggregate runs are usable.
- **`tm_modules` syntax extension**: `:=`/`:=+`/`:=-` (set / add / remove from default) is a planned later refactor. The runner currently sends `tm_modules:=` (replace whole list, default empty).
- **Heartbeat-eviction false positives**: Resume flow covers the rare miss.
- **Env reuse across contestants on the same stage** saves one world load per contestant. Requires either a `despawn_robot` service or an `update_robots` service that takes a target fleet description and computes a diff (RobotDiff) against current state, adding/removing robots accordingly. The latter is more declarative.
- **Re-enable ROS-skipped tests** (`_build_launch_args` / `_build_pending` / `_per_spawn_headless` snapshot tests) by extracting them to free functions so they can be exercised without a ROS init.

## Pre-existing recorder bug (out of scope, document only)

`arena_evaluation/arena_evaluation/arena_evaluation/data_recorder_node.py:218,439` subscribes to absolute `/scenario_reset`, but `task_generator/task_generator/node.py:188-190` publishes to `<ns>/task_reset`. The recorder's episode segmentation is broken even single-env. **Not addressed in this refactor.** Add a known-issue note in the moved README and file separately.

Implication for `benchmark_n > 1`: parallel envs would also cross-talk on whatever `/scenario_reset` publisher is bridged in (if any). v1 default is `benchmark_n=1` (clean) but `>1` is permitted with a runner log warning, since the cross-talk is pre-existing, not a regression.

## Verification

1. **Static**: `ruff check` clean across the touched packages.
2. **Build**: `colcon build --packages-select arena_evaluation task_generator arena_bringup` succeeds.
3. **Move sanity**: `ros2 pkg prefix arena_evaluation` then check `share/arena_evaluation/configs/benchmark/{config,suites,contests}/` are populated and `share/arena_evaluation/launch/benchmark.launch.py` exists.
4. **Launch args**: `ros2 launch task_generator task_generator.launch.py --show-args` lists `episodes`, `scenario_file`, `agent_name`.
5. **Parse tests**: `colcon test --packages-select arena_evaluation` runs the moved `test_benchmark_parse.py` green; `colcon test --packages-select task_generator` no longer references benchmark.
6. **scenario_file override**: spawn one env via `arena benchmark` with a stage that sets `SCENARIO.file: 4.json`. Verify `ros2 param get <ns>/task_generator_node task.scenario.file` returns `4` (stripped, and the launch-arg override beats the YAML default `default`).
7. **Single-cell smoke (manual)**: `source arena -c 'arena benchmark suite:=basic contest:=basic sim:=dummy'`. Expect: one env spawns, robot is spawned via SpawnRobot, episodes run, env despawns, runner exits 0. State file at `share/arena_evaluation/data/<run_id>/.benchmark_state.json` shows `"status": "ok"` for the cell.
8. **Resume (manual)**: kill the runner mid-run; rerun with `arena benchmark --resume <run_id>`. Pending cells continue, completed cells skip, `progress.csv` continues to grow.
9. **Parallel smoke (manual, optional)**: `arena benchmark env_n:=2 sim:=dummy`. Expect 2 in-flight envs, slot packer places them non-overlapping; with `headless:=0`, only env_0 (slot 0) shows visible, slot 1 is hidden — matches the arena_node convention.
10. **Negative**: an invalid suite YAML → exit code 2, clear error to stderr; an unreachable `/arena/spawn_env` → exit code 2 within ~15s.
