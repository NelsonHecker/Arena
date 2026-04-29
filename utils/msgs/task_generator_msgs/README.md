# task_generator_msgs

ROS 2 interface definitions for `task_generator_node`.

## Services (`srv/`)

| File | Purpose |
|---|---|
| `ResetEpisode.srv` | Advance to a new episode; accepts optional world and seed for replay. Resolves any in-flight `RunEpisode` goal with `Result.SKIPPED` (reason="reset") rather than letting termination close it as `SUCCESS`. |
| `QueryWorlds.srv` | List available world shortnames. |
| `QueryScenarios.srv` | List scenario shortnames, optionally scoped to a world. |
| `QueryRobots.srv` | List available robot model shortnames. |
| `QueryStaticObstacles.srv` | List available static obstacle model shortnames. |
| `QueryDynamicObstacles.srv` | List available dynamic obstacle (pedestrian) model shortnames. |
| `QueryEnvironments.srv` | List available environment shortnames. |
| `QueryParametrizeds.srv` | List available parametrized obstacle set shortnames. |
| `QueueEpisode.srv` | Stage the next episode: modes (robots / obstacles / modules), `world`, `robots[]` (incremental union), and per-mode params. Per-field merge: empty scalar fields preserve previously-queued overrides; `robots` unions with prior queued set (dedup, insertion order); params upsert per leaf key. `action` enum currently has only `MERGE = 0`. Applied at the next `ResetEpisode`. |
| `GetTaskModes.srv` | Return currently active task mode strings. |
| `SpawnStatic.srv` | Spawn a static obstacle into the running episode via TM_Obstacles.extend. |
| `SpawnDynamic.srv` | Spawn a dynamic obstacle (pedestrian) via TM_Obstacles.extend. |
| `SpawnRobot.srv` | Spawn an additional robot via TM_Robots.extend (experimental). |

`Pause`, `Unpause`, and `WaitForWorld` use `std_srvs/Empty` directly.

## Messages (`msg/`)

| File | Purpose |
|---|---|
| `EpisodeRecord.msg` | One episode: id, world, seed, task modes, `robots` (active robot model names at reset), outcome, integrity flag, plus `obstacles_params` and `robots_params` (effective per-mode params; live values overlaid with staged dict for queued records). The same `episode_id` may be republished as outcome resolves; subscribers dedup by id. |

## Latched topics

Published `TRANSIENT_LOCAL` (depth 1) so subscribers attaching after publish see the current value:

| Topic | Type | Source |
|---|---|---|
| `state/episode` | `EpisodeRecord` | Current episode. Republished on every state mutation (start, outcome resolution). Same `episode_id` may appear repeatedly; subscribers dedup. |
| `state/queue` | `EpisodeRecord` | Queued (next) episode. Republished on every `QueueEpisode` write and after reset drains the queue. Depth configured via `episode_queue_depth` (default 10). |
| `state/paused` | `std_msgs/Bool` | Authoritative pause state; published from `_cb_pause` only on actual transitions. UIs should drive their pause indicator off this rather than off service-call return values. |

## Actions (`action/`)

| File | Purpose |
|---|---|
| `RunEpisode.action` | Single-flight episode runner: goal carries optional world; result reports outcome (`SUCCESS` / `FAILED` / `SKIPPED`). A concurrent `ResetEpisode` resolves the in-flight goal with `SKIPPED` (reason="reset"). |
