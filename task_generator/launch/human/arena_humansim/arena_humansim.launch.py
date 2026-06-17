import os

import launch
from ament_index_python.packages import get_package_share_directory
from arena_bringup.actions import IsolatedIncludeLaunchDescription


def generate_launch_description():
    namespace = launch.substitutions.LaunchConfiguration('namespace', default='')

    return launch.LaunchDescription([
        IsolatedIncludeLaunchDescription(
            os.path.join(
                get_package_share_directory('arena_humansim'),
                'launch/arena_humansim.launch.py',
            ),
            args={
                'mode': 'subsystem',
                'use_sim_time': 'true',
                'markers': '2',
                'namespace': namespace,
            },
        ),
    ])
