# Temporary Blender Pedestrian Replacement Script (Clean Native Rigged glTF)

This folder contains the temporary utility script `replace_pedestrians.py` designed to swap pedestrian models inside existing Arena Evaluation 3.0 `.blend` files in-place without re-running simulation benchmarks.

## The Clean Native Industry-Standard Architecture
- **Single Rigged glTF 2.0 (.glb)**: Each character is stored as a single binary containing `1 Mesh + 1 Armature + Actions ("Walk", "Idle")`.
- **Native Blender GPU Skinning**: Blender 4/5 imports the Armature and deforms the mesh natively in C++ on the GPU with full volume preservation and proper normals.
- **Faceted Shading & Skin Discoloration Fix**: Split normals are preserved from Collada source geometry, and materials have `Alpha Hashed` transparency enabled (`blend_method = 'HASHED'`). Hair, eyelashes, and eyebrow texture cards render with transparent backgrounds rather than opaque black borders.
- **Zero Shape Keys & Zero Sitting**: No multi-phase GLB slicing or shape-key blending loops. Characters possess only `Walk` and `Idle` actions.
- **Root Trajectory Preservation**: The root empty object (`Pedestrian_{pid}`) and all its trajectory animation keyframes (`location`, `rotation_euler`, velocity, timestamps) remain 100% untouched. The Armature is parented to the empty at `(0, 0, 0)`.
- **Automatic Motion Detection**: Pedestrians with cumulative displacement $> 0.15\,\text{m}$ along their path are automatically assigned the `"Walk"` action; stationary observers are assigned `"Idle"`.

## Generated Rigged Assets Available in Cache (`u:/data/blender_cache/glb/`)
- `Common_arenian_rigged.glb`
- `Common_worker_male_asian_middleage_rigged.glb`
- `Common_worker_male_caucasian_young_rigged.glb`
- `Hospital_nurse_female_caucasian_young_rigged.glb`
- `Office_office_female_african_young_rigged.glb`
- `Office_office_female_asian_young_rigged.glb`
- `Office_office_female_caucasian_young_rigged.glb`
- `Office_office_male_african_middleage_rigged.glb`
- `Office_office_male_african_young_rigged.glb`
- `Office_office_male_asian_middleage_rigged.glb`
- `Office_office_male_caucasian_middleage_rigged.glb`
- `Office_office_male_caucasian_young_rigged.glb`

## How to Run

### Method 1: Using an explicit mapping
```bash
python u:/src/Arena/arena_blender_viz/temp/replace_pedestrians.py \
    --blend u:/data/blender/hospital_1/hospital_1_plain.blend \
    --mapping "0:Hospital/nurse_female_caucasian_young,1:Common/Human/worker_male_caucasian_young,2:Office/office_female_caucasian_young" \
    --output u:/data/blender/hospital_1/hospital_1_plain_updated.blend
```

### Method 2: Using a scenario YAML file
```bash
python u:/src/Arena/arena_blender_viz/temp/replace_pedestrians.py \
    --blend u:/data/blender/hospital_1/hospital_1_plain.blend \
    --scenario u:/src/Arena/arena_simulation_setup/worlds/hospital_1a/scenarios/fig8_hospital_door_dilemma/scenario.yaml \
    --output u:/data/blender/hospital_1/hospital_1_plain_updated.blend
```

*(If `--output` is omitted, the `.blend` file is updated in-place).*
