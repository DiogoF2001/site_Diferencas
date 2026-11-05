import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import accounts, permissions
from core.forms import MemberForm
from core.models import AuditEvent, Location, Membership


def _location_with_perm(request, location_id, perm):
    location = get_object_or_404(Location, pk=location_id)
    if not permissions.has_perm_in(request.user, perm, location):
        raise PermissionDenied
    return location


def _current_memberships(location):
    return (
        Membership.objects.filter(location=location)
        .overlapping(timezone.localdate())
        .select_related("user")
        .order_by("user__full_name", "start_date")
    )


def _group_by_user(memberships):
    people = {}
    for membership in memberships:
        people.setdefault(membership.user, []).append(membership)
    return people


@login_required
def member_list(request, location_id):
    location = _location_with_perm(request, location_id, permissions.MANAGE_MEMBERS)
    people = _group_by_user(_current_memberships(location))
    with_device = set(
        TOTPDevice.objects.filter(user__in=people, confirmed=True).values_list("user", flat=True)
    )
    actor = request.user
    rows = [
        {
            "user": user,
            "memberships": memberships,
            "has_two_factor": user.pk in with_device,
            "can_remove": permissions.can_remove_from_location(actor, user, location),
            "can_manage_account": permissions.can_manage_account(actor, user),
            "can_send_link": permissions.can_send_recovery_link(actor, user, location),
            "sends_two_factor_link": accounts.needs_two_factor_link(user),
        }
        for user, memberships in people.items()
    ]
    context = {
        "location": location,
        "rows": rows,
        "can_list": permissions.has_perm_in(actor, "core.view_professionals", location),
    }
    return render(request, "core/member_list.html", context)


@login_required
def member_add(request, location_id):
    location = _location_with_perm(request, location_id, permissions.MANAGE_MEMBERS)
    roles = permissions.assignable_roles(request.user, location)
    form = MemberForm(request.POST or None, roles=roles)
    if form.is_valid():
        data = form.cleaned_data
        try:
            _membership, created, sent = accounts.add_member(
                request,
                request.user,
                location,
                email=data["email"],
                full_name=data["full_name"],
                role=data["role"],
                subrole=data["subrole"],
                start=data["start_date"],
                end=data["end_date"],
            )
        except ValidationError as error:
            _add_errors(form, error)
        except accounts.EmailLimitReached:
            form.add_error(None, _("Too many emails to this address in the last hour."))
        except OSError:
            # smtplib errors are OSErrors; the transaction left no account behind.
            form.add_error(None, _("The email could not be sent. Please try again."))
        else:
            if created:
                messages.success(request, _("Account created. The invitation was sent by email."))
            elif sent == AuditEvent.Action.TWO_FACTOR_LINK_FAILED:
                messages.success(
                    request,
                    _("This email already had an account. The membership was added."),
                )
                messages.warning(request, accounts.LINK_FAILED_MESSAGE)
            elif sent == AuditEvent.Action.TWO_FACTOR_LINK_SENT:
                messages.success(
                    request,
                    _(
                        "This email already had an account. The membership was added and, as the "
                        "role requires two-factor authentication, the link to set it up was sent."
                    ),
                )
            elif sent == AuditEvent.Action.INVITATION_SENT:
                messages.success(
                    request,
                    _(
                        "This email already had an account, which never set a password. The "
                        "membership was added and the invitation was sent again."
                    ),
                )
            else:
                messages.success(
                    request,
                    _("This email already had an account. Only the membership was added."),
                )
            return redirect("member_list", location.pk)
    return render(request, "core/member_add.html", {"location": location, "form": form})


def _add_errors(form, error):
    """Model errors on the form, under the matching field when there is one."""
    fields = {"start_date", "end_date", "role", "subrole", "email", "full_name"}
    if hasattr(error, "error_dict"):
        for field, errors in error.error_dict.items():
            for item in errors:
                form.add_error(field if field in fields else None, item)
    else:
        form.add_error(None, error)


def _member(location, user_id):
    """Only people with an active or future membership here; anyone else is not found."""
    return get_object_or_404(permissions.members_of(location), pk=user_id)


@require_POST
@login_required
def member_remove(request, location_id, user_id):
    location = _location_with_perm(request, location_id, permissions.MANAGE_MEMBERS)
    target = _member(location, user_id)
    accounts.remove_from_location(request.user, target, location)
    messages.success(request, _("%(name)s was removed from this location.") % {"name": target})
    return redirect("member_list", location.pk)


@require_POST
@login_required
def account_deactivate(request, location_id, user_id):
    return _set_active(request, location_id, user_id, active=False)


@require_POST
@login_required
def account_reactivate(request, location_id, user_id):
    return _set_active(request, location_id, user_id, active=True)


def _set_active(request, location_id, user_id, *, active):
    location = _location_with_perm(request, location_id, permissions.MANAGE_MEMBERS)
    target = _member(location, user_id)
    accounts.set_account_active(request.user, target, active)
    if active:
        message = _("The account of %(name)s was reactivated.")
    else:
        message = _("The account of %(name)s was deactivated.")
    messages.success(request, message % {"name": target})
    return redirect("member_list", location.pk)


@require_POST
@login_required
def account_reset_two_factor(request, location_id, user_id):
    location = _location_with_perm(request, location_id, permissions.MANAGE_MEMBERS)
    target = _member(location, user_id)
    accounts.reset_two_factor(request.user, target)
    messages.success(
        request,
        _(
            "Two-factor authentication of %(name)s was reset. If their role requires it, "
            "they need a new link to set it up again."
        )
        % {"name": target},
    )
    return redirect("member_list", location.pk)


@require_POST
@login_required
def account_send_link(request, location_id, user_id):
    location = _location_with_perm(request, location_id, permissions.MANAGE_MEMBERS)
    target = _member(location, user_id)
    try:
        accounts.send_recovery_link(request, request.user, target, location)
    except accounts.EmailLimitReached:
        messages.error(request, _("Too many emails to this address in the last hour."))
    except OSError:
        messages.error(request, _("The email could not be sent. Please try again."))
    else:
        messages.success(request, _("A link was sent to %(email)s.") % {"email": target.email})
    return redirect("member_list", location.pk)


@login_required
def professional_list(request, location_id):
    """Coordination's list: the location's members and their roles here, optionally elsewhere.

    Elsewhere it shows only roles and locations, never what the person does there (plan, 4).
    """
    location = _location_with_perm(request, location_id, "core.view_professionals")
    show_other = request.GET.get("outros") == "1"
    people = _group_by_user(_current_memberships(location))
    elsewhere = {}
    if show_other:
        others = (
            Membership.objects.filter(user__in=people)
            .exclude(location=location)
            .overlapping(timezone.localdate())
            .select_related("location")
            .order_by("location__name", "start_date")
        )
        for membership in others:
            elsewhere.setdefault(membership.user_id, []).append(membership)
    rows = [
        {"user": user, "memberships": memberships, "elsewhere": elsewhere.get(user.pk, [])}
        for user, memberships in people.items()
    ]
    if request.GET.get("formato") == "csv":
        return _professionals_csv(location, rows, show_other)
    context = {"location": location, "rows": rows, "show_other": show_other}
    return render(request, "core/professional_list.html", context)


def _describe(membership, *, with_location=False):
    role = membership.get_role_display()
    if membership.subrole:
        role = f"{role} ({membership.get_subrole_display()})"
    end = membership.end_date.isoformat() if membership.end_date else "…"
    text = f"{role}, {membership.start_date.isoformat()} – {end}"
    return f"{membership.location}: {text}" if with_location else text


def _csv_cell(value):
    """Spreadsheets run cells that start with these characters as formulas."""
    value = str(value)
    return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _professionals_csv(location, rows, show_other):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"profissionais-{location.pk}-{timezone.localdate().isoformat()}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    # The BOM and the semicolon are what spreadsheets in Portugal expect.
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    header = [_("Name"), _("Email address"), _("Account"), _("Roles in this location")]
    if show_other:
        header.append(_("Roles in other locations"))
    writer.writerow(header)
    for row in rows:
        user = row["user"]
        line = [
            user.full_name,
            user.email,
            pgettext("account", "active") if user.is_active else pgettext("account", "deactivated"),
            "; ".join(_describe(membership) for membership in row["memberships"]),
        ]
        if show_other:
            line.append("; ".join(_describe(item, with_location=True) for item in row["elsewhere"]))
        writer.writerow([_csv_cell(value) for value in line])
    return response
