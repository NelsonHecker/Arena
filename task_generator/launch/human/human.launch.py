import launch
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

from arena_bringup.substitutions import LaunchArgument, SelectAction

from task_generator.constants import Constants


def generate_launch_description():

    ld = []

    LaunchArgument.auto_append(ld)

    namespace = LaunchArgument(
        name='namespace',
    )

    launch_human_simulator = SelectAction(launch.substitutions.LaunchConfiguration('simulator'))

    launch_human_simulator.add(
        Constants.HumanSimulator.DUMMY.value,
        launch.actions.GroupAction([])
    )

    launch_human_simulator.add(
        Constants.HumanSimulator.NONE.value,
        launch.actions.GroupAction([])
    )

    launch_human_simulator.add(
        Constants.HumanSimulator.HUNAV.value,
        launch.actions.IncludeLaunchDescription(
            PathJoinSubstitution([
                FindPackageShare('task_generator'),
                'launch', 'human', 'hunav', 'hunav.launch.py',
            ]),
            launch_arguments={
                'use_sim_time': 'true',
                'world_file': '',
                **namespace.dict
            }.items(),
        )
    )

    launch_human_simulator.add(
        Constants.HumanSimulator.ARENA.value,
        launch.actions.IncludeLaunchDescription(
            PathJoinSubstitution([
                FindPackageShare('task_generator'),
                'launch', 'human', 'arena_humansim', 'arena_humansim.launch.py',
            ]),
            launch_arguments={
                'use_sim_time': 'true',
                **namespace.dict
            }.items(),
        )
    )

    simulator = LaunchArgument(
        name='simulator',
        choices=launch_human_simulator.keys,
    )

    ld = launch.LaunchDescription([
        *ld,
        launch_human_simulator,
    ])
    return ld


if __name__ == '__main__':
    generate_launch_description()
