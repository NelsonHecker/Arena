# Authoring a new world

End-to-end guide for creating a world that Arena can load. Covers the manual
path; see [scripts/generate_world](scripts/generate_world)
for the AI-assisted generation pipeline.

## Prerequisites

- Arena workspace built (`colcon build`).
- `arena_simulation_setup` on `$AMENT_PREFIX_PATH`.
- `touch_world` script available: `ros2 run arena_simulation_setup touch_world`.

## 1. Create the world directory

```bash
export WORLD=my_world
mkdir -p \
    $ARENA_DIR/arena_simulation_setup/worlds/$WORLD/map \
    $ARENA_DIR/arena_simulation_setup/worlds/$WORLD/scenarios/default \
    $ARENA_DIR/arena_simulation_setup/worlds/$WORLD/assets
```

`$ARENA_DIR` is the workspace source root. If unset, `touch_world` uses the
current working directory.

## 2. Author `world.yaml`

Create `worlds/$WORLD/world.yaml`. The minimum valid file is one zone with
corners and at least one wall:

```yaml
zones:
- name: main_room
  description: Main room
  material:
  - Concrete_Smooth
  - {}
  corners:
  - {x: 0.0, y: 0.0, z: 0.0}
  - {x: 10.0, y: 0.0, z: 0.0}
  - {x: 10.0, y: 10.0, z: 0.0}
  - {x: 0.0, y: 10.0, z: 0.0}
  walls:
  - start: {x: 0.0, y: 0.0, z: 0.0}
    end:   {x: 10.0, y: 0.0, z: 0.0}
    material: {name: Plaster_Wall, domain: Common, _modifiers: null}
  - start: {x: 10.0, y: 0.0, z: 0.0}
    end:   {x: 10.0, y: 10.0, z: 0.0}
    material: {name: Plaster_Wall, domain: Common, _modifiers: null}
  - start: {x: 10.0, y: 10.0, z: 0.0}
    end:   {x: 0.0, y: 10.0, z: 0.0}
    material: {name: Plaster_Wall, domain: Common, _modifiers: null}
  - start: {x: 0.0, y: 10.0, z: 0.0}
    end:   {x: 0.0, y: 0.0, z: 0.0}
    material: {name: Plaster_Wall, domain: Common, _modifiers: null}
  doors: []
  elevators: []
  entities:
    static: []
    dynamic: []
```

Key points:

- `corners` is an ordered polygon; its interior is the navigable floor.
- Each `walls:` entry needs at least `start`, `end`, and either `material` or
  `kind`. Use `kind: <name>` to reference a `WallIdentifier` asset; omit
  `kind` for an inline material.
- `material` on a zone accepts the same forms as `MaterialIdentifier`: a plain
  string `Concrete_Smooth`, or a two-element list `[name, modifiers_dict]`.
- Multiple zones share a single flat `zones` list. Zone boundaries are defined
  only by their `corners` polygon and their `walls` list, with no explicit
  parent-child relationship.
- An empty material opts a surface out entirely: `material: ''` on a zone
  spawns no floor, `ceiling_material: ''` no ceiling, `material: ''` on a
  wall entry drops that wall, and `wall_material: ''` on every zone of a
  level suppresses the occupancy-detected collision walls. The short keys
  `mat`, `ceiling_mat`, `wall_mat` are accepted as aliases.

### Ceilings

Add a ceiling to any zone with these optional keys:

```yaml
  ceiling: true                # true by default, set false to leave the zone open
  ceiling_height: 3.0          # top height in metres, omit to derive from wall stack
  ceiling_cast_shadows: false  # false by default, true to let the ceiling occlude light
  ceiling_material:            # MaterialIdentifier, defaults to Concrete_Smooth
  - Concrete_Smooth
  - {}
```

With `ceiling_height` absent, the height is the tallest wall top in the zone
(`max(segment.start.z + segment.height)` over the zone walls), falling back to
`2.0` m when the zone has no walls.

Ceilings are opaque from below and transparent from above. They are visual-only
(no collision). With `ceiling_cast_shadows` false the ceiling does not occlude
the sun, so interiors stay lit without global illumination.

### Semantic annotations

Door and elevator state is intrinsic: every spawned door/elevator publishes
its full vocabulary (`state`/`progress`/`open`/... for a door; `arriving_eta`,
`occupants`, `cabin_door`, `cabin_door_progress`, ... for an elevator) with no
annotation needed. `semantics:` on a `doors:`/`elevators:` entry is only for
attaching a *scripted* kind (`gate`, `pressure_plate`) to that entry. Zones
accept an optional `semantics:` list of literal state/predicate primitives:

```yaml
zones:
- name: lobby
  corners: [...]
  semantics:
  - {state: max_speed, value: 1.5}
  - {predicate: quiet, value: true}
```

An `Elevator` entry configures its fire-recall regime as a first-class field,
not a semantics annotation:

```yaml
elevators:
- name: 1_elevator
  position: {x: 5.0, y: 0.0, z: 0.0}
  destination: "2.2_elevator"
  recall_on: alarm
```

Full field reference: [worlds/README.md](worlds/README.md).

### M2 kinds, params, and timelines

M2 adds scriptable/derived kinds on top of the intrinsic `door`/`elevator`
vocabularies and `zone`. Each kind takes its config under a `params:` dict on
the primitive or preset item, which round-trips opaquely (omitted on
serialize when empty):

| kind | attaches to | preset expansion | `params` keys |
| --- | --- | --- | --- |
| `signal` | a standalone `signals:` entry (zone-level) | `state`, `phase_remaining`, `stop` | `phases` (list of `{name, duration}`), `stop_phases`, `regime` |
| `schedule` | a standalone `schedules:` entry (zone-level) | `state`, `active`, `window_remaining` | `windows` (list of `{start, end, value}`), `default`, `regime` |
| `gate` | a `doors:` entry | `locked`, `blocked` | `authorized` (sim_paths/robot names), `unlock_on`, `locked` (initial value) |
| `pressure_plate` | a `doors:`/`elevators:` entry (own `position`) | `pressed` | `position` (`[x, y]`), `radius`, `drives`, `latch`, `press_on`, `regime` |
| `occupancy_cap` | a `zones:` entry | `occupancy`, `cap`, `over_cap` | `cap` |
| `sound` | a standalone `sounds:` entry (zone- or scenario-level) | `sounding`, `volume_db` | `sound_on`, `regime`, `sounding`/`volume_db` (initial values) |

`signal`, `schedule`, and `sound` have no wall/door geometry of their own, so
a zone carries them as sibling lists to `doors:`/`elevators:`. A `sound`
still needs a placement: exactly one of `position` (`[x, y]`), `entity_ref`
(name of a static entity in the same world, whose yaw frame `offset` is
applied in) or `frame` (a TF frame the sound rides, `offset` local to it, so
`frame: jackal/base_link` is a speaker bolted to that robot).

```yaml
zones:
- name: lobby
  corners: [...]
  schedules:
  - name: fire_alarm
    semantics:
    - {preset: schedule, params: {windows: [], regime: alarm}}
  signals:
  - name: crosswalk_light
    semantics:
    - {preset: signal, params: {phases: [{name: go, duration: 20.0}, {name: stop, duration: 10.0}]}}
  sounds:
  - name: hall_siren
    asset_id: alarm_loop
    position: [4.0, 2.3]
    semantics:
    - {preset: sound, params: {sound_on: alarm, volume_db: 88.0}}
```

A preset `params:` key that names one of the preset's own primitives
(`volume_db`, `sounding`, `locked`, ...) becomes that primitive's initial
`value` instead of a shared param, so `{preset: sound, params: {sounding:
true, volume_db: 62.0}}` is a radio that plays from the start at 62 dB. A
top-level `value:` on a preset item that expands to more than one primitive
is rejected at load: there is no single primitive it could mean.

A scenario may carry its own `sounds:` list with the same schema. Those are
episode-scoped: attached at reset, gone at the next one, and their
`entity_ref` may also name one of the scenario's own `static:` obstacles.

#### Pedestrian stimuli

A sound that propagation marks audible for a pedestrian reaches humansim as a
stimulus named after the catalog `category` of its `asset_id` (`alarm_loop`
has `category: alarm`, so its stimulus is `alarm`). An agent type opts in by
declaring a need of that name and a `transitions:` entry on it, and humansim
sets that need to 100 once the agent's sampled `reaction_time` has elapsed,
so the transition fires. Agent types without such a need ignore the sound.
See
[worlds/hospital_1/scenarios/fire_alarm_evacuation](worlds/hospital_1/scenarios/fire_alarm_evacuation/scenario.yaml)
for the reference: the `evacuee` agent type idles until `alarm` rises, then
walks to the static `exit` object.

`gate` and `pressure_plate` reuse an existing `doors:`/`elevators:` entry as
their attachment point, `occupancy_cap` reuses a `zones:` entry, all via the
same `semantics:` list. A `gate` should spawn unlocked (`locked: false` in its
params): the world is shared by every scenario, so a gate that defaulted to
locked would block scenarios that never touch its regime. A scenario that
wants the door locked at episode start says so explicitly in its `timeline:`
(see below), leaving the world itself inert:

```yaml
doors:
- name: door_edge_1_1
  start: {x: 4.0, y: 1.55, z: 0.0}
  end:   {x: 4.0, y: 2.45, z: 0.0}
  semantics:
  - {preset: gate, params: {authorized: [], unlock_on: alarm, locked: false}}
  - {preset: pressure_plate, params: {position: [4.0, 2.0], press_on: alarm, drives: door_edge_1_1}}
```

A `regime` (or its per-kind alias `unlock_on`/`press_on`) names a boolean
asserted by a scripted kind's driving predicate. Other kinds (gate,
pressure_plate) consult that name without a direct wire between the two
entities. A `sound` consumes a regime the same way, via its `sound_on` alias.
An elevator's `recall_on` field is the same regime-consult
mechanism, just wired as a first-class `Elevator` field instead of a
`semantics:` alias, since recall is mechanism configuration rather than
published state. See the fire-alarm worked example below.

### Scenario timelines

`scenario.yaml` accepts an optional `timeline:` list. Each entry fires a `set`
action list of `{entity, field, value}` writes against exactly one trigger:

| trigger | meaning |
| --- | --- |
| `at: <seconds>` | fire once at episode second `t` |
| `every: <seconds>` | fire each period, optional `offset`/`until` |
| `when: {entity, field, is}` | fire on the false-to-true edge of a semantic value |

```yaml
timeline:
- at: 0.0
  set:
  - {entity: door_edge_1_1, field: locked, value: "true"}
- at: 12.0
  set:
  - {entity: fire_alarm, field: active, value: "true"}
```

The world's `door_edge_1_1` spawns unlocked, and this scenario locks it at
`t=0` so the corridor starts sealed. At `t=12s` the `fire_alarm` schedule's `active` predicate goes true and
asserts regime `alarm`: a gate with `unlock_on: alarm` reports `locked=false`,
a pressure plate with `press_on: alarm` reports `pressed=true` and holds its
`drives` door open, and an elevator with `recall_on: alarm` refuses calls and
holds its cabin door open, all as pure regime consults with no per-effect
timeline entry. See
[worlds/three_storied_residential/scenarios/fire_alarm/scenario.yaml](worlds/three_storied_residential/scenarios/fire_alarm/scenario.yaml)
for the reference timeline.

## 3. Generate the map

```bash
touch_world my_world
```

This reads `worlds/my_world/world.yaml`, renders a PNG via
`WorldDescription.render()`, and writes:
- `map/map.png`
- `map/map.yaml`

To regenerate after editing `world.yaml`:

```bash
touch_world my_world
```

To regenerate with visible static obstacle footprints:

```bash
touch_world my_world \
    --assets red \
    --assets-label blue \
    --assets-bbox "((-.5, .5), (-.5, .5))"
```

To regenerate all files (including `world.yaml` itself, e.g. after schema
changes):

```bash
touch_world my_world --all
```

`touch_world` accepts `--resolution <float>` (metres per pixel, default `0.05`).

## 4. Add a scenario

Create `worlds/$WORLD/scenarios/default/scenario.yaml`:

```yaml
static: []
dynamic: []
robots:
  - start: [1.0, 1.0, 0.0]
    goal:  [8.0, 8.0, 0.0]
```

An empty scenario (robot start/goal only) is valid. Add static obstacles by
listing `Obstacle` entries under `static:`, dynamic pedestrians under `dynamic:`.
A static entry's flat top-level keys `type`, `capacity`, `satisfies`,
`interaction_radius` and `formation` are forwarded to humansim as its
WorldObject, so a `go_to` step or an interaction `target:` can name the
entry by `type`.

For HumanSim (arena_humansim) pedestrians include an `agent:` block. The
`agent_type` is either a built-in type (`adult`, `elder`) or a path-relative
agent-type YAML file (`./doctor.yaml`) defining scripted behavior
(sequences, interactions):

```yaml
dynamic:
- name: agent_1
  model: female_adult_medical_01
  agent: {agent_type: adult, desired_velocity: 1.2}
  pose: [2.0, 5.0, 0.0]   # yaw in radians
  waypoints:
  - [2.0, 5.0, 0.0]
  - [8.0, 5.0, 0.0]
```

See [worlds/README.md](worlds/README.md) for the full
scenario schema.

## 5. Add world-local assets (optional)

Assets placed in `worlds/$WORLD/assets/` are resolved before network-fetched
assets. To ship a custom wall style:

```bash
mkdir -p worlds/$WORLD/assets/Common/Wall/my_style
# create worlds/$WORLD/assets/Common/Wall/my_style/my_style.yaml
```

Then reference it in `world.yaml` walls as `kind: my_style`.

Wall preset YAML schema: [configs/walls/README.md](configs/walls/README.md).

## 6. Generate with the AI pipeline (alternative)

[scripts/generate_world](scripts/generate_world) posts a
natural-language prompt to a generation server and extracts the resulting zip
into a world directory:

```bash
generate_world "A hospital floor with 4 patient rooms and a central hallway" \
    --endpoint http://localhost:5501 \
    --outdir my_world
```

`--outdir` is resolved relative to `<arena_simulation_setup share>/worlds/` if
it is not an absolute path. The server must be running separately; this script
is a thin client.

After generation, run `touch_world my_world` to ensure `map/` is current.

## 7. Validate

```python
from arena_simulation_setup.tree.World.World import WorldIdentifier

world = WorldIdentifier('my_world').resolve_sync()
desc = world.load()
print(f"{len(desc.zones)} zone(s), "
      f"{sum(1 for _ in desc.all_walls)} wall segments")
```

This will raise `FileNotFoundError` if `world.yaml` is missing, and `ValueError`
or `cattrs` errors if the YAML is malformed.

List all scenarios:

```python
for scenario_id in world.scenario.listall():
    print(scenario_id.name)
```

Load a scenario:

```python
scenario = world.scenario('default').resolve_sync()
print(scenario.load())
```
