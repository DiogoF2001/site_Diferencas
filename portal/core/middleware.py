from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django_otp import user_has_device

from core.forms import LoginForm
from core.permissions import is_admin, lacks_required_two_factor, two_factor_grace_ends

# What a signed-in person can reach before entering the second factor.
EXEMPT_URL_NAMES = {
    "logout",
    "two_factor_verify",
    "two_factor_setup",
    "two_factor_enrol",
    "two_factor_link",
    "healthz",
}


class TwoFactorMiddleware:
    """Until the second factor is entered, every page sends the person to that step.

    With a device, that is the code. Without one, staff whose role requires it are sent to set it
    up while the grace period lasts, and are signed out after it, since a password-only session is
    not enough for them (plan, section 5). The admin always sets it up here. This covers the
    backoffice too. Goes after django_otp's OTPMiddleware and MessageMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if not user.is_authenticated or user.is_verified():
            return self.get_response(request)
        if is_admin(user):
            setup_required = not user_has_device(user)
        elif lacks_required_two_factor(user):
            if two_factor_grace_ends(user) is None:
                logout(request)
                messages.error(request, LoginForm.error_messages["two_factor_missing"])
                return redirect("login")
            setup_required = True
        else:
            setup_required = False
        if not self._is_exempt(request):
            if user_has_device(user):
                return self._redirect("two_factor_verify", request)
            if setup_required:
                return self._redirect("two_factor_setup", request)
        return self.get_response(request)

    @staticmethod
    def _is_exempt(request):
        try:
            return resolve(request.path_info).url_name in EXEMPT_URL_NAMES
        except Resolver404:
            return False

    @staticmethod
    def _redirect(url_name, request):
        return redirect(f"{reverse(url_name)}?{urlencode({'next': request.get_full_path()})}")
