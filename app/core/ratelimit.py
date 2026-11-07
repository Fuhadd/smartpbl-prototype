"""In-memory sliding-window rate limiting.

Each limiter keeps, per key (an IP, a username, a user id), the timestamps of recent
requests and refuses a request once `limit` fall within the last `window_s` seconds.

PROTOTYPE SCOPE: state lives in this process. With N workers or replicas the effective
limit is N x `limit`, and a restart forgets it. Production needs a shared store (Redis
with a sorted set or a token bucket in Lua) or limits at the gateway (see SECURITY.md).
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, status


class SlidingWindowLimiter:
    def __init__(
        self,
        name: str,
        limit: Callable[[], int],
        window_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._limit = limit  # read per call, so settings (and tests) can change it
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()  # sync endpoints run on a thread pool

    def check(self, key: str) -> None:
        """Count one request for `key`; raise 429 with Retry-After if over the limit.
        Refused requests are not counted, so a client that waits is let back in."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window_s:
                hits.popleft()
            if len(hits) >= self._limit():
                retry_after = max(1, round(hits[0] + self.window_s - now))
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "too many requests; try again later",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory against many one-off keys
                self._prune(now)

    def _prune(self, now: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window_s]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_registry: list[SlidingWindowLimiter] = []


def limiter(name: str, limit: Callable[[], int], window_s: float = 60.0) -> SlidingWindowLimiter:
    created = SlidingWindowLimiter(name, limit, window_s)
    _registry.append(created)
    return created


def reset_all() -> None:
    """Forget all counts (tests: each test starts with a clean window)."""
    for each in _registry:
        each.reset()
