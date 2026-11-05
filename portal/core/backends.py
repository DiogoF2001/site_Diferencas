from django.contrib.auth.backends import ModelBackend

from core.permissions import has_portal_access


class MembershipBackend(ModelBackend):
    """Checked at login and on every request, so access ends as soon as a membership does."""

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and has_portal_access(user)
