# Arena-Rosnav

A modular ROS 2 (Humble) platform for researching and benchmarking autonomous robot navigation in 2D and 3D simulated environments. It supports classical planners (Nav2), deep-RL planners ([rosnav_rl](https://github.com/Arena-Rosnav/rosnav-rl)), and a variety of simulators (Gazebo, Isaac Sim).

---

## Installation

Prerequisites: [Docker](https://docs.docker.com/engine/install/) installation with [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) for GPU support. Current user must be in group `docker`.
Afterwards, run the following commands to install Arena:

### Basic Installation

```sh
curl https://raw.githubusercontent.com/voshch/Arena/jazzy/install.sh > install.sh
bash install.sh
```
and follow the prompts. This will create a ROS 2 workspace at your target location and instruct you how to proceed (yellow text).


### Optional Features
```sh
cd ~/arena_ws # replace with your actual workspace path
source arena
arena feature isaac install # optional
arena feature gazebo install # optional
arena feature training install # optional
arena feature vllm install # optional: local LLM backend
```

We recommend installing at least one simulator.

#### vllm

Runs a local vLLM server plus a LiteLLM proxy that speaks the Gemini API, so GPT consumers in `task_generator` transparently hit local inference instead of Google. Defaults target an 11 GB 2080 Ti (Qwen3-0.6B, 40% GPU util).

Tune via [`_meta/docker/features/vllm/config.yaml`](_meta/docker/features/vllm/config.yaml):

| key | default | purpose |
| --- | --- | --- |
| `model` | `Qwen/Qwen3-0.6B` | HF model id |
| `gpu_memory_utilization` | `0.4` | fraction of VRAM vllm may claim |
| `max_model_len` | `4096` | context window |
| `port` / `proxy_port` | `8000` / `4000` | vllm / LiteLLM ports |

After editing, re-run `arena feature vllm update` to recreate the container.
The container will start automatically on source and continue running in the background. To free up GPU memory, stop it with `arena feature docker stop`.

## Usage

```sh
cd ~/arena_ws # replace with your actual workspace path
source arena
arena launch sim:=isaac                          # Isaac Sim
arena launch local_planner:=rosnav_rl agent_name:=<your_agent>  # DRL planner
arena launch sim:=gazebo local_planner:=rosnav_rl env_n:=2 train_config:=<path to config.yaml> # DRL training 
```

### DRL quick-start
Place your trained agent folder inside `Arena/arena_training/agents/<agent_name>/` (must contain `training_config.yaml` and `best_model.zip`), then launch with `local_planner:=rosnav_rl agent_name:=<agent_name>`. Refer to the [arena_training](arena_training/README.md) for training instructions.


## Troubleshooting

### Unknown runtime specified 'nvidia'

```sh
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd
```
