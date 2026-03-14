import launch.actions
import launch.substitutions

from arena_bringup.substitutions import LaunchArgument
from launch import LaunchDescription


def generate_launch_description():
    ld = []
    LaunchArgument.auto_append(ld)
    log_level = LaunchArgument(
        name='log_level',
        default_value='debug',
        description='Logging level',
    )
    return LaunchDescription([
        *ld,
        launch.actions.ExecuteProcess(
            cmd=['bash', '-c', 'arena feature isaac launch'],
            sigterm_timeout=launch.substitutions.LaunchConfiguration('sigterm_timeout', default='5'),
            sigkill_timeout=launch.substitutions.LaunchConfiguration('sigkill_timeout', default='5'),
            on_exit=[launch.actions.Shutdown()],
            output='log',
        )
    ])
