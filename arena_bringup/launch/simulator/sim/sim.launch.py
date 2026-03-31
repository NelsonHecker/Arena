import os

import launch.actions
import launch.launch_description_sources
import launch.substitutions
from ament_index_python.packages import get_package_share_directory

import launch
import launch_ros.actions
from arena_bringup.substitutions import LaunchArgument, SelectAction

from task_generator.constants import Constants


def generate_launch_description():

    ld = []
    LaunchArgument.auto_append(ld)

    use_sim_time = LaunchArgument(
        name='use_sim_time',
    )

    headless = LaunchArgument(
        name='headless',
        default_value='False',
    )

    # TODO temporary
    world = LaunchArgument(
        name='world'
    )

    launch_simulator = SelectAction(launch.substitutions.LaunchConfiguration('simulator'))

    launch_simulator.add(
        Constants.SimSimulator.DUMMY.value,
        launch.actions.GroupAction([
            launch_ros.actions.Node(
                package='tf2_ros',
                executable='static_transform_publisher',
                arguments=['--frame-id', 'map', '--child-frame-id', 'dummy'],
            ),
        ])
    )

    launch_simulator.add(
        Constants.SimSimulator.GAZEBO.value,
        launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                os.path.join(get_package_share_directory(
                    'arena_bringup'), 'launch/simulator/sim/gazebo/gazebo.launch.py')
            ),
            launch_arguments={
                **use_sim_time.dict,
                **headless.dict,
                **world.dict,
            }.items(),
        )
    )

    launch_simulator.add(
        Constants.SimSimulator.ISAAC.value,
        launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                os.path.join(get_package_share_directory(
                    'arena_bringup'), 'launch/simulator/sim/isaac/isaac.launch.py')
            ),
            launch_arguments={
                'use_sim_time': use_sim_time.substitution,
                # 'headless': headless.substitution
            }.items(),
        )
    )

    simulator = LaunchArgument(
        name='simulator',
        choices=launch_simulator.keys,
    )

    ld = launch.LaunchDescription([
        *ld,
        launch_simulator,
    ])
    return ld


if __name__ == '__main__':
    generate_launch_description()
