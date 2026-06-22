"""Cam: scripted control of the Arena viewport camera over /arena/viewport/*."""

from .camera import Camera
from .client import TargetSelection
from .shot import load_shot
from .shots import discover

discover()

__all__ = ["Camera", "TargetSelection", "load_shot"]
