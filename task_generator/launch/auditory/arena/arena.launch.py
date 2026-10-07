import os

import launch
from ament_index_python.packages import get_package_share_directory
from arena_bringup.actions import IsolatedIncludeLaunchDescription

_PREFIX = 'auditory.'
_PASSTHROUGH = ('debug.map_source',)


def _include(context: launch.LaunchContext) -> list[launch.LaunchDescriptionEntity]:
    configs = context.launch_configurations
    forwarded = {key.removeprefix(_PREFIX): value for key, value in configs.items() if key.startswith(_PREFIX)}
    passthrough = {key: configs[key] for key in _PASSTHROUGH if key in configs}
    return [
        IsolatedIncludeLaunchDescription(
            os.path.join(
                get_package_share_directory('arena_auditory'),
                'launch/arena_auditory.launch.py',
            ),
            args={
                **forwarded,
                **passthrough,
                'namespace': configs.get('namespace', ''),
                'env.ns': configs.get('environment_namespace', ''),
                'hearing': configs.get('robot.hearing', 'none'),
            },
        ),
    ]


def generate_launch_description():
    return launch.LaunchDescription([launch.actions.OpaqueFunction(function=_include)])
