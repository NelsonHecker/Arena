"""Generic QoS profiles, the caller picks the depth."""

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy


def latched(depth: int = 1) -> QoSProfile:
    """RELIABLE, TRANSIENT_LOCAL, KEEP_LAST."""
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )


def reliable(depth: int) -> QoSProfile:
    """RELIABLE, VOLATILE, KEEP_LAST."""
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )


def best_effort(depth: int) -> QoSProfile:
    """BEST_EFFORT, VOLATILE, KEEP_LAST."""
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )
