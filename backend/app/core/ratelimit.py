"""Login lockout: too many wrong passwords from one caller, and that caller waits.

Kept in-process on purpose — a lockout is a speed bump against a slow brute
force, not a security boundary, and a shared counter would need Redis before it
mattered. The window is a sliding one: the Nth failure locks the caller for
`window_seconds`, and old failures age out on their own.

Keyed by client IP by default. Behind a reverse proxy the IP is the proxy's, so
`proxy_header` (e.g. `X-Forwarded-For`) can be trusted instead — only enable it
when something in front of the app overwrites that header, or a client can forge
its way past the lockout.
"""

import time
from collections import defaultdict


class LoginThrottle:
    """Count recent failures per key and say when a key is locked out."""

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = defaultdict(list)

    def _prune(self, key: str, window_seconds: float, now: float) -> list[float]:
        recent = [t for t in self._failures[key] if now - t < window_seconds]
        self._failures[key] = recent
        return recent

    def is_locked_out(
        self, key: str, max_attempts: int, window_seconds: float, now: float | None = None
    ) -> bool:
        """True once `max_attempts` failures landed inside the window."""
        if max_attempts <= 0:
            return False
        now = time.monotonic() if now is None else now
        return len(self._prune(key, window_seconds, now)) >= max_attempts

    def record_failure(self, key: str, now: float | None = None) -> int:
        """Note one wrong password; returns how many are in the window now."""
        now = time.monotonic() if now is None else now
        self._failures[key].append(now)
        return len(self._failures[key])

    def clear(self, key: str) -> None:
        """Forget a key's failures — a successful login wipes the slate."""
        self._failures.pop(key, None)

    def retry_after(self, key: str, window_seconds: float, now: float | None = None) -> int:
        """Seconds until the oldest failure ages out (for a Retry-After header)."""
        now = time.monotonic() if now is None else now
        recent = self._prune(key, window_seconds, now)
        if not recent:
            return 0
        return max(1, int(window_seconds - (now - recent[0])))


# One shared instance: a restart resets it, which is acceptable for a speed bump.
throttle = LoginThrottle()
