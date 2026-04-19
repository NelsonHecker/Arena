import typing

import launch


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
