# Consolidate pedestrian visualization into BaseHumanSimulator

Currently pedestrian visualization is split across a separate node (`pedestrian_marker_publisher`) and the human sim implementations. This refactor moves all marker publishing into `BaseHumanSimulator` so implementations can publish both standard body markers and custom debug markers through a single pipeline.

## Context

- `arena_humansim` now publishes debug `MarkerArray` topics (`viz/perception`, `viz/global_plan`, etc.) from its ROS node
- These need to be forwarded into Arena's rviz ecosystem via the task_generator bridge
- The existing `pedestrian_marker_publisher` node subscribes to `arena_peds` (Pedestrians msg) and republishes as `pedestrian_markers` (MarkerArray) — this is a pointless hop since BaseHumanSimulator already has the data
- The `DELETEALL` marker in `pedestrian_marker_publisher` prevents other sources from co-publishing on the same topic

## Tasks

### 1. Add MarkerArray publisher to BaseHumanSimulator

**File:** `task_generator/simulators/human/__init__.py`

- Add `_marker_publisher: rclpy.publisher.Publisher` for `MarkerArray` on `{namespace}/pedestrian_markers`
- Add `publish_markers(self, markers: MarkerArray)` method

### 2. Move pedestrian→marker conversion into BaseHumanSimulator

**File:** `task_generator/simulators/human/__init__.py`

- Port `PedestrianMarkerPublisher.pedestrians_callback` logic into a method on BaseHumanSimulator (e.g. `_pedestrians_to_markers`)
- Modify `publish_arena_peds()` to also convert the Pedestrians msg to MarkerArray and publish via `_marker_publisher`
- Keep the same marker namespaces (`pedestrian_meshes`, `pedestrian_velocity`, `pedestrian_orientation`, `pedestrian_labels`) for rviz config compatibility
- Remove the `DELETEALL` marker — use marker lifetimes instead, since debug markers from implementations will share the topic

### 3. Remove pedestrian_marker_publisher node

**File:** `task_generator/launch/task_generator.launch.py`

- Remove the `pedestrian_marker_node` Node action (lines ~87-103)
- Remove its inclusion in the launch group (line ~179)

**File:** `utils/rviz_utils/rviz_utils/scripts/pedestrian_marker_publisher.py`

- Delete or deprecate. The logic now lives in BaseHumanSimulator.

### 4. Wire arena_humansim bridge to forward debug markers

**File:** `task_generator/simulators/human/arena_humansim/arena_humansim.py`

- In `__init__`, subscribe to the 7 `viz/*` MarkerArray topics from the humansim node (use `service_namespace` pattern for the topic prefix, same as services)
- In each subscription callback, forward received MarkerArray to `self.publish_markers()`
- Topics to subscribe to:
  - `viz/perception` — vision cones, observation lines
  - `viz/behavior` — command labels, need bars
  - `viz/global_plan` — A* paths, intermediate goals, goal arrows
  - `viz/local_plan` — velocity arrows
  - `viz/interaction` — participant links, labels
  - `viz/waypoints` — waypoint paths, active wp, acceptance radius
  - `viz/infrastructure` — sources, sinks, walls, world objects

### 5. Update rviz config generator

**File:** `utils/rviz_utils/rviz_utils/scripts/rviz_config.py`

- No changes needed — it already discovers `*/pedestrian_markers` topics. Since all markers now go through that topic, existing discovery works.

### 6. Verify other implementations

Check that these implementations still work (they call `publish_arena_peds` which will now also publish markers):

- `task_generator/simulators/human/dummy.py`
- `task_generator/simulators/human/hunav/hunav.py`
- `task_generator/simulators/human/isaac.py`

These don't publish custom debug markers, so they just get the standard body/velocity/label markers for free.

### 7. Parameters

The pedestrian_marker_publisher currently declares these parameters:
- `body_height` (1.6), `body_radius` (0.25), `head_radius` (0.15)
- `arrow_length` (0.6)
- `show_labels` (true), `show_velocity_arrows` (true), `show_orientation_arrows` (true)
- `mesh_resource` (path to .dae)

Decide whether to keep these as ROS parameters on the task_generator node or hardcode reasonable defaults. The mesh_resource path is the most important one to preserve.
