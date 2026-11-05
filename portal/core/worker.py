"""Minimal periodic task runner used by the `worker` service.

Modules declare tasks in their own `tasks.py` with the `periodic` decorator. Tasks must be
idempotent: the schedule lives in memory, so every task runs again when the worker restarts.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

logger = logging.getLogger(__name__)


@dataclass
class PeriodicTask:
    name: str
    func: Callable[[], None]
    every: timedelta
    last_run: float | None = None

    def is_due(self, now):
        return self.last_run is None or now - self.last_run >= self.every.total_seconds()


registry: dict[str, PeriodicTask] = {}


def periodic(every):
    def decorator(func):
        name = f"{func.__module__}.{func.__qualname__}"
        registry[name] = PeriodicTask(name=name, func=func, every=every)
        return func

    return decorator


def run_due_tasks(now=None):
    now = time.monotonic() if now is None else now
    executed = []
    for task in registry.values():
        if not task.is_due(now):
            continue
        task.last_run = now
        executed.append(task.name)
        try:
            task.func()
        except Exception:
            logger.exception("Periodic task %s failed", task.name)
    return executed
