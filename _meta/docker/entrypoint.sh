#!/bin/bash -i

source /opt/venv/bin/activate
source /opt/ros/jazzy/setup.bash || echo 'Warning: could not source ROS2 jazzy setup.bash'
source /opt/arena_ws/install/local_setup.bash || echo 'Warning: could not source arena_ws local_setup.bash'
cd /opt/arena_ws

exec "$@"