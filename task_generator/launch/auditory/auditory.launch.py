import launch
from arena_bringup.substitutions import LaunchArgument, SelectAction
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from task_generator.constants import Constants


def generate_launch_description() -> launch.LaunchDescription:

    ld = []

    LaunchArgument.auto_append(ld)

    namespace = LaunchArgument(
        name='namespace',
    )

    environment_namespace = LaunchArgument(
        name='environment_namespace',
    )

    launch_auditory_simulator = SelectAction(launch.substitutions.LaunchConfiguration('simulator'))

    launch_auditory_simulator.add(Constants.AuditorySimulator.NONE.value, launch.actions.GroupAction([]))

    launch_auditory_simulator.add(
        Constants.AuditorySimulator.ARENA.value,
        launch.actions.IncludeLaunchDescription(
            PathJoinSubstitution(
                [
                    FindPackageShare('task_generator'),
                    'launch',
                    'auditory',
                    'arena',
                    'arena.launch.py',
                ]
            ),
            launch_arguments={
                **namespace.dict,
                **environment_namespace.dict,
            }.items(),
        ),
    )

    simulator = LaunchArgument(
        name='simulator',
        choices=launch_auditory_simulator.keys,
    )

    ld = launch.LaunchDescription(
        [
            *ld,
            launch_auditory_simulator,
        ]
    )
    return ld


if __name__ == '__main__':
    generate_launch_description()
