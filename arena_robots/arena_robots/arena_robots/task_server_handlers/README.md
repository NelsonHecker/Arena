# Task kinds

A **task kind** is a public action endpoint the `task_server` advertises on
behalf of a robot. Each `TaskKind` has one action type (defined in
`arena_robots_msgs`) and one public suffix (e.g. `goto_pose`); the
`task_server` mounts it under the robot's namespace as
`<namespace>/<suffix>`. Which task kinds a running `task_server` actually
advertises depends on the selected `bringup` and the handlers registered for
that `(TaskKind, bringup_kind)` pair.

## Sources of truth

| File | Role |
|---|---|
| [`task_kinds.py`](../task_kinds.py) | `TaskKind` enum, `PUBLIC_SUFFIX`, `action_type()`, `endpoint()` — the only place these are defined |
| `task_server_handlers/__init__.py` | `HANDLERS` registry keyed by `(TaskKind, bringup_kind)`; stores zero-arg loaders so msgs deps are imported lazily |
| `task_server_handlers/<kind>/__init__.py` | per-kind `@HANDLERS.register` lazy-loader block; one entry per supported bringup |
| `task_server_handlers/<kind>/<bringup>.py` | the `TaskHandler` implementation for that `(kind, bringup)` pair |
| `arena_robots_msgs/action/<Kind>.action` | the IDL the action type comes from |
| `clients/<kind>.py` | optional Python client wrapper used by `task_generator` and standalone drivers |

## Adding a new task kind

### 1. Define the action IDL

Add `arena_robots_msgs/action/<Kind>.action`. Keep the goal/feedback/result
fields minimal and framework-neutral — every bringup has to implement it, so
nothing bringup-specific belongs here.

### 2. Register the enum and suffix

In [`task_kinds.py`](../task_kinds.py):

```python
class TaskKind(enum.Enum):
    GOTO_POSE = "goto_pose"
    FOLLOW_PATH = "follow_path"          # new

PUBLIC_SUFFIX: dict[TaskKind, str] = {
    TaskKind.GOTO_POSE: "goto_pose",
    TaskKind.FOLLOW_PATH: "follow_path", # new
}

def action_type(tk: TaskKind) -> type:
    if tk is TaskKind.GOTO_POSE:
        from arena_robots_msgs.action import GotoPose
        return GotoPose
    if tk is TaskKind.FOLLOW_PATH:       # new
        from arena_robots_msgs.action import FollowPath
        return FollowPath
    raise KeyError(tk)
```

The import stays inside the branch so `arena_robots_msgs` is only resolved
when the kind is actually in use.

### 3. Create the handler package

```
task_server_handlers/
└── follow_path/
    ├── __init__.py         # @HANDLERS.register(...) loaders, one per bringup
    ├── nav2.py             # FollowPathHandlerNav2(TaskHandler)
    └── _passthrough.py     # optional: shared implementations for none/external
```

`task_server_handlers/follow_path/__init__.py`:

```python
from arena_robots_msgs.action import FollowPath

from arena_robots.task_kinds import TaskKind
from arena_robots.task_server_handlers import HANDLERS, TaskHandler

FollowPathHandler = TaskHandler[FollowPath.Goal, FollowPath.Feedback, FollowPath.Result]

@HANDLERS.register((TaskKind.FOLLOW_PATH, "nav2"))
def _load_nav2():
    from .nav2 import FollowPathHandlerNav2
    return FollowPathHandlerNav2
```

A `TaskHandler` is a `Protocol` (see the base registry module) — implementing
it means accepting `(bringup, *, tf_buffer, node)` in `__init__` and exposing
an `async def execute(goal_handle) -> Result`. There is no abstract base class
to subclass; duck-typing is sufficient.

### 4. Make the per-kind package loadable

Append the import to `task_server_handlers/__init__.py` so registration fires
on package import:

```python
from . import goto_pose      # noqa: E402,F401
from . import follow_path    # noqa: E402,F401  # new
```

### 5. (Optional) Ship a Python client

Mirror `clients/goto_pose.py` as `clients/follow_path.py`. Clients are not
required — any consumer can talk to the raw action endpoint — but `task_generator`
and [DRIVING.md](../../../DRIVING.md) examples use them.

### 6. Wire into a `Bringup`

A `Bringup` advertises the task kinds it supports; the `task_server` iterates
that list at startup and looks up `HANDLERS.get((kind, bringup_kind))` for
each. A new task kind is visible as soon as at least one bringup declares it
and a matching handler is registered.

## Design invariants

- **`TaskKind` is closed.** The enum is the sole allowlist; `task_generator`,
  the `task_server`, and clients all key off it. Don't parametrise the set by
  config.
- **Handler registry is `(TaskKind, bringup_kind)`-keyed, not per-robot.**
  Robot-specific behaviour belongs in the handler's interpretation of the
  `Bringup` instance, not in a third registry axis.
- **Loaders stay zero-arg and lazy.** Putting the `nav2_msgs` import (or any
  other non-core msgs import) at module top level will break bringups that
  don't need it.
- **No fallback handlers.** `KeyError` at `HANDLERS.get` is the correct
  outcome for an unsupported `(kind, bringup)` pair — the `task_server` skips
  advertising that endpoint instead of silently degrading.
