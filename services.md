# task_generator service cleanup + MCP server (combined)

## Context

Current state of the repo (verified by direct read):
- `task_generator_node` exposes 9 services (`reset_task`, `pause_simulation` (SetBool), `wait_for_world`, `get_environments`, `get_parametrizeds`, `get_obstacles`, `get_scenarios`, `get_robots`, `get_worlds`).
- `task_generator_msgs` has 7 `Get*.srv` files (one of which, `GetRobotScenarios.srv`, is dead code), no `msg/` directory.
- Internal callers: `arena_training/.../base_env.py` (calls `reset_task`, `pause_simulation`), `rosnav_rl/.../curriculum_base.py` (uses raw `SetParameters` to flip task modes + episode params).
- No MCP infrastructure anywhere. The `vllm` feature provides a LiteLLM proxy already; LLM stack exists.
- `task_generator_msgs/CMakeLists.txt` uses `file(GLOB ...)` — new files are picked up automatically.

This plan covers two pieces together:
1. **Service cleanup** — rename for verb consistency (task → episode), split god-services (`pause_simulation`, `get_obstacles`), add a small lifecycle surface, structured `Info[]` query responses, LLM-shaped `.srv` field comments. Task-mode setter is the one custom config service (set/get only — value space is enums); episode-shaping params (timeout, goal_tolerance, etc.) stay on raw ROS2 params with `ParameterDescriptor`s.
2. **MCP server** — new `task_generator_mcp` package wrapping services as Model Context Protocol tools + resources. Enum constraints in tool schemas are compiled at startup from the Python source-of-truth (`Constants.TaskMode.*`), not from `.msg`-defined constants — keeps a single source of truth.

Service cleanup is upstream of MCP — MCP wraps the services. Both ship in this plan because the contract is small enough to lock in once and fan out.

**Scope boundaries** (per prior conversation):
- Core dispatcher only. Task-mode internals (PROMPT's `set_velocity_field`/`set_arena_world_bounds`, TM_Scenario's scenario application) are **not touched**.
- Simulator-backend services (HuNav's `get_agents`/`get_walls`, Gazebo/Isaac internals) are **not touched**.
- **Robot goal-setting is NOT added at the task_generator level.** That surface already lives at the per-robot endpoint advertised by the p2p navigation task adapter / `arena_robots` task_server: `<robot_namespace>/goto_pose` (action type `arena_robots_msgs/action/GotoPose`). External callers (panel, MCP, CLI) drive robots through that endpoint directly. Task-generator-internal manual-mod paths (RVIZ_UI's `Task.set_robot_goal` / `Task.set_robot_position`) flip the episode integrity flag; external direct sends to `<robot>/goto_pose` are out-of-band and not observed.
- **Spawn/despawn services ARE added** at the new `runtime/` namespace, dispatched through the active task mode's `extend()` method (so task modes still own population semantics; the service is a thin dispatcher).
- No backward-compat aliases. Hard cut.
- MCP is a thin wrapper over services; no auto-generation from `.srv` for v0 (hand-written tool registrations).

---

## Concrete contract (locked, all agents read this)

### Service namespace layout (registered via `self.service_namespace(group, name)` in node.py)

```
lifecycle/reset_episode    ResetEpisode             # service; takes target + optional world
lifecycle/run_episode    QueueEpisode (action)    # action server (serializes goals)
lifecycle/pause            Empty                    # service
lifecycle/unpause          Empty                    # service
lifecycle/wait_for_world   Empty                    # service

query/worlds               QueryWorlds
query/scenarios            QueryScenarios
query/robots               QueryRobots
query/static_obstacles     QueryStaticObstacles
query/dynamic_obstacles    QueryDynamicObstacles
query/environments         QueryEnvironments
query/parametrizeds        QueryParametrizeds

config/queue_episode       QueueEpisode             # action enum (MERGE only); per-field merge of next-episode overrides
config/get_task_modes      GetTaskModes

runtime/spawn_static       SpawnStatic              # service; dispatches to TM_Obstacles.extend
runtime/spawn_dynamic      SpawnDynamic             # service; dispatches to TM_Obstacles.extend
runtime/spawn_robot        SpawnRobot               # service; dispatches to TM_Robots.extend (experimental)
```

**Episode-shaping params** (`timeout`, `goal_tolerance_radius`, `robot_safe_dist`, `auto_reset`, `train_mode`, `episodes`, `record_data_dir`) stay on ROS2 params. Each is declared with a `ParameterDescriptor` carrying `description`, `floating_point_range` / `integer_range` where applicable, and `read_only=False`. Internal callers and MCP both go through `SetParameters`/`GetParameters`. `get_static_config` is also dropped — startup config (`sim`, `human`, `agent_name`, planner stack) reads via `GetParameters` against documented param names.

### Latched topics (new)
- `state/world` — `std_msgs/String`, latched (TRANSIENT_LOCAL, depth 1). Published whenever the active world changes (i.e. when `_current_episode.world` changes at a reset boundary).
- `state/episode` — `task_generator_msgs/EpisodeRecord`, latched (TRANSIENT_LOCAL, depth 1). Current episode only. Republished on every state mutation (episode start, outcome resolution). Same `episode_id` may appear repeatedly across publications as the record mutates; subscribers dedup by id and keep the latest version. History is not exposed via the API; consumers that need a window accumulate locally.
- `state/queue` — `task_generator_msgs/EpisodeRecord`, latched (TRANSIENT_LOCAL, depth `episode_queue_depth`, default 10). Queued (next) episode reflecting the current overrides buffer overlaid with live values. Republished on every `QueueEpisode` write and after reset drains the queue.

### Existing topics (kept untouched)
`task_reset`, `finished`, `reset_start`, `reset_end`.

### RVIZ_UI input topics (namespaced)
Today the RVIZ_UI module subscribes to root-level `/initialpose`, `/goal_pose`, `/clicked_point` — wrong for multi-task_generator setups (one RViz click would target every instance). Move them under the task_generator node namespace:
- `<task_generator_node>/initialpose`
- `<task_generator_node>/goal_pose`
- `<task_generator_node>/clicked_point`

Both subscriber side ([tasks/modules/rviz_ui.py:9-11](task_generator/task_generator/tasks/modules/rviz_ui.py#L9)) and the RViz default config template ([utils/rviz_utils/config/rviz_default.rviz:58,65,73](utils/rviz_utils/config/rviz_default.rviz#L58)) must be updated together. RViz tools (`2D Pose Estimate`, `2D Goal Pose`, `Publish Point`) publish to whatever topic their `Topic.Value` field says; using the existing `{task_generator_node}` template substitution in `rviz_config.py:342` makes this clean.

### `.srv` schemas (concrete — agents must match these field names)

**ResetEpisode.srv** — advances to a new episode. Replay/retry/back are caller-side: query history, then call this with the desired seed and world.
```
# World id for the new episode. Empty = inherit from current.
string world
# Seed for the new episode. -1 (default) = derive via blake2b((run_seed, world, episode_id)).
# Any non-negative value = use verbatim, typically copied from a historical
# EpisodeRecord.seed for bit-perfect replay (only meaningful for TM_Random /
# TM_Scenario; other modes ignore until migrated). Negative values other
# than -1 are reserved.
int64 seed -1
---
bool success
string error_msg
```

**QueueEpisode.action** (lives under `task_generator_msgs/action/`)
```
# === Goal ===
# Optional world to load before this episode; empty keeps current.
string world

---

# === Result ===
# Episode finished its goals.
uint8 SUCCESS = 1
# Episode ran but failed (timeout, collision, abandoned, etc.).
uint8 FAILED = 2
# Episode was preempted/cancelled before terminating naturally.
uint8 SKIPPED = 3
uint8 state
# Human-readable detail; empty by default.
string reason
# Episode index that ran; 0 if SKIPPED before start.
uint32 episode_id

---

# === Feedback ===
# Episode has been pulled off the queue and is now running.
uint8 STARTED = 1
uint8 state
```

**Pause.srv / Unpause.srv** — use `std_srvs/Empty` directly; do not create new files.

**WaitForWorld.srv** — use `std_srvs/Empty` directly; do not create new file.

**No `SetWorld` service.** World is bound to the episode; it can only change at an episode boundary via `reset_episode(target=NEXT, world=W)` or `run_episode(world=W)`.

**QueryWorlds.srv / QueryRobots.srv / QueryEnvironments.srv / QueryParametrizeds.srv / QueryStaticObstacles.srv / QueryDynamicObstacles.srv** — request empty, response `string[] ids`. Bare strings; the Identifier `.shortname` is the only metadata available without per-asset YAML inspection. Promote to a structured `*Info` msg later when there's actually metadata to carry.

**QueryScenarios.srv**
```
# Restrict to scenarios for a specific world; empty means current world
string world
---
# Scenario shortnames scoped to the world in the request
string[] ids
```

**QueueEpisode.srv** — strings validated server-side against the Python enum (`Constants.TaskMode.TM_Robots(value)` etc.). MCP compiles allowed-value constraints into the tool JSON schema at startup from the same enum. Per-field merge with `action = MERGE` (the only currently-defined value).
```
# Per-field merge: empty/zero leaves prior queued value untouched.
uint8 MERGE = 0
uint8 action

# Empty keeps prior queued value.
string tm_robots
# Empty keeps prior queued value.
string tm_obstacles
# Replaces current set when keep_modules=false.
string[] tm_modules
# True ignores tm_modules.
bool keep_modules

# Empty keeps prior queued value.
string world
# Incremental: union with prior queued robots set; dedup; empty array no-op.
string[] robots

# Leaf-keyed per-mode params; per-key upsert.
rcl_interfaces/Parameter[] obstacles_params
# Leaf-keyed per-mode params; per-key upsert.
rcl_interfaces/Parameter[] robots_params
---
bool success
string error_msg
```

**GetTaskModes.srv**
```
---
string tm_robots
string tm_obstacles
string[] tm_modules
```

**SpawnStatic.srv / SpawnDynamic.srv** — same shape, different model identifier space (static obstacles vs pedestrians/dynamic).
```
# Model shortname (must appear in QueryStaticObstacles / QueryDynamicObstacles).
string model
# Pose for the spawned entity. Ignored when use_pose=false.
geometry_msgs/PoseStamped pose
# When true, place at `pose`; when false, the active task mode chooses a random
# pose via TM_Random's placement logic (the canonical default).
bool use_pose
---
# Server-assigned id of the spawned entity; empty on failure.
string id
bool success
string error_msg
```

**SpawnRobot.srv** — same shape, plus a name slot. Marked experimental until per-sim/per-task-mode implementations stabilize.
```
# Robot model shortname (must appear in QueryRobots).
string model
# Robot name; if empty, server auto-generates "<model>_<n>".
string name
# Optional pose. When use_pose=false, TM_Robots.extend chooses placement.
geometry_msgs/PoseStamped pose
bool use_pose
---
string name
bool success
string error_msg
```

### `.msg` schemas

**`EpisodeRecord`** is the universal record type, published on both `state/episode` (current) and `state/queue` (next). Same `episode_id` may appear repeatedly across publications as the record mutates; subscribers dedup by id and keep the latest version. History is no longer exposed via the API — consumers that need a window accumulate locally from the topic.

```
# EpisodeRecord.msg
# Same id may appear repeatedly across publications as outcome resolves;
# subscribers dedup by episode_id and keep the latest version per id.
# 0 = idle.
uint32 episode_id
# World id bound to this episode.
string world
# Deterministic seed; populated at episode start.
int64 seed
# Snapshot of task modes at the start of this episode.
string tm_robots
string tm_obstacles
string[] tm_modules
# Robot model names active at this episode's reset.
string[] robots
# Lifecycle state.
uint8 UNFINISHED = 0
uint8 SUCCESS    = 1
uint8 FAILED     = 2
uint8 SKIPPED    = 3
uint8 outcome_state
string outcome_reason
string goal_uuid
builtin_interfaces/Time start_time
# False = manually mutated mid-episode.
bool integrity
# Effective params for tm_obstacles only; live overlaid with staged for queued records.
rcl_interfaces/Parameter[] obstacles_params
# Effective params for tm_robots only; live overlaid with staged for queued records.
rcl_interfaces/Parameter[] robots_params
```

No `*Info` wrappers — bare `string[]` is the right shape for the simple queries until per-asset metadata exists.

**No enum-carrier `.msg` files.** The Python enums in `task_generator/constants/__init__.py:29-65` are the single source of truth. Hand-coded `.msg` constants would drift on every Python-side enum change. Wire format is the enum `.value` string; MCP tool schemas embed JSON-schema `enum` constraints compiled from the Python enum members at server startup.

### `.srv` / `.msg` conventions
- Every field gets a `#` comment immediately above explaining purpose, value space, units, constraints. These become MCP tool descriptions.
- Enum-valued fields use `string` (the Python enum `.value`). Server validates by attempting `EnumClass(value)`; failure → `success=False` with allowed values listed in `error_msg`. MCP applies the same constraint at the tool-schema layer so the LLM sees valid options upfront.
- Setter services return `bool success` + `string error_msg` (empty on success).

---

## MCP server design

**Package:** new ament_python package at `utils/task_generator_mcp/` (sibling of `arena_rclpy_mixins`, `rviz_utils`).

**Layout:**
```
utils/task_generator_mcp/
  package.xml
  setup.py
  resource/task_generator_mcp
  task_generator_mcp/
    __init__.py
    server.py        # MCP server entry point
    ros_bridge.py    # rclpy node + service clients
    tools.py         # one Python function per service, decorated as MCP tool
    resources.py     # MCP resources for state/world, state/episode
```

**SDK:** the official `mcp` Python SDK (`pip install mcp`). Exposes `Server`, `@server.list_tools`, `@server.call_tool`, `@server.list_resources`, `@server.read_resource`, stdio transport via `mcp.server.stdio.stdio_server()`.

**Transport:** stdio for v0 (works with Claude Desktop, mcp-cli, any stdio-MCP client). HTTP/SSE deferred.

**Bridge:**
- `ros_bridge.py` defines a single `RosBridge` class wrapping an `rclpy.Node` (built on `arena_rclpy_mixins.AsyncNode` so we get `await_ros` / `ClientWrapper` for free; per memory `feedback_async_rclpy_mixins`).
- The bridge spins on a background thread; the MCP server runs on the main asyncio loop.
- One `ClientWrapper` per task_generator service. Service paths configurable via env var `TASK_GENERATOR_NODE_NAME` (default `/task_generator_node`).

**Tools — service-backed and action-backed:**
- `lifecycle_reset_episode(target: str = "NEXT", world: str = "")` → service call. JSON-schema `enum: ["NEXT", "PREVIOUS", "CURRENT"]` for `target`, default `"NEXT"`; mapped to `uint8` constant. `world` empty inherits.
- `lifecycle_run_episode(world: str = "") -> {state, reason, episode_id}` → **action client**. Sends goal, awaits result. v0 does not stream feedback. `state` returned as string name (`"SUCCESS"`/`"FAILED"`/`"SKIPPED"`).
- `lifecycle_pause()` / `lifecycle_unpause()` / `lifecycle_wait_for_world()`
- `query_worlds()`, `query_scenarios(world: str = "")`, `query_robots()`, `query_static_obstacles()`, `query_dynamic_obstacles()`, `query_environments()`, `query_parametrizeds()` → all return `list[str]`.
- `query_episode() -> {current, queued}` → reads cached `state/episode` and `state/queue` subscriptions. No service call.
- `config_queue_episode(tm_robots: str = "", tm_obstacles: str = "", tm_modules: list[str] | None = None, keep_modules: bool = False, world: str = "", robots: list[str] | None = None)` — calls `config/queue_episode` with `action = MERGE`. JSON-schema `enum` constraints compiled at startup from `Constants.TaskMode.TM_Robots`, `TM_Obstacles`, `TM_Module` (`.value` strings).
- `config_get_task_modes()` — returns `.value` strings.

**Tools — param-backed (allowlist over `SetParameters`/`GetParameters`):**
- `config_set_episode_params(timeout: float | None = None, goal_tolerance_radius: float | None = None, robot_safe_dist: float | None = None, auto_reset: bool | None = None, train_mode: bool | None = None, episodes: int | None = None, record_data_dir: str | None = None)` — the tool builds a single `SetParameters.Request` containing only the fields the caller passed. Type validation comes from the param's `ParameterDescriptor` server-side; the MCP tool schema mirrors descriptor-declared ranges.
- `config_get_episode_params()` — single `GetParameters` call against the allowlist.
- `config_get_static_config()` — `GetParameters` against the documented startup-config allowlist (`sim`, `human`, `agent_name`, `global_planner`, `local_planner`, `inter_planner`, `navigator`).

The param allowlist lives in `task_generator_mcp/params.py` as a constant — single place to extend when new mutable params are added.

Tool descriptions are hand-written in `tools.py` for v0, keyed off the same wording as `.srv` field comments / `ParameterDescriptor.description` strings.

**Resources (read-only state):**
- `task_generator://state/world` — current world id (subscribes to latched `state/world` topic, returns last value).
- `task_generator://state/episode` — `{current, queued}` JSON, sourced from latched `state/episode` and `state/queue` topics.

**Entry point:** `task_generator_mcp` console script in `setup.py` → `task_generator_mcp.server:main`. Runs stdio MCP server.

**Smoke flow:** `task_generator_mcp` running, with `task_generator_node` alive, called from `mcp` CLI:
```
$ mcp tools task_generator_mcp
$ mcp call task_generator_mcp query_worlds
```

(Not run in this PR per memory `feedback_no_smoke_tests` — left for the user.)

---

## Files to modify / create

### `task_generator_msgs` (Agent A)
- New `srv/`: `ResetEpisode.srv`, `QueryWorlds.srv`, `QueryScenarios.srv`, `QueryRobots.srv`, `QueryStaticObstacles.srv`, `QueryDynamicObstacles.srv`, `QueryEnvironments.srv`, `QueryParametrizeds.srv`, `GetEpisode.srv`, `SetTaskModes.srv`, `GetTaskModes.srv`, `SpawnStatic.srv`, `SpawnDynamic.srv`, `SpawnRobot.srv` — **14 files**. No `SetWorld.srv` (world is episode-bound).
- New `action/`: `QueueEpisode.action` — **1 file**. (CMakeLists.txt already globs `action/*.action`; no edits needed.)
- New `msg/`: `EpisodeRecord.msg`, `EpisodeState.msg` — **2 files**. No `*Info` wrappers, no enum-carrier msgs, no `EpisodeState.msg` (replaced by `EpisodeState.current`).
- **Delete** all 7 existing `srv/Get*.srv` files via Bash `rm` (the agent must request this; CMakeLists glob requires the files be removed, not just orphaned).
- `CMakeLists.txt` — no edits needed (GLOB picks up files); confirm `DEPENDENCIES std_msgs` is sufficient (all new types reference each other or std_msgs).

### `task_generator/task_generator/node.py` (Agent B)
- Rewrite `_set_up_services` (currently lines 307-365): register **16 services** + **1 action server** at the new namespaced paths.
- **EpisodeRuntime attrs struct** holds all episode-related state in one named container, replacing what would otherwise be ~8 separate `self._*` fields on the node:
  ```python
  @attrs.define
  class EpisodeRuntime:
      current: EpisodeRecord
      previous: EpisodeRecord | None = None
      history: collections.deque[EpisodeRecord] = attrs.field(
          factory=lambda: collections.deque(maxlen=10)
      )
      run_seed: str = attrs.field(factory=lambda: uuid.uuid4().hex)
      pending_outcomes: dict[int, asyncio.Future] = attrs.field(factory=dict)
      pending_overrides: TaskModeOverrides | None = None
      action_in_flight: bool = False
      pending_external_goal: object | None = None  # ServerGoalHandle
  ```
  Node holds `self._episodes: EpisodeRuntime`. `history.maxlen` parameterized via `episode_history_size` ROS param at construction time. Per-episode seed = `int.from_bytes(blake2b(f"{run_seed}|{world}|{episode_id}".encode(), digest_size=8).digest(), "big")`.
- Split `_cb_pause_simulation` → `_cb_pause` + `_cb_unpause`; factor shared internal `_do_pause`/`_do_unpause`.
- Split `_cb_get_obstacles` → `_cb_query_static_obstacles` + `_cb_query_dynamic_obstacles`.
- Rename existing query callbacks: `_cb_get_worlds` → `_cb_query_worlds`, etc. Each returns `string[]` of `.shortname` values.
- New service callbacks: `_cb_reset_episode` (world + seed), `_cb_get_episode` (range), `_cb_set_task_modes`, `_cb_get_task_modes`.
- **`_cb_reset_episode`**: build new EpisodeRecord with `world = request.world or _current_episode.world`, `seed = request.seed if request.seed != 0 else blake2b((run_seed, world, episode_id+1))`, fresh `episode_id`, current task modes; push old current onto history; trigger reset. Replay/retry are caller-side: client looks up a historical record's `seed` and `world` and passes them.
- **Reset cycle plumbing:** `Task.reset(record)` accepts the EpisodeRecord; the existing reset path passes `record.seed` down to `tm_obstacles.reset()` and `tm_robots.reset()`. Migrate **TM_Random** and **TM_Scenario** to seed their RNGs from `record.seed`. Other modes accept the seed param but may currently ignore it — document per-mode determinism status in `tasks/README.md`.
- **Seed derivation** uses `hashlib.blake2b(f"{run_seed}|{world}|{episode_id}".encode(), digest_size=8).digest()` cast to uint64 (big-endian). Stable across processes when `run_seed` is set explicitly. Default `run_seed = uuid.uuid4().hex` makes each launch unique.
- **Two seed concerns, both satisfied:**
  - *Intra-process replay:* the seed is **stored** in EpisodeRecord at episode start. To replay, caller looks up history record's seed and passes it back via `reset_episode(seed=...)`. No re-derivation; bit-perfect by construction (where TMs honor the seed).
  - *Inter-process determinism:* same `run_seed` + same `world` + same `episode_id` → same uint64 across processes via blake2b stability.
- **TM hierarchy (Agent B):**
  - `TM_Obstacles` and `TM_Robots` base classes are unified: `TM_Random` *is* the base implementation for each. The "random placement" logic lives there; other modes subclass it.
  - All TMs inherit `extend(model, pose=None)` from `TM_Random` for free.
  - **`TM_Scenario.extend()` override:** first try to fill any unused predefined scenario slots; if exhausted, delegate up to `TM_Random.extend()` for random placement. Slot tracking is per-scenario, internal to TM_Scenario.
- **Task-mode `extend()` interface (new):**
  - `TM_Obstacles` base class gains `async extend(self, kind: ObstacleKind, model: str, pose: Pose | None = None) -> str` returning the spawned id. `kind` is `STATIC` or `DYNAMIC`. Default impl: if `pose is None`, delegate to `TM_Random`'s placement logic; if set, spawn at the pose. Concrete subclasses override only when they need different semantics.
  - `TM_Robots` base class gains `async extend(self, model: str, name: str | None = None, pose: Pose | None = None) -> str` returning the assigned name. Same default-pose-via-TM_Random pattern.
  - **Task modes touched in this PR:** TM_Random gets the canonical `extend` implementation. Other TMs inherit the default (delegate to TM_Random for random placement, accept explicit pose). Mode-specific overrides (e.g. SCENARIO refusing extends, PROMPT integrating into its prompt flow) are follow-up — out of scope for this PR.
- **`runtime/spawn_*` callbacks** (`_cb_spawn_static`, `_cb_spawn_dynamic`, `_cb_spawn_robot`):
  1. Look up active `tm_obstacles` / `tm_robots` instance.
  2. Convert `request.pose` to `Pose | None` (None when `use_pose=false`).
  3. Await `tm.extend(...)`.
  4. Flip `_current_episode.integrity = False`; republish `EpisodeState`.
  5. Return assigned id and `success=True`. On exception (unknown model, placement failure), return `success=False, error_msg=str(e)`.
- **Integrity flag flip points** (all flip `_current_episode.integrity = False` and republish `EpisodeState`):
  - `runtime/spawn_*` callbacks.
  - `Task.set_robot_position` (called from `Mod_OverrideRobot._cb_set_position` on namespaced `<task_generator_node>/initialpose`).
  - `Task.set_robot_goal` (called from `Mod_OverrideRobot._cb_set_goal` on namespaced `<task_generator_node>/goal_pose`).
  - **Not flipped** by `reset_episode(CURRENT/PREVIOUS)` — replays preserve the historical record's integrity value.
  - **Not observable**: external direct calls to `<robot>/goto_pose` (arena_robots task_server). These bypass task_generator entirely; integrity stays whatever it was. Documented caveat — `arena_evaluation` filters should treat integrity=true as "task_generator-mediated only."
  - On every NEXT (new EpisodeRecord), integrity initializes to `true`.
- **`_cb_set_task_modes`**: validate each non-empty string with `Constants.TaskMode.TM_Robots(value)` etc. Catch `ValueError`, return `success=False` with allowed values listed. On success, store pending values; apply at the start of the next reset inside the lock — they bind into the new EpisodeRecord at NEXT. `keep_modules=True` skips module replacement. Empty string skips that scalar field.
- **Unified dispatch via `lifecycle/run_episode` action server.** Single-flight; one in-flight episode at a time. The action server is the only path that builds EpisodeRecords and drives reset cycles.
  - `goal_callback`: accept new external goals only when nothing is in-flight AND no pending external goal already exists. Otherwise reject. (Optionally: hold one pending external slot — see "On terminal" below.)
  - `execute_callback`: build EpisodeRecord (using goal's `world` and `seed` overrides; `seed=0` derives), trigger reset cycle, publish `STARTED` feedback, await a per-episode_id `asyncio.Future` resolved by `_check_task_status`, return `RunEpisode.Result(state, reason, episode_id)`.
  - **`reset_episode` service is implemented internally as "submit an external `run_episode` goal and don't wait for the result."** The service callback queues the goal via the same `goal_callback` path, returns `success=True` once accepted (or `False, "busy"` if rejected), and does NOT await termination.
  - **`auto_reset` is implemented at the action-server's terminal hook:**
    ```
    on goal terminal:
        if pending external goal: accept and execute it
        elif auto_reset=true:    synthesize internal goal (world inherited, seed derived) and execute
        else:                    stay idle
    ```
    Internal auto-reset goals don't have a goal_uuid (record's `goal_uuid` stays empty). External goals carry their action UUID.
  - `cancel_callback`: resolve the in-flight future with `(SKIPPED, "cancelled")`.
  - Publish `EpisodeState` to `state/episode` on every state change (start, terminate, cancel).
- **`_cb_get_episode(range)`**: build `EpisodeState` from `_episode_history` (clipped to last `range` items) + `_current_episode`. Return.
- New latched publisher: `state/world` (publish on `_current_episode.world` change at reset boundary). `state/episode` published as above.
- **ParameterDescriptors:** when declaring the runtime-mutable params (`timeout`, `goal_tolerance_radius`, `robot_safe_dist`, `auto_reset`, `train_mode`, `episodes`, `record_data_dir`, plus the new `run_seed` and `episode_history_size`), attach a `ParameterDescriptor` carrying `description` and ranges where applicable. This is what makes the param-backed MCP tools discoverable.
- **Standalone vs managed mode** is selected via the existing `auto_reset` boolean param.
  - `auto_reset=true` (default, "standalone"): node auto-advances on terminal detection. Runs `episodes` count then shuts down.
  - `auto_reset=false` ("managed"): terminal detection still publishes `state/episode` events, but does NOT trigger an auto reset. External controller (training script, MCP, panel, action goal) drives transitions via `reset_episode` / `run_episode`.
  - **`train_mode` ROS param is deleted entirely.** It was wearing four hats today; only the ones relevant to task_generator are removed in this PR (the Robot-runtime-param `train_mode` inside arena_robots stays for now — the student's native nav2 adapter will obsolete it).
- **`train_mode` removal — task_generator scope:**
  - `node.py:71` `_train_mode` field deleted.
  - `node.py:196` short-circuit deleted; `auto_reset` is the only managed switch.
  - `tasks/task.py:118, 134, 205` deleted — the "lock task modes at init / re-poll every reset" pattern they implemented is replaced by the new `_pending_tm_*` flow driven by `config/set_task_modes`.
  - `manager/robot_manager.py:152, 356` — Robot-runtime-param `train_mode` **kept** (forwarded into arena_robots Nav2 internals). Student's adapter will retire it later.
- Use `arena_rclpy_mixins` helpers where applicable; do not hand-roll `asyncio.wrap_future`.

### `task_generator/task_generator/tasks/task.py` (Agent B)
- `Task.set_robot_position` and `Task.set_robot_goal`: flip `self.node._current_episode.integrity = False` and trigger an `EpisodeState` republish. (Currently these just dispatch to the adapter — wrap with the integrity hook.)
- `Task.force_reset` (called from `_cb_new_scenario` on the namespaced `clicked_point`): unchanged behaviorally — but it now triggers `_cb_reset_episode(target=NEXT)` semantics rather than the legacy `reset_task`.
- `Task.reset(record: EpisodeRecord)` signature change: passes `record.seed` to TM resets.

### `task_generator/task_generator/tasks/obstacles/__init__.py` and `tasks/robots/__init__.py` (Agent B)
- **TM_Random and TM_Scenario stay as peers under their respective base classes** — TM_Random has substantial random-specific config ([_Config attrs class with 6 ROSParamT fields](task_generator/task_generator/tasks/obstacles/random.py)); making it a parent would force TM_Scenario etc. to inherit slots they don't want.
- Factor random *placement* (not random *config*) into a free helper: new file `tasks/obstacles/_placement.py` exposing `async def random_placement(ctx, ...) -> Pose`. Same for robots.
- Add `extend(model, pose=None)` method on the `TM_Obstacles` and `TM_Robots` base classes. Default implementation: if `pose is None`, calls `random_placement(self._ctx)`; spawns at the chosen pose.
- TM_Scenario overrides `extend()` to fill open scenario slots first, then delegates to the placement helper when exhausted.
- Other modes inherit the default unchanged.
- Confirm TM params are namespaced (e.g. `tm_obstacles.random.n_static_obstacles_range`) consistent with the existing `Constants.TaskMode.TM_Obstacles.prefix` pattern in [constants/__init__.py:37-38](task_generator/task_generator/constants/__init__.py#L37). If today's declarations don't follow this prefix, fix during the PARAMS audit.

### Internal method rename pass (Agent B, consistency)
- `Task._reset_task` → `Task._reset_episode`
- `Task.before_reset_task` → `Task.before_reset_episode` (in `manager/environment_manager.py`, `simulators/sim/*.py`, `manager/README.md`)
- `Task.after_reset_task` → `Task.after_reset_episode`
- Update [tasks/modules/benchmark.py:393, 398, 483](task_generator/task_generator/tasks/modules/benchmark.py#L393) call sites.
- Pure rename; no behavior change. Bundle in Agent B's commit so internal naming matches the renamed service surface.

### `utils/arena_rclpy_mixins/arena_rclpy_mixins/params.py` (Agent B — small extension)
- Forward declaration is the standard: each TM declares its parameter schema at node startup, not lazily on first activation.
- Each TM is a package: `__init__.py` (eager) calls `_TaskRegistry.register_<family>` and `declare_schema(node, ns)`. `impl.py` (lazy) contains the class body and is imported only when the mode is activated.
- `declare_schema(node, ns)` calls `node.rosparam.declare_forward(name, default, descriptor=ParameterDescriptor(...))` for every parameter the mode owns.
- `_TaskRegistry.walk_schemas(node)` is called once at node init to fire every registered schema. No per-activation declare/destroy cycle exists.

### `task_generator/launch/task_generator.launch.py` and `arena_bringup/launch/arena.launch.py` (Agent B)
- Expose `auto_reset` as a launch argument (default `true` for backward compat). Forward via `**auto_reset.param(bool)` (matches the existing `train_mode` pattern at [task_generator.launch.py:83-161](task_generator/launch/task_generator.launch.py#L83)).
- Description references the standalone/managed semantics documented in the node-side ParameterDescriptor.
- **`train_mode` is removed from task_generator_node entirely** — no ROS param declaration, no launch arg in either file.
- **`train_config:=path` is the only RL-mode entry point.** When non-empty:
  - Launch derives `auto_reset:=false` (managed mode) and forwards as a node param.
  - Launch starts `train_agent.py` with the config (existing behavior).
  - No other implicit flags. Cmd_vel routing is handled by the arena_robots adapter layer (out of scope per concern A; student's native nav2 adapter will own that).
- Concretely, replace the existing `train_mode` LaunchArgument blocks in [arena.launch.py:141-142, 263](arena_bringup/launch/arena.launch.py#L141) and [task_generator.launch.py:83-84, 161](task_generator/launch/task_generator.launch.py#L83) with derived assignments from `train_config` non-emptiness, plus an explicit `auto_reset` LaunchArgument (default `true`, overridable).

### `arena_training/arena_training/environments/base_env.py` (Agent C)
- Line 146: `reset_task` → `lifecycle/reset_episode` in service-path construction.
- Lines 159-170, 383-385: replace the single `pause_simulation` (SetBool) client with two `EmptySrv` clients on `lifecycle/pause` and `lifecycle/unpause`. Where the code called `SetBool(True)`, call the pause client; where `SetBool(False)`, call resume.
- Remove `from std_srvs.srv import SetBool` once unused.

### `arena_training/deps/rosnav_rl/.../curriculum_base.py` (Agent C)
- Lines 97-100: parameter-node template default — update if it referenced a service path; node names stay.
- Lines 187, 320: where `SetParameters.Request()` sets `tm_robots`/`tm_obstacles`/`tm_modules`, **route to `config/set_task_modes`** with the `.value` strings directly (no enum-constant lookup needed; service is string-typed). Episode-shaping params (`timeout`/`goal_tolerance_radius`/`robot_safe_dist`/`auto_reset`/`train_mode`/`episodes`/`record_data_dir`) and any other params **stay on raw `SetParameters`** — no migration needed for those.
- Add `from task_generator_msgs.srv import SetTaskModes`. The `tm_modules` field is a `list[str]` of `.value` strings — convert from whatever shape the curriculum config uses (today often comma-joined string; split on comma if needed).

### `utils/task_generator_mcp/` (Agent D — new package)
- `package.xml` — ament_python, depends on `rclpy`, `rclpy_action`, `task_generator_msgs`, `task_generator` (for the Python enum import), `arena_rclpy_mixins`, `std_msgs`, `std_srvs`, `rcl_interfaces`.
- `setup.py` — `entry_points={'console_scripts': ['task_generator_mcp = task_generator_mcp.server:main']}`. Add `mcp>=1.0` to `install_requires`.
- `resource/task_generator_mcp` — empty marker file.
- `task_generator_mcp/__init__.py` — empty.
- `task_generator_mcp/ros_bridge.py` — `RosBridge` class: `rclpy.Node` + `ClientWrapper` for each service + an `ActionClient` for `lifecycle/run_episode` + clients for `SetParameters`/`GetParameters`/`DescribeParameters` against the task_generator node + subscribers for the two latched state topics with last-value caching. Spin on a background thread.
- `task_generator_mcp/params.py` — single allowlist constant: `EPISODE_PARAMS = ("timeout", "goal_tolerance_radius", "robot_safe_dist", "auto_reset", "train_mode", "episodes", "record_data_dir")`, `STATIC_CONFIG_PARAMS = ("sim", "human", "agent_name", "global_planner", "local_planner", "inter_planner", "navigator")`.
- `task_generator_mcp/tools.py` — registers MCP tools. **Enum constraints compiled from Python source:** at module load, `from task_generator.constants import Constants` and build JSON schemas like `{"type":"string","enum":[m.value for m in Constants.TaskMode.TM_Robots]+[""]}` for `tm_robots`. Param-backed tools build their schemas from `DescribeParameters` results at startup (one round-trip on connect, cached). Also exposes `runtime_spawn_static` / `runtime_spawn_dynamic` / `runtime_spawn_robot` as MCP tools (kwargs: `model`, optional `pose` dict, optional `name` for robot). **Robot goal-setting is NOT exposed at the task_generator MCP layer** — callers needing that go through the per-robot `<robot>/goto_pose` action endpoint owned by `arena_robots`.
- `task_generator_mcp/resources.py` — registers MCP resources for `task_generator://state/world` and `task_generator://state/episode`.
- `task_generator_mcp/server.py` — `main()` constructs `RosBridge`, fetches param descriptors once for the allowlist, registers tools/resources on an MCP `Server`, runs stdio transport.

---

## Agent split (6 parallel Sonnet agents)

All six read this plan file as the contract. The contract is concrete enough to avoid drift.

| Agent | Scope | Outputs |
|---|---|---|
| **A: msgs** | `utils/msgs/task_generator_msgs/{srv,msg,action,CMakeLists.txt}` | 14 new `.srv`, 1 new `.action` (`RunEpisode`), 2 new `.msg`; deletes 7 obsolete `Get*.srv` (requests Bash for `rm`) |
| **B: node** | `task_generator/task_generator/node.py`, `tasks/task.py`, `tasks/obstacles/__init__.py`, `tasks/robots/__init__.py`, TM_Random impls, `task_generator/launch/task_generator.launch.py`, `arena_bringup/launch/arena.launch.py`, `utils/arena_rclpy_mixins/arena_rclpy_mixins/params.py` | Rewritten `_set_up_services`, all new/split/renamed callbacks, action server, EpisodeRecord state, `Task.set_robot_*` integrity hooks, `extend()` method on TM bases (TM_Random as base), `train_mode` removal across node + launches, `auto_reset` launch arg + ParameterDescriptor, `ROSParamT.destroy()` |
| **C: callers** | `arena_training/.../base_env.py`, `arena_training/.../flatland_gymnasium_env.py`, `rosnav_rl/.../curriculum_base.py` | Migrated service paths + new `config/*` calls; `train_mode` ROS-param reads → constructor kwargs only |
| **D: mcp** | `utils/task_generator_mcp/` (new package) | Full MCP package per the design above |
| **E: rviz** | `task_generator/.../tasks/modules/rviz_ui.py`, `utils/rviz_utils/config/rviz_default.rviz` | Namespace `/initialpose`, `/goal_pose`, `/clicked_point` under task_generator node |
| **F: panel** | `utils/task_generator_gui/src/task_generator_panel.cpp`, `utils/task_generator_gui/src/task_generator_panel_getset_params.cpp`, header(s) | Service path migration across **both** cpp files; Back / Retry / Next buttons (Retry/Back implemented as `get_episode` query then `reset_episode` with the historical seed/world); task-mode comboboxes via `config/set_task_modes`; `get_*` clients → `query/*`; param widgets via standard `list_parameters` + `describe_parameters` + `get_parameters` filtered by task-mode prefix (e.g. `tm_obstacles.<mode>`), refreshed on combobox change; subscribe to `state/episode` for playlist; world combobox stages for Next |

Mutual exclusion: each agent owns its files exclusively. No agent touches another's scope.

Cross-references:
- A's `.srv` field names are the contract for B, C, D, F. Schemas above are precise — no agent should invent names.
- B's service paths (`lifecycle/...`, `query/...`, `config/...`, `runtime/...`) are the contract for C, D, F. Plan above lists all.
- D imports from `task_generator_msgs.srv`/`.msg`/`.action`; imports must match A's filenames.
- D also imports from `task_generator.constants` (the Python enum) — that's the source of truth for enum values, not any `.msg`.
- F is C++; uses `task_generator_msgs::srv::*` types and `arena_robots_msgs::action::GotoPose` (already used in arena_robots) for any direct robot-goal calls (panel does NOT call task_generator for goal-setting).

---

## Test assignments (per agent)

Per memory `feedback_no_smoke_tests`: static analysis + unit tests only; no `colcon build`, no launches. Per memory `feedback_no_mocking`: tests use real types; if a test would only work via mocking, skip it.

| Agent | Tests |
|---|---|
| **A: msgs** | Round-trip per `.srv`/`.msg`/`.action`: serialize a populated request/response/goal/feedback, deserialize, assert field equality. Pure-Python, no ROS runtime. |
| **B: node** | (1) Service-registration test: instantiate node in dummy mode, assert exactly the planned 16 services + 1 action are registered with expected paths. (2) Seed derivation: `blake2b((run_seed, world, episode_id))` is stable across calls and sensitive to all three inputs. (3) `EpisodeRuntime` invariants: history bounded by `maxlen`; `pending_overrides` apply once and clear at reset; `previous` set on NEXT, cleared on PREVIOUS-then-NEXT. (4) `ROSParamT.declare`/`destroy` idempotency. (5) `_cb_reset_episode` enum-value validation (unknown task-mode strings → success=False with allowed values listed). (6) `_cb_set_task_modes` server-side enum validation. |
| **C: callers** | None new — caller migration tests would require ROS runtime. Existing tests still pass post-rename (no behavior change at call sites). |
| **D: mcp** | (1) Tool-schema generation: confirm `Constants.TaskMode.TM_Robots.value` enum constraints land in JSON schema correctly. (2) Param allowlist round-trip: `DescribeParameters` results → tool schema → `SetParameters` request shape. (3) Action client wraps `RunEpisode.action` correctly (goal serialization, result deserialization, feedback streaming). |
| **E: rviz** | None new — config files only; behavior verified by Agent B's service-registration test. |
| **F: panel** | Static check only (C++ compile validation deferred to user post-build). |

## Doc assignments (per agent)

| Agent | Docs |
|---|---|
| **A: msgs** | `utils/msgs/task_generator_msgs/README.md` (if exists; else create with one-liner per new srv/msg/action). |
| **B: node** | `CLAUDE.md` (Reset lifecycle section ~lines 41-50, Training mode line 84), `task_generator/README.md` (lines 52, 58 — reset_task wording), `task_generator/task_generator/manager/README.md` (lines 102-103 — before/after_reset_task), `task_generator/task_generator/tasks/README.md` (TM_Random / extend() / EpisodeRecord), `task_generator/task_generator/constants/README.md` (auto_reset, train_mode removal), `arena_bringup/BRINGUP.md` (line 162 — train_mode), `arena_bringup/launch/README.md` (lines 34-35 — train_mode arg). |
| **C: callers** | `arena_training/README.md` (lines 54, 57, 65, 66, 69 — train_mode discussion → drop or rephrase), `arena_training/deps/rosnav_rl/rosnav_rl/rosnav_rl/action_server/README.md` (line 83 — train_mode reference). |
| **D: mcp** | New `utils/task_generator_mcp/README.md` documenting tools, resources, env vars (`TASK_GENERATOR_NODE_NAME`), MCP client setup (Claude Desktop, mcp-cli). |
| **E: rviz** | `task_generator/task_generator/tasks/modules/README.md` (RVIZ_UI section — namespaced topic paths). |
| **F: panel** | `utils/task_generator_gui/README.md` (if exists; else create) — Back/Retry/Next, playlist, world combobox staging, task-mode comboboxes. |

## Verification (post-agent landing)

Manual checks (post-fan-out, before commit):
1. **Cross-agent alignment grep:**
   - `grep -r "task_generator_msgs.srv" task_generator/ utils/task_generator_mcp/ arena_training/ rosnav_rl/` — every imported srv exists in A's output.
   - `grep -rn "config/set_task_modes\|lifecycle/reset_episode\|lifecycle/pause\|lifecycle/unpause" arena_training/ rosnav_rl/ utils/task_generator_mcp/` — every path is registered in B's `_set_up_services`.
   - **No `Tm*.msg` imports anywhere:** `grep -rn "from task_generator_msgs.msg import Tm" .` — must return nothing. Enum values are Python strings, not msg constants.
   - **No dropped services referenced:** `grep -rn "set_episode_params\|get_episode_params\|get_static_config" .` — must return nothing in code (param-backed tools wrap `SetParameters`/`GetParameters` directly).
2. **No dead service references:** `grep -rn "reset_task\|pause_simulation\|get_obstacles\|get_environments\|get_parametrizeds\|get_scenarios\|get_robots\|get_worlds\|wait_for_world" task_generator/ arena_training/ rosnav_rl/ utils/task_generator_mcp/` — only matches in node.py callback bodies if any internal helpers retained the name; no service-path string literals.
3. **MCP package sanity:** `python -c "from task_generator_mcp import server; from task_generator_mcp.tools import register_tools; from task_generator_mcp.resources import register_resources"` — imports resolve (run by user post-`colcon build`, not by us).
4. **Enum source-of-truth check:** confirm `task_generator_mcp/tools.py` imports `Constants.TaskMode.*` from `task_generator.constants` and uses `[m.value for m in ...]` to build JSON schema enum lists — no hand-coded enum value strings in MCP code.

User runs the actual build + integration smoke after reviewing the diff.

---

## Out of scope (explicit)

- Task-mode-specific services/topics other than the RVIZ_UI input-topic namespacing in Agent E. PROMPT's `set_velocity_field`/`set_arena_world_bounds` and TM_Scenario application internals stay untouched.
- Simulator-backend services (HuNav, Gazebo, Isaac, arena_humansim).
- Robot goal-setting wrapper at task_generator level — surface lives at per-robot `<robot>/goto_pose` (arena_robots task_server), unchanged.
- TM_* `extend()` overrides for non-TM_Random modes — they inherit the default (delegate to TM_Random for randomization, accept explicit pose). Mode-specific overrides (SCENARIO refusing, PROMPT integrating) are follow-ups.
- Bit-perfect replay for non-TM_Random/TM_Scenario task modes — seed param plumbed but each mode opt-in.
- Backward-compat aliases for renamed services.
- MCP HTTP/SSE transport, MCP prompts, auto-generation of MCP tools from `.srv` files — all v1.x material.
- Structured `Info[]` query responses — bare `string[]` is sufficient until per-asset metadata exists. Promote later when there's a real source (asset-YAML metadata key, sidecar file, etc.).
- Persona/rubric eval methodology (`arena_evaluation` extensions).
- Simulator permanence (separate workstream).
