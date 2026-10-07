# Auditory simulator dispatch

Entry point: [`auditory.launch.py`](auditory.launch.py).

Called from `task_generator.launch.py`'s OpaqueFunction (once per
environment, next to the human dispatch, only when `auditory` is not `none`)
with `simulator` (the auditory key), `namespace` and `environment_namespace`.
Its job is to select and delegate to one auditory backend. Every `auditory.*`
launch configuration of the parent stays visible to the backend.

## SelectAction dispatch

Keys are `Constants.AuditorySimulator` values:

| Key | Action |
| --- | --- |
| `none` | empty group, no nodes |
| `arena` | includes [`arena/arena.launch.py`](arena/arena.launch.py) |

Selected with `auditory:=<key>` at the top level.

## arena backend

[`arena/arena.launch.py`](arena/arena.launch.py) is a shim like
`human/arena_humansim/arena_humansim.launch.py`. It strips the `auditory.`
prefix from every launch configuration that carries it and includes
`arena_auditory`'s `launch/arena_auditory.launch.py` in isolation with:

| Arg | Value |
| --- | --- |
| `<key>` | `auditory.<key>` of the parent, forwarded as node param `<key>` to every stack node |
| `namespace` | task generator node namespace, the stack nodes live below it |
| `env.ns` | absolute env namespace |
| `hearing` | `robot.hearing`, `srp` and `seld` default `array.spec` to `four_mic` |

Empty values keep the node default from `arena_auditory/params.py`. The
nodes, their parameters and topics are documented in the
[arena_auditory README](../../../arena_auditory/README.md).

## Node side

`task_generator/simulators/auditory/` mirrors the human registry:
`AuditorySimulatorRegistry` yields a `BaseAuditorySimulator` per key. The
backend class declares what the task generator must provide, today only
`requires_map_server`, which the arena backend sets because the propagation
node builds its acoustic scene from the map topic. `displays()` yields the
RViz displays of the backend.

## Layout

```
launch/auditory/
|-- auditory.launch.py     dispatcher
`-- arena/
    `-- arena.launch.py    shim into arena_auditory's arena_auditory.launch.py
```

The nodes live in the `arena_auditory` package, the auditory feature
(`arena feature auditory install`). Without it, any launch that enables the
sounds module (`auditory:=arena`, `robot.hearing`, `auditory.static_sounds`
or `task.modules:=sounds`) fails before spawning with an install hint.
