import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.models import User


class Command(BaseCommand):
    help = gettext_lazy("Creates the admin account from the environment. Safe to run repeatedly.")

    def handle(self, *args, **options):
        email = os.environ.get("PORTAL_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("PORTAL_ADMIN_PASSWORD", "")
        full_name = os.environ.get("PORTAL_ADMIN_NAME", "").strip() or "Admin"
        if not email or not password:
            raise CommandError(_("PORTAL_ADMIN_EMAIL and PORTAL_ADMIN_PASSWORD must be set."))

        if User.objects.filter(is_superuser=True).exclude(email=email).exists():
            raise CommandError(_("Another admin account already exists."))

        user = User.objects.filter(email=email).first()
        if user is None:
            self.create_admin(email, full_name, password)
            self.stdout.write(_("Admin account created."))
        elif not user.is_superuser:
            raise CommandError(_("This email address belongs to an account that is not the admin."))
        else:
            # The password in the environment only applies on creation, so running this again
            # never undoes a password the admin has changed since.
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])
            self.stdout.write(_("The admin account already exists; nothing to create."))

    def create_admin(self, email, full_name, password):
        user = User(email=email, full_name=full_name, is_superuser=True)
        try:
            user.full_clean(exclude=["password"])
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        user.set_password(password)
        user.save()
