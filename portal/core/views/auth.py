from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.debug import sensitive_post_parameters
from django_otp import user_has_device

from core import accounts
from core.audit import Action, record
from core.forms import LoginForm
from core.models import Location, Membership
from core.permissions import (
    MANAGE_MENTORSHIPS,
    VIEW_AUDIT,
    enrols_two_factor_by_link,
    is_admin,
    locations_with_perm,
)
from core.tokens import password_link_token
from core.views.two_factor import start_enrolment


class LoginView(auth_views.LoginView):
    form_class = LoginForm
    template_name = "core/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["self_password_reset"] = settings.PORTAL_SELF_PASSWORD_RESET
        return context


class PasswordSetView(auth_views.PasswordResetConfirmView):
    """The page behind invitation and recovery links. It never signs the person in.

    Staff whose role requires 2FA and who have no device go straight on to set it up (plan,
    section 5): they cannot sign in without it, so leaving halfway means asking for a new link.
    """

    template_name = "core/password_set.html"
    token_generator = password_link_token
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        response = super().form_valid(form)
        record(Action.PASSWORD_SET, actor=self.user, target=self.user)
        if enrols_two_factor_by_link(self.user):
            start_enrolment(self.request, self.user)
            return redirect("two_factor_enrol")
        messages.success(self.request, _("Your password is set. You can now sign in."))
        return response


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "core/password_change.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        response = super().form_valid(form)
        record(Action.PASSWORD_CHANGED, actor=self.request.user, target=self.request.user)
        messages.success(self.request, _("Your password has been changed."))
        return response


@method_decorator(sensitive_post_parameters(), name="dispatch")
class SelfPasswordResetView(auth_views.PasswordResetView):
    """'Forgot my password', switched off by PORTAL_SELF_PASSWORD_RESET until the centre wants it.

    The answer is the same whether or not the address has an account, and the emails count
    towards the same hourly limit as the ones the secretariat sends.
    """

    template_name = "core/password_reset.html"
    form_class = PasswordResetForm

    def dispatch(self, request, *args, **kwargs):
        if not settings.PORTAL_SELF_PASSWORD_RESET:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        for user in form.get_users(form.cleaned_data["email"]):
            if user.is_superuser:
                continue
            try:
                with transaction.atomic():
                    accounts.send_password_link(self.request, user)
            except accounts.EmailLimitReached:
                pass
        return render(self.request, "core/password_reset_sent.html")


@login_required
def home(request):
    if is_admin(request.user):
        locations = Location.objects.all()
    else:
        memberships = Membership.objects.active_on().filter(user=request.user)
        locations = Location.objects.filter(is_active=True, pk__in=memberships.values("location"))
    managed = set(
        locations_with_perm(request.user, "core.manage_members").values_list("pk", flat=True)
    )
    listed = set(
        locations_with_perm(request.user, "core.view_professionals").values_list("pk", flat=True)
    )
    mentored = set(
        locations_with_perm(request.user, MANAGE_MENTORSHIPS).values_list("pk", flat=True)
    )
    audited = set(locations_with_perm(request.user, VIEW_AUDIT).values_list("pk", flat=True))
    rows = [
        {
            "location": location,
            "manages": location.pk in managed,
            "lists": location.pk in listed,
            "mentors": location.pk in mentored,
            "audits": location.pk in audited,
        }
        for location in locations
    ]
    context = {"rows": rows, "has_two_factor": user_has_device(request.user)}
    return render(request, "core/home.html", context)
