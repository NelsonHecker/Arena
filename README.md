# Arena-Rosnav

A modular ROS 2 (Humble) platform for researching and benchmarking autonomous robot navigation in 2D and 3D simulated environments. It supports classical planners (Nav2), deep-RL planners ([rosnav_rl](https://github.com/Arena-Rosnav/rosnav-rl)), and a variety of simulators (Gazebo, Isaac Sim).

---

## Installation

```sh
curl https://raw.githubusercontent.com/voshch/Arena/humble/install.sh > install.sh
bash install.sh

cd ~/arena5_ws # replace with your actual workspace path
source arena
arena update
arena build
arena feature gazebo install # optional
arena feature isaac install # optional
```

## Usage

```sh
cd ~/arena5_ws # replace with your actual workspace path
source arena
arena launch sim:=gazebo                         # default — Gazebo simulator
arena launch sim:=isaac                          # Isaac Sim
arena launch local_planner:=rosnav_rl agent_name:=<your_agent>  # DRL planner
```

### Key launch arguments

| Argument | Default | Description |
|---|---|---|
| `sim` | `gazebo` | Simulator backend (`gazebo` / `isaac`) |
| `local_planner` | `teb` | Local planner (`teb` / `dwa` / `rosnav_rl` / …) |
| `agent_name` | `''` | DRL agent directory name under `arena_training/agents/` (required when `local_planner:=rosnav_rl`) |
| `train_mode` | `false` | Set `true` during active training — suppresses the RL action server |
| `global_planner` | `navfn` | Global planner |

> **DRL quick-start**: place your trained agent folder inside `Arena/arena_training/agents/<agent_name>/` (must contain `training_config.yaml` and `best_model.zip`), then launch with `local_planner:=rosnav_rl agent_name:=<agent_name>`.