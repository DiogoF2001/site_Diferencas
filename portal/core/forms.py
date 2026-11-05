from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.audit import Action, is_login_locked, normalise_email, record
from core.models import Role, Subrole, User
from core.permissions import may_log_in_without_two_factor


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("Wrong email address or password."),
        "locked": _("Too many failed attempts. Please try again in a few minutes."),
        "no_access": _(
            "This account has no access to the portal at the moment. "
            "Please contact your location's secretariat."
        ),
        "two_factor_missing": _(
            "This account must set up two-factor authentication before signing in. "
            "Ask your location's secretariat for a new link."
        ),
    }

    def clean(self):
        email = normalise_email(self.cleaned_data.get("username"))
        password = self.cleaned_data.get("password")
        if not email or not password:
            return self.cleaned_data
        # Checked before the password, so that a locked address learns nothing more.
        if is_login_locked(email):
            raise forms.ValidationError(self.error_messages["locked"], code="locked")
        self.user_cache = authenticate(self.request, username=email, password=password)
        if self.user_cache is None:
            raise self._refusal(email, password)
        self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        # Only reached with the right password, so it reveals nothing about the account.
        if not may_log_in_without_two_factor(user):
            raise forms.ValidationError(
                self.error_messages["two_factor_missing"], code="two_factor_missing"
            )

    def _refusal(self, email, password):
        """Explain a refusal only to whoever knows the password, so it reveals no accounts.

        Hashing for unknown addresses too keeps the response time the same either way.
        """
        user = User.objects.filter(email=email).first()
        if user is None:
            User().set_password(password)
        elif user.check_password(password):
            return forms.ValidationError(self.error_messages["no_access"], code="no_access")
        return forms.ValidationError(self.error_messages["invalid_login"], code="invalid_login")


class MemberForm(forms.Form):
    email = forms.EmailField(label=_("Email address"))
    full_name = forms.CharField(
        label=_("Full name"),
        max_length=150,
        required=False,
        help_text=_("Only for a new account. An existing account keeps its name."),
    )
    role = forms.ChoiceField(label=_("Role"))
    subrole = forms.ChoiceField(
        label=_("Subrole"),
        choices=[("", "—"), *Subrole.choices],
        required=False,
        help_text=_("Only for professionals."),
    )
    start_date = forms.DateField(
        label=_("Start date"), widget=forms.DateInput(attrs={"type": "date"})
    )
    end_date = forms.DateField(
        label=_("End date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("The last day with access. Required for interns."),
    )

    def __init__(self, *args, roles, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [(role.value, role.label) for role in roles]
        self.fields["start_date"].initial = timezone.localdate()

    def clean_email(self):
        return normalise_email(self.cleaned_data["email"])

    def clean(self):
        data = super().clean()
        email = data.get("email")
        if email and not data.get("full_name") and not User.objects.filter(email=email).exists():
            self.add_error("full_name", _("A new account needs a name."))
        if data.get("role") != Role.PROFESSIONAL:
            data["subrole"] = ""
        return data


class PasswordCheckForm(forms.Form):
    """The 2FA setup link asks for the current password: the link proves the email, this the rest.

    Wrong passwords count as failed logins, with the same lockout.
    """

    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autofocus": True, "autocomplete": "current-password"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if is_login_locked(self.user.email):
            raise forms.ValidationError(LoginForm.error_messages["locked"], code="locked")
        if not self.user.check_password(password):
            record(Action.LOGIN_FAILED, target=self.user, email=normalise_email(self.user.email))
            raise forms.ValidationError(_("Wrong password."), code="invalid")
        return password


class TokenForm(forms.Form):
    token = forms.CharField(
        label=_("Code"),
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
            }
        ),
    )

    def clean_token(self):
        token = self.cleaned_data["token"].strip()
        if not token.isdigit():
            raise forms.ValidationError(_("The code has 6 digits."))
        return token
