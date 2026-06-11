"""Namespaced launch flags (`debug.*`, `optim.*`): expansion and lookup.

Two equivalent input syntaxes collapse onto the same canonical dotted params:
`<ns>:=a,b` is shorthand for `<ns>.a:=1 <ns>.b:=1`. The dotted form is canonical
and wins on conflict; the bare comma list is pure sugar expanded at launch time.
Flags are open-namespaced (any token is accepted) and read back by prefix.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import launch
    import rclpy.node

_FALSY = frozenset({"", "0", "false", "no", "off"})


def truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in _FALSY
    return bool(value)


def flag_enabled(node: rclpy.node.Node, namespace: str, flag: str) -> bool:
    """True if `<namespace>.<flag>` is declared and set to a truthy value."""
    param = node.get_parameters_by_prefix(namespace).get(flag)
    return param is not None and truthy(param.value)


def expand_flag_namespace(
    context: launch.LaunchContext,
    name: str,
    coerce: Callable[[str], object],
) -> dict[str, object]:
    """Expand `<name>:=a,b` shorthand into dotted params `{name.a: 1, name.b: 1}`,
    overlaid by any explicit `<name>.x:=v` (coerced; explicit wins)."""
    configs = context.launch_configurations
    out: dict[str, object] = {f"{name}.{token}": 1 for raw in configs.get(name, "").split(",") if (token := raw.strip())}
    prefix = f"{name}."
    for key, value in configs.items():
        if key.startswith(prefix) and key[len(prefix) :].strip():
            out[key] = coerce(value)
    return out
