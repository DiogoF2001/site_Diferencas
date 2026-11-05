"""Account actions of the portal. Each checks its permission and leaves an AuditEvent.

The views only collect input and show results: the rules live here and in core.permissions, so
that every way into an action applies them the same way.
"""

import datetime

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import permissions
from core.audit import Action, account_emails_left, membership_snapshot, record
from core.models import Membership, User
from core.tokens import password_link_token


class EmailLimitReached(Exception):
    pass


def password_link(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse("password_set", args=[uid, password_link_token.make_token(user)])
    return request.build_absolute_uri(path)


def send_password_link(request, target, *, actor=None, location=None):
    """Email a one-time link: an invitation if the account never had a password, else recovery.

    Raises EmailLimitReached past the hourly limit per account, so that nobody floods an inbox.
    SMTP errors propagate, and the caller's transaction then leaves no trace of the action.
    """
    if account_emails_left(target) == 0:
        raise EmailLimitReached
    is_invitation = not target.has_usable_password()
    kind = "invitation" if is_invitation else "recovery"
    context = {
        "user": target,
        "link": password_link(request, target),
        "hours": settings.PASSWORD_RESET_TIMEOUT // 3600,
    }
    subject = render_to_string(f"core/email/{kind}_subject.txt", context).strip()
    body = render_to_string(f"core/email/{kind}_body.txt", context)
    send_mail(subject, body, None, [target.email])
    action = Action.INVITATION_SENT if is_invitation else Action.RECOVERY_LINK_SENT
    record(action, actor=actor, target=target, location=location)


@transaction.atomic
def add_member(request, actor, location, *, email, full_name, role, subrole, start, end):
    """Give `email` a role in `location`, creating and inviting the account if it is new.

    Returns (membership, created). An existing account only gets the membership, and the manager
    of this location sees nothing of what the person does elsewhere (plan, section 4).
    """
    if not permissions.can_assign_role(actor, role, location):
        raise PermissionDenied
    user = User.objects.filter(email=email.strip().lower()).first()
    created = user is None
    if created:
        user = User(email=email, full_name=full_name)
        user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save()
    membership = Membership(
        user=user, location=location, role=role, subrole=subrole, start_date=start, end_date=end
    )
    membership.full_clean()
    membership.save()
    record(
        Action.MEMBERSHIP_CREATED,
        actor=actor,
        target=user,
        location=location,
        after=membership_snapshot(membership),
    )
    if created:
        send_password_link(request, user, actor=actor, location=location)
    return membership, created


@transaction.atomic
def remove_from_location(actor, target, location):
    """End today the target's active roles in the location and drop the ones yet to start.

    The end date is the last day with access, so access ends at once. Roles that started today
    cannot end yesterday, and are deleted like the future ones; the audit keeps them.
    """
    if not permissions.can_remove_from_location(actor, target, location):
        raise PermissionDenied
    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)
    memberships = Membership.objects.filter(user=target, location=location).overlapping(today)
    for membership in memberships.select_for_update():
        before = membership_snapshot(membership)
        if membership.start_date >= today:
            membership.delete()
            record(
                Action.MEMBERSHIP_DELETED,
                actor=actor,
                target=target,
                location=location,
                before=before,
            )
        else:
            membership.end_date = yesterday
            membership.save(update_fields=["end_date"])
            record(
                Action.MEMBERSHIP_ENDED,
                actor=actor,
                target=target,
                location=location,
                before=before,
                after=membership_snapshot(membership),
            )


@transaction.atomic
def set_account_active(actor, target, active):
    """Deactivate or reactivate the whole account. Accounts are never deleted (plan, section 5)."""
    if not permissions.can_manage_account(actor, target):
        raise PermissionDenied
    if target.is_active == active:
        return
    target.is_active = active
    target.save(update_fields=["is_active"])
    record(
        Action.ACCOUNT_REACTIVATED if active else Action.ACCOUNT_DEACTIVATED,
        actor=actor,
        target=target,
    )


def reset_two_factor(actor, target):
    """Remove the target's devices; they set up a new one at their next request if required."""
    if not permissions.can_manage_account(actor, target):
        raise PermissionDenied
    _delete_devices(target, actor=actor)


@transaction.atomic
def _delete_devices(target, *, actor):
    deleted, _rows = TOTPDevice.objects.filter(user=target).delete()
    record(Action.TWO_FACTOR_RESET, actor=actor, target=target, devices=deleted)


def reset_two_factor_from_server(target):
    """For the reset_2fa command: whoever runs it already controls the server."""
    _delete_devices(target, actor=None)


def send_recovery_link(request, actor, target, location):
    if not permissions.can_send_recovery_link(actor, target, location):
        raise PermissionDenied
    with transaction.atomic():
        send_password_link(request, target, actor=actor, location=location)
