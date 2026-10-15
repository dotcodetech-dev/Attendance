from __future__ import annotations

import time

from .config import settings


class PunchDebouncer:
    """Turns raw per-frame matches into confirmed punches.

    Sliding-window voting: a punch fires for an employee once they collect
    settings.consecutive_frames matched frames (votes) within
    settings.vote_window_s seconds — tolerant of the gaps a walking person
    produces, unlike a strict consecutive-frame rule. At most one punch per
    settings.debounce_minutes per employee.
    """

    def __init__(self) -> None:
        self._state: dict[str, dict] = {}  # code -> {votes: [ts...], last_punch}

    def observe(self, employee_code: str) -> bool:
        """Record one frame's match; True means fire a punch now."""
        now = time.monotonic()
        st = self._state.setdefault(employee_code, {"votes": [], "last_punch": None})
        window_start = now - settings.vote_window_s
        st["votes"] = [t for t in st["votes"] if t >= window_start]
        st["votes"].append(now)

        if len(st["votes"]) < settings.consecutive_frames:
            return False
        if st["last_punch"] is not None and now - st["last_punch"] < settings.debounce_minutes * 60:
            return False
        st["last_punch"] = now
        st["votes"] = []
        return True

    def seconds_until_next_punch(self, employee_code: str) -> float:
        st = self._state.get(employee_code)
        if not st or st["last_punch"] is None:
            return 0.0
        return max(0.0, settings.debounce_minutes * 60 - (time.monotonic() - st["last_punch"]))
