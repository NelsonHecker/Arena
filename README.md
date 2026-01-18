## Installation

```sh
curl https://raw.githubusercontent.com/voshch/Arena/jazzy/install.sh > install.sh
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
arena launch sim:=isaac # add ros2 launch args as needed
```