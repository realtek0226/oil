from __future__ import annotations

import os
import random
import threading
import time
from typing import Any

import requests


class OilchemCircuitOpen(RuntimeError):
    pass


class OilchemRequestGuard:
    def __init__(self) -> None:
        self.min_interval_seconds = float(os.getenv("OILCHEM_MIN_REQUEST_INTERVAL_SECONDS", "2.0"))
        self.jitter_seconds = float(os.getenv("OILCHEM_REQUEST_JITTER_SECONDS", "0.5"))
        self.block_seconds = float(os.getenv("OILCHEM_CIRCUIT_BLOCK_SECONDS", "1800"))
        self.max_failures = int(os.getenv("OILCHEM_CIRCUIT_MAX_FAILURES", "3"))
        self._lock = threading.RLock()
        self._last_request_at = 0.0
        self._failure_count = 0
        self._blocked_until = 0.0

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        with self._lock:
            now = time.monotonic()
            if now < self._blocked_until:
                remaining = int(self._blocked_until - now)
                raise OilchemCircuitOpen(f"OilChem request circuit is open; retry after {remaining}s")
            wait_seconds = self.min_interval_seconds - (now - self._last_request_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds + random.uniform(0, max(self.jitter_seconds, 0.0)))
            self._last_request_at = time.monotonic()

        try:
            response = requests.request(method, url, **kwargs)
        except requests.RequestException:
            self._mark_failure()
            raise

        if response.status_code in {401, 403, 429}:
            self._mark_failure(force_block=True)
        elif response.status_code >= 500:
            self._mark_failure()
        else:
            self._mark_success()
        return response

    def _mark_success(self) -> None:
        with self._lock:
            self._failure_count = 0

    def _mark_failure(self, *, force_block: bool = False) -> None:
        with self._lock:
            self._failure_count += 1
            if force_block or self._failure_count >= self.max_failures:
                self._blocked_until = time.monotonic() + self.block_seconds


_guard = OilchemRequestGuard()


def oilchem_get(url: str, **kwargs: Any) -> requests.Response:
    return _guard.request("GET", url, **kwargs)


def oilchem_post(url: str, **kwargs: Any) -> requests.Response:
    return _guard.request("POST", url, **kwargs)
