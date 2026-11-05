from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django_otp import user_has_device

from core.permissions import requires_two_factor

# What a signed-in person can reach before entering the second factor.
EXEMPT_URL_NAMES = {"logout", "two_factor_verify", "two_factor_setup", "healthz"}


class TwoFactorMiddleware:
    """Until the second factor is entered, every page sends the person to that step.

    With a device, that is the code; without one, setting it up, when their role requires it
    (plan, section 5). This covers the backoffice too. Goes after django_otp's OTPMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
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
