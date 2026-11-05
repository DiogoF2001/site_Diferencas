"""Account actions of the portal. Each checks its permission and leaves an AuditEvent.

The views only collect input and show results: the rules live here and in core.permissions, so
that every way into an action applies them the same way.
"""

import datetime
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import permissions
from core.audit import Action, account_emails_left, membership_snapshot, record
from core.models import Membership, User
from core.tokens import password_link_token, two_factor_link_token

logger = logging.getLogger(__name__)

LINK_FAILED_MESSAGE = gettext_lazy("Could not send the 2FA link. Send it again later.")


class EmailLimitReached(Exception):
    pass


def password_link(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse("password_set", args=[uid, password_link_token.make_token(user)])
    return request.build_absolute_uri(path)


def _send(kind, target, context):
    subject = render_to_string(f"core/email/{kind}_subject.txt", context).strip()
    body = render_to_string(f"core/email/{kind}_body.txt", context)
    send_mail(subject, body, None, [target.email])


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
    _send(kind, target, context)
    action = Action.INVITATION_SENT if is_invitation else Action.RECOVERY_LINK_SENT
    record(action, actor=actor, target=target, location=location)


def two_factor_link(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse("two_factor_link", args=[uid, two_factor_link_token.make_token(user)])
    return request.build_absolute_uri(path)


def send_two_factor_link(request, membership, *, actor=None):
    """Plan, section 5: a role that requires 2FA, given to someone without a device, sends them
    the link to set it up, so that the role does not lock them out when it starts.

    An account that never set a password gets the invitation instead, whose flow already ends
    in the 2FA step. Returns the action recorded, or None when there was nothing to send. Counts
    towards the hourly limit (EmailLimitReached); SMTP errors propagate, as in send_password_link.
    """
    target = membership.user
    if membership.role not in permissions.TWO_FACTOR_ROLES:
        return None
    if not permissions.enrols_two_factor_by_link(target):
        return None
    if not target.has_usable_password():
        send_password_link(request, target, actor=actor, location=membership.location)
        return Action.INVITATION_SENT
    if account_emails_left(target) == 0:
        raise EmailLimitReached
    context = {
        "user": target,
        "membership": membership,
        "link": two_factor_link(request, target),
        "hours": settings.PASSWORD_RESET_TIMEOUT // 3600,
        "grace_days": settings.PORTAL_TWO_FACTOR_GRACE_DAYS,
    }
    _send("two_factor_link", target, context)
    record(Action.TWO_FACTOR_LINK_SENT, actor=actor, target=target, location=membership.location)
    return Action.TWO_FACTOR_LINK_SENT


def offer_two_factor_link(request, membership, *, actor=None):
    """send_two_factor_link for a role just given: the role stands even if the email fails.

    Plan, section 5: a failure (hourly limit or SMTP) is recorded and the caller warns whoever
    gave the role, who can send the link again from the members page.
    """
    try:
        return send_two_factor_link(request, membership, actor=actor)
    except (EmailLimitReached, OSError) as error:
        reason = "limit" if isinstance(error, EmailLimitReached) else "smtp"
        logger.warning("2FA link to user %s not sent: %s", membership.user_id, reason)
        record(
            Action.TWO_FACTOR_LINK_FAILED,
            actor=actor,
            target=membership.user,
            location=membership.location,
            reason=reason,
        )
        return Action.TWO_FACTOR_LINK_FAILED


def send_two_factor_notice(target):
    """Tell the account's owner that 2FA was turned on, for when someone else did it with their
    password (plan, section 5). An SMTP failure is logged and audited, and does not undo the 2FA.
    """
    try:
        _send("two_factor_enabled", target, {"user": target})
    except OSError:
        logger.exception("Could not send the 2FA confirmation to user %s", target.pk)
        record(Action.TWO_FACTOR_NOTICE_FAILED, actor=target, target=target, reason="smtp")
        return
    record(Action.TWO_FACTOR_NOTICE_SENT, actor=target, target=target)


@transaction.atomic
def add_member(request, actor, location, *, email, full_name, role, subrole, start, end):
    """Give `email` a role in `location`, creating and inviting the account if it is new.

    Returns (membership, created, sent). An existing account only gets the membership, and the
    manager of this location sees nothing of what the person does elsewhere (plan, section 4).
    `sent` is the email action recorded: the invitation, or the 2FA link for a role requiring it,
    or its failure. Only the invitation of a new account undoes everything when it fails.
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
        sent = Action.INVITATION_SENT
    else:
        sent = offer_two_factor_link(request, membership, actor=actor)
    return membership, created, sent


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
def change_membership(request, actor, membership, *, role, subrole, start, end):
    """Change the role or the dates of an active or future membership, up to the actor's level.

    Returns (membership, sent): the membership now in force and the 2FA email action, as in
    add_member. A new role for a membership that already started does not rewrite the past:
    the old role ends yesterday and the new one starts today, with the end date asked for.
    """
    if not permissions.can_change_membership(actor, membership, role):
        raise PermissionDenied
    today = timezone.localdate()
    if membership.end_date is not None and membership.end_date < today:
        raise PermissionDenied
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    before = membership_snapshot(membership)
    role_changed = (role, subrole) != (membership.role, membership.subrole)
    started = membership.start_date < today
    if role_changed and started:
        membership.check_change(membership.start_date, end)
        new = Membership(
            user=membership.user,
            location=membership.location,
            role=role,
            subrole=subrole,
            start_date=today,
            end_date=end,
        )
        membership.end_date = today - datetime.timedelta(days=1)
        membership.full_clean()
        membership.save(update_fields=["end_date"])
        new.full_clean()
        new.save()
        details = {"before": before, "role_change": True}
        record(
            Action.MEMBERSHIP_ENDED,
            actor=actor,
            target=membership.user,
            location=membership.location,
            after=membership_snapshot(membership),
            **details,
        )
        record(
            Action.MEMBERSHIP_CREATED,
            actor=actor,
            target=new.user,
            location=new.location,
            after=membership_snapshot(new),
            role_change=True,
        )
        membership = new
    else:
        membership.check_change(start, end)
        membership.role, membership.subrole = role, subrole
        membership.start_date, membership.end_date = start, end
        membership.full_clean()
        membership.save()
        after = membership_snapshot(membership)
        if after == before:
            return membership, None
        record(
            Action.MEMBERSHIP_CHANGED,
            actor=actor,
            target=membership.user,
            location=membership.location,
            before=before,
            after=after,
        )
    sent = None
    if before["role"] != membership.role:
        sent = offer_two_factor_link(request, membership, actor=actor)
    return membership, sent


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
    """Remove the target's devices. Staff whose role requires 2FA then need a new link."""
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
    """The members page's "Send password link": the invitation or the recovery link.

    Someone who still has to set 2FA up for a staff role sets it up in the same flow, so this
    also helps whoever forgot the password they need for the 2FA link.
    """
    if not permissions.can_send_recovery_link(actor, target, location):
        raise PermissionDenied
    with transaction.atomic():
        send_password_link(request, target, actor=actor, location=location)


class NothingToSend(Exception):
    pass


def resend_two_factor_link(request, actor, target, location):
    """The members page's "Send 2FA link", for someone with a password and 2FA still to set up.

    Raises NothingToSend once that is no longer the case (2FA done, role gone, no password).
    """
    if not permissions.can_send_recovery_link(actor, target, location):
        raise PermissionDenied
    with transaction.atomic():
        membership = _two_factor_membership(target, location)
        if membership is None:
            raise NothingToSend
        send_two_factor_link(request, membership, actor=actor)


def _two_factor_membership(target, location):
    """The staff role, here if there is one, that a 2FA link would be about; None if none is due."""
    if not target.has_usable_password() or not permissions.enrols_two_factor_by_link(target):
        return None
    memberships = (
        Membership.objects.filter(user=target, role__in=permissions.TWO_FACTOR_ROLES)
        .overlapping(timezone.localdate())
        .select_related("location")
    )
    return (
        memberships.filter(location=location).first() or memberships.order_by("start_date").first()
    )


def needs_two_factor_link(target):
    return _two_factor_membership(target, None) is not None
