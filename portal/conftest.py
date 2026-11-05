from pathlib import Path

import pytest
from django.core.management import call_command
from django.utils.translation.reloader import translation_file_changed


@pytest.fixture(scope="session", autouse=True)
def compiled_translations():
    """The .mo files are build artefacts, and the tests check the Portuguese text."""
    call_command("compilemessages", verbosity=0)
    # Django has already cached the catalogues as they were before this compiled them.
    translation_file_changed(sender=None, file_path=Path("django.mo"))
