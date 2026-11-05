import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured

from core.models import Location, Membership, Role, Subrole, User
from core.permissions import (
    PermissionRule,
    assignable_roles,
    can_assign_role,
    can_manage_account,
    can_remove_from_location,
    filter_by_perm,
    has_perm_in,
    locations_with_perm,
    mentees_of,
    register_permissions,
    registered_permissions,
    role_level_in,
)
from core.tests.helpers import make_account, make_member, make_mentorship

pytestmark = pytest.mark.django_db

MANAGE = "core.manage_members"


@pytest.fixture
def polo_a():
    return Location.objects.create(name="Polo A")


@pytest.fixture
def polo_b():
    return Location.objects.create(name="Polo B")


def member(name, location, role, **fields):
    user = make_account(name)
    make_member(user, location, role, **fields)
    return user


# Registry


def test_modules_are_discovered_when_the_app_loads():
    assert {"core.manage_members", "salas.approve"} <= registered_permissions()


def test_unknown_permission_raises(polo_a):
    with pytest.raises(ImproperlyConfigured):
        has_perm_in(make_account("pessoa"), "salas.typo", polo_a)
    with pytest.raises(ImproperlyConfigured):
        locations_with_perm(make_account("outra"), "salas.typo")


def test_declaring_a_permission_twice_raises():
    with pytest.raises(ImproperlyConfigured):
        register_permissions("core", {"manage_members": PermissionRule()})


def test_global_permission_cannot_be_given_to_roles():
    with pytest.raises(ImproperlyConfigured):
        register_permissions(
            "core", {"bad": PermissionRule(is_global=True, roles=frozenset({Role.COORDINATION}))}
        )


def test_location_permission_without_a_location_raises():
    with pytest.raises(ValueError):
        has_perm_in(make_account("admin", is_superuser=True), MANAGE)


def test_global_permission_has_no_locations():
    with pytest.raises(ValueError):
        locations_with_perm(make_account("admin", is_superuser=True), "core.technical_area")


# Who counts


def test_anonymous_user_holds_nothing(polo_a):
    anonymous = AnonymousUser()

    assert has_perm_in(anonymous, "salas.view_availability", polo_a) is False
    assert has_perm_in(anonymous, "core.technical_area") is False
    assert not locations_with_perm(anonymous, "salas.view_availability").exists()


def test_deactivated_account_holds_nothing(polo_a):
    user = member("pessoa", polo_a, Role.COORDINATION)
    user.is_active = False
    user.save()

    assert has_perm_in(user, MANAGE, polo_a) is False
    assert not locations_with_perm(user, MANAGE).exists()


def test_deactivated_admin_holds_nothing(polo_a):
    admin = make_account("admin", is_superuser=True, is_active=False)

    assert has_perm_in(admin, MANAGE, polo_a) is False
    assert has_perm_in(admin, "core.technical_area") is False
    assert not locations_with_perm(admin, MANAGE).exists()


def test_permissions_of_two_roles_in_the_same_location_add_up(polo_a):
    user = member("pessoa", polo_a, Role.PROFESSIONAL)
    make_member(user, polo_a, Role.COORDINATION)

    assert has_perm_in(user, "salas.submit_request", polo_a) is True
    assert has_perm_in(user, "salas.book_directly", polo_a) is True


def test_different_roles_in_different_locations_do_not_mix(polo_a, polo_b):
    user = member("pessoa", polo_a, Role.COORDINATION)
    make_member(user, polo_b, Role.PROFESSIONAL)

    assert has_perm_in(user, "core.view_audit", polo_a) is True
    assert has_perm_in(user, "core.view_audit", polo_b) is False
    assert has_perm_in(user, "salas.submit_request", polo_a) is False
    assert has_perm_in(user, "salas.submit_request", polo_b) is True


@pytest.mark.parametrize(
    "start,end,active",
    [
        pytest.param(0, 30, True, id="first_day"),
        pytest.param(-30, 0, True, id="last_day"),
        pytest.param(-30, None, True, id="open_ended"),
        pytest.param(1, 30, False, id="starts_tomorrow"),
        pytest.param(-30, -1, False, id="ended_yesterday"),
    ],
)
def test_membership_dates_are_inclusive(start, end, active, polo_a):
    user = member("pessoa", polo_a, Role.PROFESSIONAL, start=start, end=end)

    assert has_perm_in(user, "salas.submit_request", polo_a) is active


def test_the_day_changes_at_midnight_in_lisbon_not_in_utc(polo_a):
    # 23:30 on 30 June in UTC is already 00:30 on 1 July in Lisbon, which is on summer time.
    moment = datetime.datetime(2026, 6, 30, 23, 30, tzinfo=ZoneInfo("UTC"))
    ending = make_account("termina")
    Membership.objects.create(
        user=ending,
        location=polo_a,
        role=Role.PROFESSIONAL,
        subrole=Subrole.INTERN,
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 6, 30),
    )
    starting = make_account("comeca")
    Membership.objects.create(
        user=starting,
        location=polo_a,
        role=Role.PROFESSIONAL,
        subrole=Subrole.RESIDENT,
        start_date=datetime.date(2026, 7, 1),
    )

    with mock.patch("django.utils.timezone.now", return_value=moment):
        assert has_perm_in(ending, "salas.submit_request", polo_a) is False
        assert has_perm_in(starting, "salas.submit_request", polo_a) is True


# Inactive locations


def test_inactive_location_gives_members_nothing_until_it_is_reactivated(polo_a):
    user = member("pessoa", polo_a, Role.COORDINATION)
    polo_a.is_active = False
    polo_a.save()

    assert has_perm_in(user, MANAGE, polo_a) is False
    assert not locations_with_perm(user, MANAGE).exists()
    assert role_level_in(user, polo_a) == 0

    polo_a.is_active = True
    polo_a.save()

    assert has_perm_in(user, MANAGE, polo_a) is True


def test_admin_keeps_access_to_an_inactive_location(polo_a):
    admin = make_account("admin", is_superuser=True)
    polo_a.is_active = False
    polo_a.save()

    assert has_perm_in(admin, MANAGE, polo_a) is True
    assert polo_a in locations_with_perm(admin, MANAGE)


# Admin account


def test_stray_membership_of_the_admin_does_not_change_its_permissions(polo_a):
    admin = make_account("admin", is_superuser=True)
    make_member(admin, polo_a, Role.PROFESSIONAL)

    assert has_perm_in(admin, "salas.submit_request", polo_a) is False
    assert role_level_in(admin, polo_a) == 0


# Query helpers


def test_filter_by_perm_keeps_only_the_locations_with_the_permission(polo_a, polo_b):
    user = member("pessoa", polo_a, Role.SECRETARIAT)
    make_member(user, polo_b, Role.PROFESSIONAL)
    rows = Membership.objects.all()

    assert {row.location for row in filter_by_perm(rows, user, MANAGE)} == {polo_a}


def test_filter_by_perm_follows_a_relation(polo_a, polo_b):
    user = member("pessoa", polo_a, Role.SECRETARIAT)
    other = member("outra", polo_b, Role.SECRETARIAT)

    people = User.objects.distinct()
    filtered = filter_by_perm(people, user, MANAGE, location_field="memberships__location")

    assert user in filtered
    assert other not in filtered


def test_filter_by_perm_returns_nothing_without_the_permission(polo_a):
    user = member("pessoa", polo_a, Role.PROFESSIONAL)

    assert not filter_by_perm(Membership.objects.all(), user, MANAGE).exists()


def test_expired_role_does_not_leak_through_an_active_one(polo_a):
    # A location where the permission comes from an expired row and another role is still active.
    user = member("pessoa", polo_a, Role.SECRETARIAT, start=-30, end=-1)
    make_member(user, polo_a, Role.PROFESSIONAL)

    assert has_perm_in(user, MANAGE, polo_a) is False
    assert not locations_with_perm(user, MANAGE).exists()


# Role ceiling


@pytest.mark.parametrize(
    "actor_role,assignable",
    [
        # A professional has a level but no right to manage members, so not even their own role.
        (Role.PROFESSIONAL, []),
        (Role.SECRETARIAT, [Role.PROFESSIONAL, Role.SECRETARIAT]),
        (Role.COORDINATION, [Role.PROFESSIONAL, Role.SECRETARIAT, Role.COORDINATION]),
    ],
)
def test_roles_can_be_given_up_to_the_actors_own_level(actor_role, assignable, polo_a):
    actor = member("pessoa", polo_a, actor_role)

    assert assignable_roles(actor, polo_a) == assignable
    for role in Role:
        assert can_assign_role(actor, role, polo_a) is (role in assignable)


def test_admin_can_give_every_role(polo_a):
    admin = make_account("admin", is_superuser=True)

    assert assignable_roles(admin, polo_a) == list(Role)


def test_ceiling_is_per_location(polo_a, polo_b):
    actor = member("pessoa", polo_a, Role.COORDINATION)
    make_member(actor, polo_b, Role.SECRETARIAT)

    assert can_assign_role(actor, Role.COORDINATION, polo_a) is True
    assert can_assign_role(actor, Role.COORDINATION, polo_b) is False
    assert can_assign_role(actor, Role.SECRETARIAT, polo_b) is True


def test_role_elsewhere_gives_no_right_to_assign_here(polo_a, polo_b):
    actor = member("pessoa", polo_a, Role.COORDINATION)

    assert assignable_roles(actor, polo_b) == []


def test_ceiling_uses_the_highest_active_role(polo_a):
    actor = member("pessoa", polo_a, Role.PROFESSIONAL)
    make_member(actor, polo_a, Role.COORDINATION)

    assert can_assign_role(actor, Role.COORDINATION, polo_a) is True


def test_ceiling_ignores_an_expired_higher_role(polo_a):
    actor = member("pessoa", polo_a, Role.COORDINATION, start=-30, end=-1)
    make_member(actor, polo_a, Role.SECRETARIAT)

    assert can_assign_role(actor, Role.COORDINATION, polo_a) is False
    assert can_assign_role(actor, Role.SECRETARIAT, polo_a) is True


def test_unknown_role_raises(polo_a):
    with pytest.raises(ValueError):
        can_assign_role(make_account("admin", is_superuser=True), "owner", polo_a)


# Removing from a location


@pytest.mark.parametrize(
    "actor_role,target_role,allowed",
    [
        (Role.PROFESSIONAL, Role.PROFESSIONAL, False),
        (Role.SECRETARIAT, Role.PROFESSIONAL, True),
        (Role.SECRETARIAT, Role.SECRETARIAT, True),
        (Role.SECRETARIAT, Role.COORDINATION, False),
        (Role.COORDINATION, Role.COORDINATION, True),
    ],
)
def test_removal_needs_the_targets_level(actor_role, target_role, allowed, polo_a):
    actor = member("gestora", polo_a, actor_role)
    target = member("alvo", polo_a, target_role)

    assert can_remove_from_location(actor, target, polo_a) is allowed


def test_removal_counts_the_targets_highest_role(polo_a):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_a, Role.COORDINATION)

    assert can_remove_from_location(actor, target, polo_a) is False


def test_removal_counts_a_role_that_has_yet_to_start(polo_a):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_a, Role.COORDINATION, start=5, end=30)

    assert can_remove_from_location(actor, target, polo_a) is False


def test_removal_ignores_the_targets_role_elsewhere(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.COORDINATION)

    assert can_remove_from_location(actor, target, polo_a) is True


def test_removal_needs_a_role_in_that_location(polo_a, polo_b):
    actor = member("gestora", polo_b, Role.COORDINATION)
    target = member("alvo", polo_a, Role.PROFESSIONAL)

    assert can_remove_from_location(actor, target, polo_a) is False


def test_nothing_to_remove_without_a_membership(polo_a):
    admin = make_account("admin", is_superuser=True)
    actor = member("gestora", polo_a, Role.COORDINATION)
    target = member("alvo", polo_a, Role.PROFESSIONAL, start=-30, end=-1)

    assert can_remove_from_location(actor, target, polo_a) is False
    assert can_remove_from_location(admin, target, polo_a) is False


def test_admin_can_remove_anyone_with_a_membership(polo_a):
    admin = make_account("admin", is_superuser=True)
    target = member("alvo", polo_a, Role.COORDINATION)

    assert can_remove_from_location(admin, target, polo_a) is True


# Actions on the whole account


def test_account_action_with_a_level_at_least_equal_in_every_location(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    make_member(actor, polo_b, Role.COORDINATION)
    target = member("alvo", polo_a, Role.SECRETARIAT)
    make_member(target, polo_b, Role.PROFESSIONAL)

    assert can_manage_account(actor, target) is True


def test_account_action_denied_if_one_location_is_missing(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.COORDINATION)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.PROFESSIONAL)

    assert can_manage_account(actor, target) is False


def test_account_action_compares_location_by_location_not_the_highest_overall(polo_a, polo_b):
    # The actor's highest level is above the target's, but below it in polo B.
    actor = member("gestora", polo_a, Role.COORDINATION)
    make_member(actor, polo_b, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.COORDINATION)

    assert can_manage_account(actor, target) is False


def test_account_action_denied_with_a_lower_level(polo_a):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.COORDINATION)

    assert can_manage_account(actor, target) is False


def test_account_action_needs_the_right_to_manage_members_not_only_the_level(polo_a):
    actor = member("gestora", polo_a, Role.PROFESSIONAL)
    target = member("alvo", polo_a, Role.PROFESSIONAL)

    assert can_manage_account(actor, target) is False


def test_account_action_denied_when_the_actors_membership_expired(polo_a):
    actor = member("gestora", polo_a, Role.COORDINATION, start=-30, end=-1)
    target = member("alvo", polo_a, Role.PROFESSIONAL)

    assert can_manage_account(actor, target) is False


def test_account_action_ignores_the_targets_expired_memberships(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.COORDINATION, start=-30, end=-1)

    assert can_manage_account(actor, target) is True


def test_account_action_denied_if_the_target_will_be_in_a_location_the_actor_is_not(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.COORDINATION, start=1, end=30)

    assert can_manage_account(actor, target) is False


def test_account_action_denied_if_the_target_will_outrank_the_actor_in_the_location(polo_a):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_a, Role.COORDINATION, start=5, end=30)

    assert can_manage_account(actor, target) is False


def test_account_action_allowed_with_the_level_for_the_targets_future_role(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    make_member(actor, polo_b, Role.COORDINATION)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.COORDINATION, start=5, end=30)

    assert can_manage_account(actor, target) is True


def test_account_that_has_not_started_can_be_managed_up_to_the_actors_level(polo_a):
    actor = member("gestora", polo_a, Role.SECRETARIAT)
    created = member("nova", polo_a, Role.SECRETARIAT, start=5, end=30)
    above = member("acima", polo_a, Role.COORDINATION, start=5, end=30)

    assert can_manage_account(actor, created) is True
    assert can_manage_account(actor, above) is False


def test_account_that_has_not_started_elsewhere_cannot_be_managed_from_here(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.COORDINATION)
    target = member("alvo", polo_b, Role.PROFESSIONAL, start=5, end=30)

    assert can_manage_account(actor, target) is False


def test_actors_own_future_role_does_not_count(polo_a):
    actor = member("gestora", polo_a, Role.COORDINATION, start=5, end=30)
    target = member("alvo", polo_a, Role.PROFESSIONAL)

    assert can_manage_account(actor, target) is False


def test_target_with_a_future_membership_in_an_inactive_location_is_only_for_the_admin(
    polo_a, polo_b
):
    actor = member("gestora", polo_a, Role.COORDINATION)
    make_member(actor, polo_b, Role.COORDINATION)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.PROFESSIONAL, start=5, end=30)
    polo_b.is_active = False
    polo_b.save()

    assert can_manage_account(actor, target) is False
    assert can_manage_account(make_account("admin", is_superuser=True), target) is True


def test_target_whose_memberships_have_all_ended_is_only_for_the_admin(polo_a):
    actor = member("gestora", polo_a, Role.COORDINATION)
    target = member("alvo", polo_a, Role.PROFESSIONAL, start=-30, end=-1)

    assert can_manage_account(actor, target) is False
    assert can_manage_account(make_account("admin", is_superuser=True), target) is True


def test_deactivated_target_keeps_its_level(polo_a):
    target = member("alvo", polo_a, Role.COORDINATION)
    target.is_active = False
    target.save()

    assert can_manage_account(member("sec", polo_a, Role.SECRETARIAT), target) is False
    assert can_manage_account(member("coord", polo_a, Role.COORDINATION), target) is True


def test_target_in_an_inactive_location_is_only_for_the_admin(polo_a, polo_b):
    actor = member("gestora", polo_a, Role.COORDINATION)
    make_member(actor, polo_b, Role.COORDINATION)
    target = member("alvo", polo_a, Role.PROFESSIONAL)
    make_member(target, polo_b, Role.PROFESSIONAL)
    polo_b.is_active = False
    polo_b.save()

    assert can_manage_account(actor, target) is False
    assert can_manage_account(make_account("admin", is_superuser=True), target) is True


def test_nobody_acts_on_their_own_account(polo_a):
    coordinator = member("gestora", polo_a, Role.COORDINATION)
    admin = make_account("admin", is_superuser=True)

    assert can_manage_account(coordinator, coordinator) is False
    assert can_manage_account(admin, admin) is False


def test_members_cannot_act_on_the_admin_account(polo_a):
    # The admin has no memberships, which must not read as "a level in all of none of them".
    actor = member("gestora", polo_a, Role.COORDINATION)

    assert can_manage_account(actor, make_account("admin", is_superuser=True)) is False


def test_stray_membership_does_not_let_members_act_on_the_admin_account(polo_a):
    actor = member("gestora", polo_a, Role.COORDINATION)
    admin = make_account("admin", is_superuser=True)
    make_member(admin, polo_a, Role.PROFESSIONAL)

    assert can_manage_account(actor, admin) is False


def test_admin_can_act_on_any_other_account(polo_a):
    target = member("alvo", polo_a, Role.COORDINATION)

    assert can_manage_account(make_account("admin", is_superuser=True), target) is True


def test_anonymous_user_cannot_act_on_an_account(polo_a):
    target = member("alvo", polo_a, Role.PROFESSIONAL)

    assert can_manage_account(AnonymousUser(), target) is False


# Mentorships


@pytest.fixture
def mentor(polo_a):
    return member("orientadora", polo_a, Role.PROFESSIONAL)


@pytest.fixture
def mentee(polo_a):
    return member("orientanda", polo_a, Role.PROFESSIONAL, subrole=Subrole.INTERN)


def test_mentor_reaches_the_mentee(mentor, mentee, polo_a):
    make_mentorship(mentor, mentee, polo_a)

    assert list(mentees_of(mentor, polo_a)) == [mentee]


def test_mentorship_only_goes_from_mentor_to_mentee(mentor, mentee, polo_a):
    make_mentorship(mentor, mentee, polo_a)

    assert not mentees_of(mentee, polo_a).exists()


def test_mentorship_is_per_location(mentor, mentee, polo_a, polo_b):
    make_mentorship(mentor, mentee, polo_a)
    make_member(mentor, polo_b, Role.PROFESSIONAL)
    make_member(mentee, polo_b, Role.PROFESSIONAL, subrole=Subrole.INTERN)

    assert not mentees_of(mentor, polo_b).exists()


def test_other_professionals_do_not_reach_the_mentee(mentor, mentee, polo_a):
    make_mentorship(mentor, mentee, polo_a)

    assert not mentees_of(member("outra", polo_a, Role.PROFESSIONAL), polo_a).exists()


@pytest.mark.parametrize(
    "start,end", [pytest.param(-30, -1, id="ended"), pytest.param(1, 30, id="not_started")]
)
def test_mentorship_outside_its_dates_reaches_nobody(start, end, mentor, mentee, polo_a):
    make_mentorship(mentor, mentee, polo_a, start=start, end=end)

    assert not mentees_of(mentor, polo_a).exists()


def test_mentor_with_an_expired_membership_reaches_nobody(mentee, polo_a):
    mentor = member("orientadora", polo_a, Role.PROFESSIONAL, start=-30, end=-1)
    make_mentorship(mentor, mentee, polo_a)

    assert not mentees_of(mentor, polo_a).exists()


def test_mentor_who_is_no_longer_a_professional_reaches_nobody(mentee, polo_a):
    mentor = member("orientadora", polo_a, Role.PROFESSIONAL, start=-30, end=-1)
    make_member(mentor, polo_a, Role.SECRETARIAT)
    make_mentorship(mentor, mentee, polo_a)

    assert not mentees_of(mentor, polo_a).exists()


def test_mentee_with_an_expired_membership_is_not_reached(mentor, polo_a):
    mentee = member("orientanda", polo_a, Role.PROFESSIONAL, subrole=Subrole.INTERN, end=-1)
    make_mentorship(mentor, mentee, polo_a)

    assert not mentees_of(mentor, polo_a).exists()


def test_mentee_who_is_no_longer_an_intern_is_not_reached(mentor, polo_a):
    mentee = member("orientanda", polo_a, Role.PROFESSIONAL, subrole=Subrole.RESIDENT)
    make_mentorship(mentor, mentee, polo_a)

    assert not mentees_of(mentor, polo_a).exists()


def test_deactivated_accounts_break_the_relation(mentor, mentee, polo_a):
    make_mentorship(mentor, mentee, polo_a)

    mentee.is_active = False
    mentee.save()
    assert not mentees_of(mentor, polo_a).exists()

    mentee.is_active = True
    mentee.save()
    mentor.is_active = False
    mentor.save()
    assert not mentees_of(mentor, polo_a).exists()


def test_inactive_location_breaks_the_relation(mentor, mentee, polo_a):
    make_mentorship(mentor, mentee, polo_a)
    polo_a.is_active = False
    polo_a.save()

    assert not mentees_of(mentor, polo_a).exists()
