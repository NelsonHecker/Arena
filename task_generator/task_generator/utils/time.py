import functools

import attrs
import builtin_interfaces.msg
import rclpy.time
from typing_extensions import Self


@functools.total_ordering
@attrs.define
class Time:
    """
    Wrapper for builtin_interfaces.msg.Time
    """
    sec: int = attrs.field(converter=int, default=0)
    nanosec: int = attrs.field(converter=int, default=0)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            other = self.parse(other)  # type: ignore
        return self.sec == other.sec and self.nanosec == other.nanosec

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            other = self.parse(other)  # type: ignore
        return self.sec < other.sec or self.nanosec < other.nanosec

    def __add__(self, other: object) -> Self:
        if not isinstance(other, type(self)):
            other = self.parse(other)  # type: ignore

        return self.from_float(self.to_seconds() + other.to_seconds())

    def __sub__(self, other: object) -> Self:
        if not isinstance(other, type(self)):
            other = self.parse(other)  # type: ignore
        new_time = self.to_seconds() - other.to_seconds()
        if new_time < 0:
            raise ValueError('Subtraction leads to negative time.')
        return self.from_float(new_time)

    # Parsing

    @classmethod
    def from_rclpy(cls, v: rclpy.time.Time) -> Self:
        """
        Create instance from rclpy.time.Time object.
        """
        sec, nanosec = v.seconds_nanoseconds()
        return cls(
            sec=sec,
            nanosec=nanosec,
        )

    @classmethod
    def from_msg(cls, v: builtin_interfaces.msg.Time) -> Self:
        """
        Create instance from builtin_interfaces.msg.Time object.
        """
        return cls(
            sec=v.sec,
            nanosec=v.nanosec,
        )

    @classmethod
    def from_float(cls, v: float) -> Self:
        """
        Create instance from float seconds.
        """
        sec = int(v)
        nanosec = int((v - sec) * 1e9)
        return cls(
            sec=sec,
            nanosec=nanosec,
        )

    @classmethod
    def parse(cls, v: builtin_interfaces.msg.Time | rclpy.time.Time | float) -> Self:
        """s.fr
        Create instance from either builtin_interfaces.msg.Time or rclpy.time.Time object.
        """
        if isinstance(v, builtin_interfaces.msg.Time):
            return cls.from_msg(v)
        elif isinstance(v, rclpy.time.Time):
            return cls.from_rclpy(v)
        elif isinstance(v, (int, float)):
            return cls.from_float(v)
        else:
            raise TypeError(f'Cannot parse Time from type: {type(v)}')

    # Converting

    def to_rclpy(self) -> rclpy.time.Time:
        """
        Create rclpy.time.Time from self.
        """
        return rclpy.time.Time(
            seconds=self.sec,
            nanoseconds=self.nanosec,
        )

    def to_msg(self) -> builtin_interfaces.msg.Time:
        """
        Create builtin_interfaces.msg.Time from self.
        """
        return builtin_interfaces.msg.Time(
            sec=self.sec,
            nanosec=self.nanosec,
        )

    def to_seconds(self) -> float:
        """
        Convert to seconds
        """
        return self.sec + self.nanosec / 1e9
