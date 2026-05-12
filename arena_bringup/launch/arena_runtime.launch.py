import launch
import launch_ros.actions
from arena_bringup.actions import IsolatedGroupAction
from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
from arena_bringup.substitutions import LaunchArgument
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    ld_items = []
    LaunchArgument.auto_append(ld_items)

    log_level = LaunchArgument(
        name='log_level',
        default_value='warn',
        description='Per-node log level. See launch README.',
    )

    sim = LaunchArgument(
        name='sim',
        default_value='dummy',
    )

    use_sim_time = LaunchArgument(
        name='use_sim_time',
        default_value='true',
    )

    world = LaunchArgument(
        name='world',
        default_value='map_empty',
    )

    headless = LaunchArgument(
        name='headless',
        default_value='0',
    )

    launch_sim = launch.actions.IncludeLaunchDescription(
        PathJoinSubstitution([
            FindPackageShare('arena_bringup'),
            'launch', 'simulator', 'sim', 'sim.launch.py',
        ]),
        launch_arguments={
            **use_sim_time.dict,
            **sim.dict,
            **world.dict,
            'headless': headless.substitution,
        }.items(),
    )

    arena_node = launch_ros.actions.LifecycleNode(
        package='arena_runtime',
        executable='arena_node',
        name='arena',
        namespace='',
        output='screen',
        parameters=[{'sim': sim.substitution}],
    )

    return launch.LaunchDescription([
        *ld_items,
        SetGlobalLogLevelAction(log_level.substitution),
        IsolatedGroupAction([launch_sim]),
        arena_node,
    ])


if __name__ == '__main__':
    generate_launch_description()
