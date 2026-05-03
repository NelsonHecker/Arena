import typing
from collections.abc import Mapping

import launch
import launch.launch_description_source


class IsolatedGroupAction(launch.actions.GroupAction):
    def __init__(self, actions: typing.Iterable[launch.Action], *args: object, **kwargs: object) -> None:
        return super().__init__(
            (
                launch.actions.PushEnvironment(),
                launch.actions.PushLaunchConfigurations(),
                *actions,
                launch.actions.PopLaunchConfigurations(),
                launch.actions.PopEnvironment(),
            ),
            *args,
            **kwargs,
        )


class IncludeLaunchDescriptionForward(launch.Action):
    """IncludeLaunchDescription that forwards every parent launch configuration to the child.

    `overrides` pin specific args (e.g. {'env_n': '0'}); they win over forwarded values.
    """

    def __init__(
        self,
        source: launch.launch_description_source.LaunchDescriptionSource,
        *,
        overrides: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._source = source
        self._overrides = dict(overrides) if overrides else {}

    def execute(self, context: launch.LaunchContext) -> list[launch.LaunchDescriptionEntity]:
        args = dict(context.launch_configurations)
        args.update(self._overrides)
        return [launch.actions.IncludeLaunchDescription(self._source, launch_arguments=args.items())]
