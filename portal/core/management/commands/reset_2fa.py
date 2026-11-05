from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.accounts import reset_two_factor_from_server
from core.models import User


class Command(BaseCommand):
    help = gettext_lazy(
        "Removes the two-factor devices of an account, for when the admin loses theirs."
    )

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        user = User.objects.filter(email=email.strip().lower()).first()
        if user is None:
            raise CommandError(_("There is no account with this email address."))
        reset_two_factor_from_server(user)
        self.stdout.write(_("Two-factor authentication reset. Set it up again at next sign-in."))
