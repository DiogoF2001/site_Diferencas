import time
from base64 import b32encode

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django_otp import login as otp_login
from django_otp import user_has_device
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import accounts
from core.audit import Action, record
from core.forms import PasswordCheckForm, TokenForm
from core.models import User
from core.permissions import enrols_two_factor_by_link, is_admin
from core.tokens import password_link_token, two_factor_link_token

ENROL_SESSION_KEY = "core.two_factor_enrol"
# How long after setting the password the 2FA step stays open; after that, a new link.
ENROL_MINUTES = 30


def _next_url(request):
    url = request.POST.get("next") or request.GET.get("next")
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return reverse("home")


def _verified(request, device):
    otp_login(request, device)
    # A new session key for the verified session, like Django does at login.
    request.session.cycle_key()


def _qr_code_svg(url):
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    # Built here from the otpauth URL; nothing from the request goes into it.
    return mark_safe(image.to_string(encoding="unicode"))  # noqa: S308


def _pending_device(user):
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=False)
    return device


def _confirm(request, device, form):
    """Turn the device on if the form has its current code; otherwise explain on the form."""
    user = device.user
    if not form.is_valid():
        return False
    if device.verify_token(form.cleaned_data["token"]):
        with transaction.atomic():
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            record(Action.TWO_FACTOR_ENABLED, actor=user, target=user)
        return True
    form.add_error("token", _("The code is not valid. Check the time on your phone."))
    return False


def _render_setup(request, device, form, **extra):
    context = {
        "form": form,
        "qr_code": _qr_code_svg(device.config_url),
        "secret": b32encode(device.bin_key).decode(),
        **extra,
    }
    return render(request, "core/two_factor_setup.html", context)


@never_cache
@sensitive_post_parameters()
@login_required
def setup(request):
    """Add an authenticator app: show the secret, then confirm it with a first code.

    For the admin, for anyone who wants 2FA without their role requiring it, for someone with an
    upcoming role that will, and for staff within the grace period (see TwoFactorMiddleware).
    Only the password was given here, so everyone but the admin gets an email saying so.
    """
    user = request.user
    if user_has_device(user):
        return redirect(_next_url(request))
    device = _pending_device(user)
    form = TokenForm(request.POST or None)
    if _confirm(request, device, form):
        _verified(request, device)
        if not is_admin(user):
            accounts.send_two_factor_notice(user)
        messages.success(request, _("Two-factor authentication is on."))
        return redirect(_next_url(request))
    return _render_setup(request, device, form, next=_next_url(request))


def start_enrolment(request, user):
    """Called by the link page once the password is set, when the person's role requires 2FA.

    The link's token proved access to the email address; this session carries that proof to the
    2FA step for ENROL_MINUTES, bound to the new password, so that another link ends it too.
    """
    request.session.cycle_key()
    request.session[ENROL_SESSION_KEY] = {
        "user": user.pk,
        "token": password_link_token.make_token(user),
        "at": int(time.time()),
    }


def _enrolling_user(request):
    pending = request.session.get(ENROL_SESSION_KEY)
    if not pending or time.time() - pending["at"] > ENROL_MINUTES * 60:
        return None
    user = User.objects.filter(pk=pending["user"]).first()
    if user is None or not password_link_token.check_token(user, pending["token"]):
        return None
    if not enrols_two_factor_by_link(user):
        return None
    return user


def _user_from_uid(uidb64):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


@never_cache
@sensitive_post_parameters()
def link(request, uidb64, token):
    """The link sent with a role that requires 2FA: the password, then the `enrol` step."""
    user = _user_from_uid(uidb64)
    valid = (
        user is not None
        and two_factor_link_token.check_token(user, token)
        and enrols_two_factor_by_link(user)
    )
    if not valid:
        return render(request, "core/two_factor_link.html", {"validlink": False}, status=400)
    form = PasswordCheckForm(request.POST or None, user=user)
    if form.is_valid():
        start_enrolment(request, user)
        return redirect("two_factor_enrol")
    return render(
        request, "core/two_factor_link.html", {"validlink": True, "form": form, "account": user}
    )


@never_cache
@sensitive_post_parameters()
def enrol(request):
    """Second step of an invitation or recovery link for staff: set up 2FA before signing in."""
    user = _enrolling_user(request)
    if user is None:
        request.session.pop(ENROL_SESSION_KEY, None)
        return render(request, "core/two_factor_enrol_expired.html", status=400)
    device = _pending_device(user)
    form = TokenForm(request.POST or None)
    if _confirm(request, device, form):
        del request.session[ENROL_SESSION_KEY]
        messages.success(request, _("Two-factor authentication is on. You can now sign in."))
        return redirect("login")
    if form.errors:
        record(Action.TWO_FACTOR_FAILED, actor=None, target=user, step="enrol")
    return _render_setup(request, device, form, enrolling=True)


@never_cache
@sensitive_post_parameters()
@login_required
def verify(request):
    user = request.user
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if device is None:
        return redirect(_next_url(request))
    form = TokenForm(request.POST or None)
    if form.is_valid():
        allowed, _info = device.verify_is_allowed()
        if allowed and device.verify_token(form.cleaned_data["token"]):
            _verified(request, device)
            return redirect(_next_url(request))
        record(Action.TWO_FACTOR_FAILED, actor=user, target=user)
        if allowed:
            form.add_error("token", _("The code is not valid. Check the time on your phone."))
        else:
            form.add_error("token", _("Too many wrong codes. Please wait a moment and try again."))
    return render(
        request, "core/two_factor_verify.html", {"form": form, "next": _next_url(request)}
    )
