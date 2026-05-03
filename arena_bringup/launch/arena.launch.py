import launch
import launch.utilities
import launch.utilities.type_utils
import launch_ros.actions
from arena_bringup.actions import IsolatedGroupAction
from arena_bringup.extensions.NodeLogLevelExtension import SetGlobalLogLevelAction
from arena_bringup.future import PythonExpression
from arena_bringup.substitutions import LaunchArgument
from launch.actions import LogInfo, OpaqueFunction
from launch.substitutions import PathJoinSubstitution, TextSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    ld_items = []
    LaunchArgument.auto_append(ld_items)

    log_level = LaunchArgument(
        name='log_level',
        default_value='warn',
        description='Per-node log level. See launch README.',
    )

    robot = LaunchArgument(
        name='robot',
        default_value='jackal',
        description='robot model type'
    )
    inter_planner = LaunchArgument(
        name='inter_planner',
        default_value='navigate_w_replanning_time',
        description='inter planner type (Behavior Tree)'
    )
    local_planner = LaunchArgument(
        name='local_planner',
        default_value='dwb',
        description='local planner type [teb, dwa, mpc, rlca, arena, rosnav, cohan]'
    )
    global_planner = LaunchArgument(
        name='global_planner',
        default_value='navfn',
        description='global planner type [navfn]'
    )
    sim = LaunchArgument(
        name='sim',
        default_value='dummy',
    )
    navigator = LaunchArgument(
        name='navigator',
        default_value=PythonExpression([str({"dummy": "none"}), '.get("', sim.substitution, '", "nav2")']),
        description=(
            'default navstack adapter kind [nav2, none, ...]. '
            'per-robot ``navigator:`` in robot_setup YAML wins.'
        ),
    )
    headless = LaunchArgument(
        name='headless',
        default_value='0',
        choices=['-1', '0', '1', '2'],
        description='-1 = show all environments, 0 = show all, 1 = show only rviz, 2 = show nothing'
    )
    human = LaunchArgument(
        name='human',
        description='human simulator to use',
        default_value=PythonExpression([str({"dummy": "dummy", "gazebo": "hunav", "isaac": "hunav"}), '.get("', sim.substitution, '", "dummy")']),
    )
    record_data_dir = LaunchArgument(
        name='record_data_dir',
        default_value=''
    )
    tm_robots = LaunchArgument(
        name='tm_robots',
        default_value='explore'
    )
    task_config = LaunchArgument(
        name='task_config',
        default_value='',
        description=(
            'Path to a task_modes YAML config. '
            'Empty = synthesize from legacy ``tm_robots`` arg.'
        ),
    )
    tm_obstacles = LaunchArgument(
        name='tm_obstacles',
        default_value='random'
    )
    tm_modules = LaunchArgument(
        name='tm_modules',
        default_value='rviz_ui'
    )
    world = LaunchArgument(
        name='world',
        default_value='map_empty',
        description='world to load'
    )
    use_sim_time = LaunchArgument(
        name='use_sim_time',
        default_value='true',
        description='Use simulation clock if true'
    )
    env_n = LaunchArgument(
        name='env_n',
        default_value='1',
        description='Number of environments to spawn within simulator'
    )
    debug = LaunchArgument(
        name='debug',
        default_value='False',
        description='Enable debug features'
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
            'headless': PythonExpression([headless.substitution, '>0']),
        }.items(),
    )

    world_generator_node = launch_ros.actions.Node(
        package='arena_simulation_setup',
        executable='world_generator',
        name='world_generator',
        output='screen',
    )

    # Forward to arena_node as launch-arg strings the node will pass through
    # to its internal SpawnEnv calls. Kept in sync with task_generator.launch.py args.
    _env_arg_sources: list[LaunchArgument] = [
        sim, human, tm_obstacles, tm_robots, task_config, tm_modules,
        robot, inter_planner, local_planner, global_planner, navigator,
        world, record_data_dir, debug,
    ]

    def _build_arena_node(context: launch.LaunchContext) -> list[launch.LaunchDescriptionEntity]:
        def _resolve(la: LaunchArgument) -> str:
            return launch.utilities.perform_substitutions(
                context, launch.utilities.normalize_to_list_of_substitutions(la.substitution)
            )

        env_args = [f"{la.name}:={v}" for la in _env_arg_sources if (v := _resolve(la))]
        n = launch.utilities.type_utils.perform_typed_substitution(
            context,
            launch.utilities.normalize_to_list_of_substitutions(env_n.substitution),
            int,
        )
        h = int(_resolve(headless))

        return [launch_ros.actions.Node(
            package='arena_runtime',
            executable='arena_node',
            name='arena',
            namespace='',
            output='screen',
            parameters=[{
                'sim': _resolve(sim),
                'env_n': n,
                'env_headless': h,
                'env_args': env_args,
            }],
            on_exit=launch.actions.Shutdown(reason='arena runtime exited'),
        )]

    return launch.LaunchDescription([
        *ld_items,
        LogInfo(msg=[
            TextSubstitution(text="Starting arena bringup with env_n="),
            env_n.substitution,
        ]),
        SetGlobalLogLevelAction(log_level.substitution),
        IsolatedGroupAction([launch_sim]),
        OpaqueFunction(function=_build_arena_node),
        world_generator_node,
    ])
