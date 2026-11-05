"""Mentorship actions of the portal (plan, section 4). Each checks its permission and is audited.

The audit row's account is the mentee: a mentorship is about whose schedule and hours the
mentor sees, and the mentee is the person it exposes.
"""

import datetime

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core import permissions
from core.audit import Action, mentorship_snapshot, record
from core.models import Membership, Mentorship, Role, Subrole, User


def _check(actor, location):
    if not permissions.has_perm_in(actor, permissions.MANAGE_MENTORSHIPS, location):
        raise PermissionDenied


def current(location):
    """Active and future mentorships in the location; the ended ones stay in the audit."""
    return (
        Mentorship.objects.filter(location=location)
        .overlapping(timezone.localdate())
        .select_related("mentor", "mentee")
        .order_by("mentor__full_name", "mentee__full_name", "start_date")
    )


def _professionals(location, **filters):
    memberships = Membership.objects.filter(
        location=location, role=Role.PROFESSIONAL, **filters
    ).overlapping(timezone.localdate())
    return User.objects.filter(pk__in=memberships.values("user")).order_by("full_name")


def possible_mentors(location):
    return _professionals(location)


def possible_mentees(location):
    return _professionals(location, subrole=Subrole.INTERN)


@transaction.atomic
def create_mentorship(actor, location, *, mentor, mentee, start, end):
    _check(actor, location)
    mentorship = Mentorship(
        mentor=mentor, mentee=mentee, location=location, start_date=start, end_date=end
    )
    mentorship.full_clean()
    mentorship.save()
    record(
        Action.MENTORSHIP_CREATED,
        actor=actor,
        target=mentee,
        location=location,
        after=mentorship_snapshot(mentorship),
    )
    return mentorship


@transaction.atomic
def change_mentorship(actor, mentorship, *, start, end):
    _check(actor, mentorship.location)
    mentorship = Mentorship.objects.select_for_update().get(pk=mentorship.pk)
    if mentorship.end_date is not None and mentorship.end_date < timezone.localdate():
        raise PermissionDenied
    before = mentorship_snapshot(mentorship)
    mentorship.check_change(start, end)
    mentorship.start_date, mentorship.end_date = start, end
    mentorship.full_clean()
    mentorship.save()
    after = mentorship_snapshot(mentorship)
    if after != before:
        record(
            Action.MENTORSHIP_CHANGED,
            actor=actor,
            target=mentorship.mentee,
            location=mentorship.location,
            before=before,
            after=after,
        )
    return mentorship


@transaction.atomic
def end_mentorship(actor, mentorship):
    """End it yesterday, so the mentor stops seeing the mentee at once, as when removing someone
    from a location. One that starts today or later never took effect and is deleted.
    """
    _check(actor, mentorship.location)
    mentorship = Mentorship.objects.select_for_update().get(pk=mentorship.pk)
    today = timezone.localdate()
    if mentorship.end_date is not None and mentorship.end_date < today:
        raise PermissionDenied
    before = mentorship_snapshot(mentorship)
    common = {"actor": actor, "target": mentorship.mentee, "location": mentorship.location}
    if mentorship.start_date >= today:
        mentorship.delete()
        record(Action.MENTORSHIP_DELETED, before=before, **common)
    else:
        mentorship.end_date = today - datetime.timedelta(days=1)
        mentorship.save(update_fields=["end_date"])
        record(
            Action.MENTORSHIP_ENDED, before=before, after=mentorship_snapshot(mentorship), **common
        )
