# arena_runtime

Arena-Rosnav runtime: the `arena_node` lifecycle node (env registry, holds, cleanup) plus the per-simulator adapters (gazebo, isaac, dummy).

`task_generator` (the per-env episode loop) consumes this package; the dep graph is one-way.

See [arena_runtime/README.md](arena_runtime/README.md) for the runtime primitives and service / topic surface, and [arena_runtime/sim/README.md](arena_runtime/sim/README.md) for the `BaseSim` interface.
