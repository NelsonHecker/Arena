from __future__ import annotations

import abc
import typing

from copy import deepcopy

import cattrs


class ArenaConverter(cattrs.Converter):
    """Custom converter for Arena types that exposes an API for retrieving registered structure and unstructure hooks.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._encoders: typing.Dict[typing.Type, typing.Callable] = {}
        self._decoders: typing.List[typing.Tuple[typing.Callable[[typing.Type], bool], typing.Callable]] = []

    @property
    def type_encoders(self) -> typing.Dict[typing.Type, typing.Callable]:
        """
        Get the registered type encoders.

        Returns:
            Dict[Type, Callable]: A dictionary mapping types to their corresponding encoder functions.
        """
        return self._encoders

    @property
    def type_decoders(self) -> typing.List[typing.Tuple[typing.Callable[[typing.Type], bool], typing.Callable]]:
        """
        Get the registered type decoders.

        Returns:
            List[Tuple[Callable[[Type], bool], Callable]]: A list of tuples containing predicates and their corresponding decoder functions.
        """
        return self._decoders

    def register_unstructure_hook(self, cl, *args, **kwargs):
        """
        Register an unstructure hook for a given type.
        """
        if args:
            func = args[0]
            self._encoders[cl] = func
        return super().register_unstructure_hook(cl, *args, **kwargs)

    def register_structure_hook(self, cl, *args, **kwargs):
        """
        Register a structure hook for a given type.
        """
        if args:
            def predicate(t, c=cl): return issubclass(t, c)
            func = args[0]
            self._decoders.append((predicate, func))
        return super().register_structure_hook(cl, *args, **kwargs)


converter = ArenaConverter()


class Idempotent:
    """
    A class that ensures its instances are idempotent.
    """

    @classmethod
    def converter(cls, *args, **kwargs):
        """
        If the value is already an instance of the class , return it.
        Otherwise, create a new instance of the class with the value.
        """
        if args and isinstance(args[0], cls):
            return args[0]
        return cls(*args, **kwargs)

    @classmethod
    def converter_clone(cls, *args, **kwargs):
        """
        If the value is already an instance of the class , return a deepcopy of it.
        If not , create a new instance of the class with the value.
        """
        if args and isinstance(args[0], cls):
            return deepcopy(args[0])
        return cls(*args, **kwargs)


T = typing.TypeVar('T')


def idempotent(cls: typing.Type[T]):
    """
    Make class idempotent.
    """
    if not issubclass(cls, Idempotent):
        return type(cls.__name__, (Idempotent, cls), {})
    return cls

# Serialization and Deserialization


class Serializable(abc.ABC):
    """
    A base class for serializable objects.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if not getattr(cls, "__abstractmethods__", set()):
            def unstructure_hook(obj): return obj.serialize()
            converter.register_unstructure_hook(cls, unstructure_hook)

    @abc.abstractmethod
    def serialize(self) -> typing.Any:
        """
        Define the custom serialization logic for this object.
        The return value should be a primitive type(dict, list, str, int, etc.).
        """
        raise NotImplementedError


converter.register_unstructure_hook(Serializable, lambda obj: obj.serialize())

ParseableT = typing.TypeVar('ParseableT', bound='Parseable')


class Parseable(abc.ABC):
    """
    A base class for parseable objects.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if not getattr(cls, "__abstractmethods__", set()):
            def try_parse(data):
                if isinstance(data, cls):
                    return data
                try:
                    return converter.structure_attrs_fromdict(deepcopy(data), cls)
                except Exception:
                    return cls.parse(data)

            converter.register_structure_hook(
                cls,
                lambda data, _: try_parse(data)
            )

    @classmethod
    @abc.abstractmethod
    def parse(cls: typing.Type[ParseableT], value: typing.Any) -> ParseableT:
        raise NotImplementedError


__all__ = [
    "Serializable",
    "Parseable",
    "converter",
    "Idempotent",
]
