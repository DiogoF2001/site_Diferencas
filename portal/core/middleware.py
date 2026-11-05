from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django_otp import user_has_device

from core.forms import LoginForm
from core.permissions import lacks_required_two_factor, requires_two_factor

# What a signed-in person can reach before entering the second factor.
EXEMPT_URL_NAMES = {
    "logout",
    "two_factor_verify",
    "two_factor_setup",
    "two_factor_enrol",
    "healthz",
}


class TwoFactorMiddleware:
    """Until the second factor is entered, every page sends the person to that step.

    With a device, that is the code. Without one, the admin sets it up here; anyone else whose
    role requires it is signed out, since a password-only session is not enough for them (plan,
    section 5). That happens when a role starts or the 2FA is reset during a session. This covers
    the backoffice too. Goes after django_otp's OTPMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not user.is_verified() and lacks_required_two_factor(user):
            logout(request)
            messages.error(request, LoginForm.error_messages["two_factor_missing"])
            return redirect("login")
        if user.is_authenticated and not user.is_verified() and not self._is_exempt(request):
            if user_has_device(user):
                return self._redirect("two_factor_verify", request)
            if requires_two_factor(user):
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
