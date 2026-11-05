from django.contrib.auth.tokens import PasswordResetTokenGenerator


class PasswordLinkTokenGenerator(PasswordResetTokenGenerator):
    """One-time link for invitations and recovery, valid for PASSWORD_RESET_TIMEOUT (48 h).

    Setting a password, signing in or deactivating the account invalidates every link already sent.
    """

    key_salt = "core.tokens.PasswordLinkTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}{user.is_active}"


password_link_token = PasswordLinkTokenGenerator()
