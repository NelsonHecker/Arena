import launch.actions
import launch.substitutions
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

import launch
import launch_ros.actions
from arena_bringup.substitutions import LaunchArgument, SelectAction

from arena_runtime.constants import SimSimulator


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

    world = LaunchArgument(
        name='world'
    )

    launch_simulator = SelectAction(launch.substitutions.LaunchConfiguration('sim'))

    launch_simulator.add(
        SimSimulator.DUMMY.value,
        launch.actions.GroupAction([
            launch_ros.actions.Node(
                package='tf2_ros',
                executable='static_transform_publisher',
                arguments=['--frame-id', 'map', '--child-frame-id', 'dummy'],
            ),
        ])
    )

    launch_simulator.add(
        SimSimulator.GAZEBO.value,
        launch.actions.IncludeLaunchDescription(
            PathJoinSubstitution([
                FindPackageShare('arena_bringup'),
                'launch', 'simulator', 'sim', 'gazebo', 'gazebo.launch.py',
            ]),
            launch_arguments={
                **use_sim_time.dict,
                **headless.dict,
                **world.dict,
            }.items(),
        )
    )

    launch_simulator.add(
        SimSimulator.ISAAC.value,
        launch.actions.IncludeLaunchDescription(
            PathJoinSubstitution([
                FindPackageShare('arena_bringup'),
                'launch', 'simulator', 'sim', 'isaac', 'isaac.launch.py',
            ]),
            launch_arguments={
                'use_sim_time': use_sim_time.substitution,
                # 'headless': headless.substitution
            }.items(),
        )
    )

    sim = LaunchArgument(
        name='sim',
        choices=launch_simulator.keys,
    )

    ld = launch.LaunchDescription([
        *ld,
        launch_simulator,
    ])
    return ld


if __name__ == '__main__':
    generate_launch_description()
