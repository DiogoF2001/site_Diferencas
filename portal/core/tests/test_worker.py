import signal
import subprocess
import sys
import time
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command

from core import worker
from core.tests.helpers import PRODUCTION_ENV, subprocess_env


@pytest.fixture
def empty_registry(monkeypatch):
    monkeypatch.setattr(worker, "registry", {})


@pytest.mark.usefixtures("empty_registry")
def test_task_runs_immediately_and_then_only_after_its_interval():
    calls = []

    @worker.periodic(every=timedelta(seconds=60))
    def task():
        calls.append(1)

    worker.run_due_tasks(now=1000)
    worker.run_due_tasks(now=1059)
    assert len(calls) == 1

    worker.run_due_tasks(now=1060)
    assert len(calls) == 2


@pytest.mark.usefixtures("empty_registry")
def test_failing_task_does_not_stop_the_others():
    calls = []

    @worker.periodic(every=timedelta(seconds=60))
    def broken():
        raise RuntimeError("boom")

    @worker.periodic(every=timedelta(seconds=60))
    def healthy():
        calls.append(1)

    executed = worker.run_due_tasks(now=1000)

    assert len(executed) == 2
    assert calls == [1]


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("empty_registry")
def test_runworker_once_writes_heartbeat(settings, tmp_path):
    settings.WORKER_HEARTBEAT_FILE = tmp_path / "heartbeat"

    call_command("runworker", once=True)

    assert settings.WORKER_HEARTBEAT_FILE.exists()


def test_runworker_stops_cleanly_on_sigterm(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    process = subprocess.Popen(
        [sys.executable, "manage.py", "runworker"],
        cwd=settings.BASE_DIR,
        env=subprocess_env(**PRODUCTION_ENV, WORKER_HEARTBEAT_FILE=str(heartbeat)),
    )
    try:
        deadline = time.monotonic() + 15
        while not heartbeat.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert heartbeat.exists()

        process.send_signal(signal.SIGTERM)

        assert process.wait(timeout=10) == 0
    finally:
        process.kill()
