import os

PRODUCTION_ENV = {
    "DJANGO_SECRET_KEY": "k3Y9-only-for-this-test-qP7xV2mZ8sL4tR6wN1bH5cJ0fD3gA9yU",
    "DJANGO_DEBUG": "0",
    "DJANGO_ALLOWED_HOSTS": "portal.example.test",
    "DB_NAME": "unused",
    "DB_USER": "unused",
    "DB_PASSWORD": "unused",
}


def subprocess_env(**overrides):
    """Environment for a child `manage.py`: no project settings except the given ones."""
    inherited = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "DB_", "WORKER_"))
    }
    return {**inherited, **overrides}
