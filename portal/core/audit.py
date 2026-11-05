"""Account audit: every account action in the portal leaves an AuditEvent (plan, section 11)."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.signals import user_login_failed
from django.db.models import Q
from django.dispatch import receiver
from django.utils import timezone

from core.models import AuditEvent, User
from core.permissions import members_of

Action = AuditEvent.Action


def record(action, *, actor=None, target=None, location=None, email="", **details):
    if actor is not None and not actor.is_authenticated:
        actor = None
    return AuditEvent.objects.create(
        action=action,
        actor=actor,
        target=target,
        location=location,
        email=email,
        details=details,
    )


def membership_snapshot(membership):
    return {
        "role": membership.role,
        "subrole": membership.subrole,
        "start_date": membership.start_date.isoformat(),
        "end_date": membership.end_date.isoformat() if membership.end_date else None,
    }


def mentorship_snapshot(mentorship):
    return {
        "mentor": mentorship.mentor.email,
        "mentee": mentorship.mentee.email,
        "start_date": mentorship.start_date.isoformat(),
        "end_date": mentorship.end_date.isoformat() if mentorship.end_date else None,
    }


def normalise_email(email):
    return (email or "").strip().lower()[:254]


def is_login_locked(email):
    """Too many failed logins for this address, whether or not it belongs to an account."""
    since = timezone.now() - timedelta(minutes=settings.PORTAL_LOGIN_LOCKOUT_MINUTES)
    failures = AuditEvent.objects.filter(
        action=Action.LOGIN_FAILED, email=normalise_email(email), created_at__gte=since
    )
    return failures.count() >= settings.PORTAL_LOGIN_MAX_FAILURES


def account_emails_left(user):
    """Invitation, recovery and 2FA setup emails this account can still receive this hour."""
    since = timezone.now() - timedelta(hours=1)
    sent = AuditEvent.objects.filter(
        target=user,
        action__in=[Action.INVITATION_SENT, Action.RECOVERY_LINK_SENT, Action.TWO_FACTOR_LINK_SENT],
        created_at__gte=since,
    ).count()
    return max(settings.PORTAL_ACCOUNT_EMAILS_PER_HOUR - sent, 0)


def events_in(location):
    """The account audit as the location's coordination sees it (plan, section 11).

    What happened in this location, plus what happened to the whole account (logins, passwords,
    2FA, deactivation) of the people with an active or future membership here. Events tied to
    other locations stay out: managers never see what a person does elsewhere (plan, section 4).
    """
    return AuditEvent.objects.filter(
        Q(location=location) | Q(location__isnull=True, target__in=members_of(location))
    ).select_related("actor", "target", "location")


@receiver(user_login_failed)
def record_failed_login(sender, credentials, request=None, **kwargs):
    email = normalise_email(credentials.get("username"))
    record(Action.LOGIN_FAILED, target=User.objects.filter(email=email).first(), email=email)
