from base64 import b32encode

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django_otp import login as otp_login
from django_otp import user_has_device
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.audit import Action, record
from core.forms import TokenForm


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


@never_cache
@sensitive_post_parameters()
@login_required
def setup(request):
    """Add an authenticator app: show the secret, then confirm it with a first code."""
    user = request.user
    if user_has_device(user):
        return redirect(_next_url(request))
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=False)
    form = TokenForm(request.POST or None)
    if form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            with transaction.atomic():
                device.confirmed = True
                device.save(update_fields=["confirmed"])
                record(Action.TWO_FACTOR_ENABLED, actor=user, target=user)
            _verified(request, device)
            messages.success(request, _("Two-factor authentication is on."))
            return redirect(_next_url(request))
        form.add_error("token", _("The code is not valid. Check the time on your phone."))
    context = {
        "form": form,
        "qr_code": _qr_code_svg(device.config_url),
        "secret": b32encode(device.bin_key).decode(),
        "next": _next_url(request),
    }
    return render(request, "core/two_factor_setup.html", context)


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
