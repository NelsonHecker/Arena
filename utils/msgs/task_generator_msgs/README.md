# task_generator_msgs

rosidl interfaces consumed and published by `task_generator` (the per-env episode loop). Episode lifecycle, task-mode and config queries, per-env spawn/reset, robot fleet descriptors.

Runtime types (env registry, holds, world confirm, cleanup, purge) live in [`arena_runtime_msgs`](../../../arena_runtime/arena_runtime_msgs/README.md) instead.

## Services (`srv/`)

| File | Purpose |
|---|---|
| `ResetEpisode.srv` | Advance to a new episode; accepts optional world and seed for replay. Resolves any in-flight `RunEpisode` goal with `Result.SKIPPED` (reason="reset"). |
| `QueueEpisode.srv` | Stage the next episode (modes, world, robots, per-mode params); applied at the next reset. |
| `Pause.srv` | Toggle pause from external callers. |
| `GetTaskModes.srv` | Return currently active task-mode strings. |
| `QueryWorlds.srv` / `QueryScenarios.srv` / `QueryEnvironments.srv` / `QueryParametrizeds.srv` / `QueryRobots.srv` / `QueryStaticObstacles.srv` / `QueryDynamicObstacles.srv` / `QueryTaskModes.srv` | Listing of available shortnames for the corresponding asset class. |
| `SpawnStatic.srv` / `SpawnDynamic.srv` / `SpawnRobot.srv` | Inject a static obstacle / dynamic pedestrian / additional robot into the running episode via `TM_Obstacles.extend` / `TM_Robots.extend`. `SpawnRobot` accepts an optional `args` (`diagnostic_msgs/KeyValue[]`) forwarded to `Robot.parse` (e.g. `local_planner`, `agent_name`). |

## Messages (`msg/`)

| File | Purpose |
|---|---|
| `EpisodeRecord.msg` | One episode: id, world, seed, task modes, `robots[]`, `outcome_state` (`QUEUED` / `RUNNING` / `SUCCESS` / `FAILED` / `SKIPPED` / `FATAL`), `outcome_info` (live status string, may be republished mid-episode via `Task.set_info`), integrity flag, plus `obstacles_params` / `robots_params` (effective per-mode params, with staged dict overlay for queued records). Published latched on `state/episode` and `state/queue`. |
| `RobotDescriptor.msg` | Per-robot description (model, ns, frame, capabilities). |
| `RobotFleet.msg` | All currently-active `RobotDescriptor`s in the env. Published latched on `state/robots`. |

## Actions (`action/`)

| File | Purpose |
|---|---|
| `RunEpisode.action` | Single-flight episode runner: goal carries optional world; result `state` is one of `QUEUED` / `RUNNING` / `SUCCESS` / `FAILED` / `SKIPPED` / `FATAL` (FATAL = env never reached a runnable state, do not retry). A concurrent `ResetEpisode` resolves the in-flight goal with `SKIPPED`. |
