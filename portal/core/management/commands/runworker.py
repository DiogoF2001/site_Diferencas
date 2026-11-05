import logging
import signal
import threading

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import autoreload
from django.utils.module_loading import autodiscover_modules

from core.worker import run_due_tasks

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the periodic tasks until the process is told to stop."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
        parser.add_argument(
            "--autoreload", action="store_true", help="Restart on code changes (development only)."
        )

    def handle(self, *args, **options):
        autodiscover_modules("tasks")
        stop = threading.Event()
        if options["autoreload"]:
            # The reloader runs the loop in a thread and handles SIGTERM itself.
            autoreload.run_with_reloader(self.run_loop, stop=stop)
            return
        if options["once"]:
            self.run_loop(stop=stop, once=True)
            return
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        self.run_loop(stop=stop)

    def run_loop(self, stop, once=False):
        logger.info("Worker started")
        while not stop.is_set():
            close_old_connections()
            run_due_tasks()
            settings.WORKER_HEARTBEAT_FILE.touch()
            if once:
                break
            stop.wait(settings.WORKER_INTERVAL_SECONDS)
        close_old_connections()
        logger.info("Worker stopped")
