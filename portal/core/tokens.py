from django.contrib.auth.tokens import PasswordResetTokenGenerator


class PasswordLinkTokenGenerator(PasswordResetTokenGenerator):
    """One-time link for invitations and recovery, valid for PASSWORD_RESET_TIMEOUT (48 h).

    Setting a password, signing in or deactivating the account invalidates every link already sent.
    """

    key_salt = "core.tokens.PasswordLinkTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}{user.is_active}"


password_link_token = PasswordLinkTokenGenerator()


class TwoFactorLinkTokenGenerator(PasswordResetTokenGenerator):
    """Link to set up 2FA, sent when someone gets a role that requires it (plan, section 5).

    Valid for PASSWORD_RESET_TIMEOUT. It ignores last_login, so that signing in elsewhere in the
    meantime keeps it working, and ends when the password changes or the account is deactivated.
    The link page also refuses it once there is a device (`enrols_two_factor_by_link`).
    """

    key_salt = "core.tokens.TwoFactorLinkTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.password}{timestamp}{user.email}{user.is_active}"


two_factor_link_token = TwoFactorLinkTokenGenerator()
