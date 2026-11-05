from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        from core import audit  # noqa: F401  (connects the failed-login signal)

        autodiscover_modules("permissions")
