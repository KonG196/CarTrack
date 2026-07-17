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
    """Client IP for rate-limit keys, resistant to header spoofing.

    A client can send its own ``X-Forwarded-For``; the trusted proxy in front
    (Caddy/nginx) then APPENDS the real peer, so the **last** element is the one
    the attacker cannot forge — taking the first element let anyone reset their
    own bucket per request and brute force auth. With no proxy (direct hit) there
    is no header and we fall back to the socket peer.

    Assumes exactly one trusted proxy hop. If more are ever added, raise the
    from-the-right index accordingly.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"
