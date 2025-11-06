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
            def predicate(t, c=cl):
                try:
                    return isinstance(t, type) and issubclass(t, c)
                except TypeError:
                    return False
            func = args[0]
            self._decoders.insert(0, (predicate, func))
            # return super().register_structure_hook_func(predicate, func)
        return super().register_structure_hook(cl, *args, **kwargs)


converter = ArenaConverter()

IdempotentT = typing.TypeVar('IdempotentT', bound='Idempotent')


class Idempotent:
    """
    A class that ensures its instances are idempotent.
    """

    @classmethod
    def _compatible(cls: typing.Type[IdempotentT], obj: typing.Any) -> typing.Optional[IdempotentT]:
        """
        Check if the object is compatible with the class.
        """
        if isinstance(obj, cls) or issubclass(type(obj), cls) or typing.get_origin(type(obj)) is cls:
            return obj
        return None

    @classmethod
    def instance_or(cls: typing.Type[IdempotentT], *chain: typing.Callable):
        def inner(v: typing.Any) -> IdempotentT:
            for fn in (cls._compatible, *chain):
                if (inst := fn(v)) is not None:
                    return inst
            raise ValueError(f'Cannot convert {v} to {cls}')
        return inner

    @classmethod
    def converter(cls: typing.Type[IdempotentT], *args, **kwargs) -> IdempotentT:
        """
        If the value is already an instance of the class , return it.
        Otherwise, create a new instance of the class with the value.
        """
        if args and (inst := cls._compatible(args[0])):
            return inst
        return cls(*args, **kwargs)

    @classmethod
    def converter_clone(cls: typing.Type[IdempotentT], *args, **kwargs) -> IdempotentT:
        """
        If the value is already an instance of the class , return a deepcopy of it.
        If not , create a new instance of the class with the value.
        """
        if args and (inst := cls._compatible(args[0])):
            return deepcopy(inst)
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
        """
        raise NotImplementedError


ParseableT = typing.TypeVar('ParseableT', bound='Parseable')


class Parseable(abc.ABC):
    """
    A base class for parseable objects.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if not getattr(cls, "__abstractmethods__", set()):

            def try_parse(value, target_type):
                errors = []
                # check idempotence
                try:
                    if isinstance(value, target_type):
                        return value
                except TypeError as e:
                    errors.append(e)

                # try Parseable.parse
                try:
                    return target_type.parse(value)
                except Exception as e:
                    errors.append(e)

                # try "normal" attrs structuring
                try:
                    if isinstance(value, dict):
                        return converter.structure_attrs_fromdict(value, target_type)
                except Exception as e:
                    errors.append(e)

                return None

            converter.register_structure_hook(
                cls,
                try_parse
            )

    @classmethod
    def parse(cls: typing.Type[ParseableT], value: typing.Any) -> ParseableT:
        return converter.structure_attrs_fromdict(deepcopy(value), cls)


converter.register_structure_hook(
    dict,
    lambda v, t: v if isinstance(v, dict) else dict(v)
)

__all__ = [
    "Serializable",
    "Parseable",
    "converter",
    "Idempotent",
]
