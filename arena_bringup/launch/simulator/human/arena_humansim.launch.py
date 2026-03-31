import os

import launch
import launch_ros.actions
from ament_index_python.packages import get_package_share_directory
from arena_bringup.actions import IsolatedGroupAction


def generate_launch_description():
    namespace = launch.substitutions.LaunchConfiguration('namespace', default='')

    return launch.LaunchDescription([
        IsolatedGroupAction([
            launch_ros.actions.PushRosNamespace(namespace),
            launch.actions.IncludeLaunchDescription(
                os.path.join(
                    get_package_share_directory('arena_humansim'),
                    'launch/arena_humansim.launch.py',
                ),
                launch_arguments={
                    'mode': 'subsystem',
                    'use_sim_time': 'true',
                    'markers': 'true',
                }.items(),
            ),
        ]),
    ])
