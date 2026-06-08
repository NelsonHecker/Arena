from __future__ import annotations

import arena_runtime_msgs.msg


class HoldRegistry:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, int]] = {}

    def acquire(self, caller_id: str, reason: str) -> int:
        reasons = self._data.setdefault(caller_id, {})
        reasons[reason] = reasons.get(reason, 0) + 1
        return self.total_count()

    def release(self, caller_id: str, reason: str) -> int:
        reasons = self._data.get(caller_id)
        if reasons is None:
            return self.total_count()
        count = reasons.get(reason, 0)
        if count <= 1:
            reasons.pop(reason, None)
        else:
            reasons[reason] = count - 1
        if not reasons:
            self._data.pop(caller_id, None)
        return self.total_count()

    def release_all(self, caller_id: str) -> int:
        self._data.pop(caller_id, None)
        return self.total_count()

    def is_empty(self) -> bool:
        return not self._data

    def has(self, caller_id: str, reason: str) -> bool:
        return reason in self._data.get(caller_id, {})

    def total_count(self) -> int:
        return sum(sum(reasons.values()) for reasons in self._data.values())

    def snapshot(self) -> list[arena_runtime_msgs.msg.HoldEntry]:
        entries: list[arena_runtime_msgs.msg.HoldEntry] = []
        for caller_id, reasons in self._data.items():
            for reason, count in reasons.items():
                entries.append(
                    arena_runtime_msgs.msg.HoldEntry(
                        caller_id=caller_id,
                        reason=reason,
                        count=count,
                    )
                )
        return entries
