import typing

Key = typing.TypeVar('Key')
Value = typing.TypeVar('Value')


class Registry[Key, Value]:
    __registry: dict[Key, typing.Callable[..., typing.Awaitable[Value]]]
    __name: str

    def __init__(self, entries: dict[Key, typing.Callable[..., typing.Awaitable[Value]]] | None = None) -> None:
        if entries is None:
            entries = {}

        self.__name = Value.__name__
        self.__registry = {**entries}

    def register(self, name: Key) -> typing.Callable[[typing.Callable[..., typing.Awaitable[Value]]], typing.Callable[..., typing.Awaitable[Value]]]:
        def inner_wrapper(class_loader: typing.Callable[..., typing.Awaitable[Value]]) -> typing.Callable[..., typing.Awaitable[Value]]:
            assert name not in self.__registry, f"{self.__name} '{name}' already exists!"

            self.__registry[name] = class_loader
            return class_loader

        return inner_wrapper

    def get(self, name: Key, /, *args: object, **kwargs: object) -> typing.Awaitable[Value]:
        assert name in self.__registry, f"{self.__name} '{name}' is not registered!"

        instance_future = self.__registry[name](*args, **kwargs)

        return instance_future
