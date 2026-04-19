# Navigation adapters (task_generator Python half)

task_generator's `Adapter` ABC composes an `arena_robots.bringup.Bringup` and
an `arena_robots.clients.Client`. It maps scenario Phases to arena IDL goals
and dispatches them through the Client — the same path any external consumer
uses. See [arena_robots/DRIVING.md](../../../../../arena_robots/DRIVING.md) for
the public API.

## The `Adapter` ABC

Defined in [`__init__.py`](__init__.py):

```python
@register_adapter
class MyAdapter(Adapter):
    kind       = "my_stack"              # matches Bringup.kind
    accepts    = frozenset({TaskKind.GOTO_POSE})
    bringup_cls = MyBringup
    client_cls  = GotoPoseClient

    async def dispatch_phase(self, phase, robot) -> None:
        goal = GotoPose.Goal()
        goal.target = self._phase_to_pose_stamped(phase)
        await self.client.send_goal(goal)
```

The base class constructor builds `self.bringup` and `self.client` from
`bringup_cls` / `client_cls`; subclasses only implement `dispatch_phase`.

`is_phase_done` polls `self.client.is_done()`. `on_episode_end` calls
`self.client.cancel()`. Override only when the default is wrong for your stack.

## Existing kinds

| File | Bringup | Client |
|---|---|---|
| `nav2.py` | `Nav2Bringup` | `GotoPoseClient` |
| `none.py` | `NoneBringup` | `GotoPoseClient` |
| `external.py` | `ExternalBringup` | `GotoPoseClient` |

`ExternalBringup` reads `goal_topic`, `cmd_vel_topic`, `launch_file`,
`requires`, and `extra` from `caps/mobile.yaml > external:` — configure them
there, not as constructor arguments.

## Adding a new adapter kind

1. Create `arena_robots/bringup/<kind>.py` — `Bringup` subclass with `kind`,
   `requires`, and `launch_description()`.
2. Add handler(s) in `arena_robots/task_server_handlers/<task_kind>/<kind>.py`,
   then register a lazy loader in the per-kind `__init__.py`:
   `@HANDLERS.register((TaskKind.GOTO_POSE, "<kind>"))`
   The loader imports the module and returns the handler class, so its msgs
   deps are only pulled when the bringup is selected at runtime.
3. Create `task_generator/tasks/robots/adapters/<kind>.py` — `Adapter`
   subclass with `kind`, `accepts`, `bringup_cls`, `client_cls`, and
   `dispatch_phase`.
4. Eager-import the new module from `RobotManager.__init__` so registration
   fires before `get_adapter` runs.
5. Set `navigator: <kind>` in a robot's `model_params.yaml`.
