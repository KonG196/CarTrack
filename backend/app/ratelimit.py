"""In-memory sliding-window rate limiting for the auth endpoints."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from typing import Hashable

from fastapi import Request


class RateLimiter:
    """At most `limit` recorded attempts per sliding `window_seconds`.

    Keys are chosen by the caller (e.g. an ``(ip, email)`` tuple). State
    lives in process memory: right for the single-process deployment this
    app runs as; a second uvicorn worker would keep its own counters.
    Thread-safe — sync FastAPI endpoints run on a threadpool.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[Hashable, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: Hashable, now: float | None = None) -> bool:
        stamp = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._attempts[key]
            self._prune(attempts, stamp)
            if len(attempts) >= self.limit:
                return False
            attempts.append(stamp)
            return True

    def retry_after(self, key: Hashable, now: float | None = None) -> int:
        stamp = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._attempts[key]
            self._prune(attempts, stamp)
            if not attempts:
                return 1
            return max(1, math.ceil(attempts[0] + self.window_seconds - stamp))

    def reset(self, key: Hashable) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()

    def _prune(self, attempts: deque[float], stamp: float) -> None:
        while attempts and attempts[0] <= stamp - self.window_seconds:
            attempts.popleft()


def client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit keys.

    Behind nginx the first X-Forwarded-For element is the real client
    (nginx.conf must set ``proxy_set_header X-Forwarded-For``); otherwise
    the socket peer address is used.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
