# Environment configs

An environment YAML defines named obstacle-group templates used by the
parametrized task mode to furnish free space in a world. Each file is a
`dict` resolved by `EnvironmentIdentifier`.

## Location and resolution

`EnvironmentIdentifier` is backed by `EnvironmentResolver`, which looks under
`ASS_DIR / 'configs' / 'environment'`
([tree/configs/environment.py:15](../../src/arena_simulation_setup/tree/configs/environment.py#L15)).

`ASS_DIR` is the installed share path of `arena_simulation_setup` (or the
`ASS_DIR` env var when `ament_index_python` is absent).

Name resolution: `EnvironmentIdentifier('hospital')` loads
`configs/environment/hospital.yaml`. The `shortname` property strips the
`.yaml` suffix.

## Schema

```yaml
groups:
  - name: office              # group name (referenced by task-mode config)
    margin: 3                 # clearance around the group footprint [m]
    size: [1.5, 1.5]          # bounding box of the group [m x m]
    rotations: [0, 180]       # allowed placement rotations [degrees]
    entities:
      static:
        - position: [0.0, 0.0, 0.0]   # [x, y, yaw_deg] relative to group origin
          model: office_desk           # ObjectIdentifier name
        - position: [1, 0, -90]
          model: office_chair
```

`EnvironmentDescription` is an untyped `dict` subclass; no validation beyond
top-level `dict` is performed at load time
([tree/configs/environment.py:32](../../src/arena_simulation_setup/tree/configs/environment.py#L32)).

## Shipped files

| File | Groups defined |
|---|---|
| `default.yaml` | `office`, `circle`, `cafeteria`, `residential`, `hospital`, `outdoor` |
| `hospital.yaml` | `hospital_reception` |
| `office.yaml` | office-specific groups |
| `canteen.yaml` | canteen-specific groups |

## Adding a new environment

Create `configs/environment/<name>.yaml` following the schema above. Reference
it by short name (without `.yaml`) wherever an `EnvironmentIdentifier` is
expected.
