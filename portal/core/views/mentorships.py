from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core import mentorships, permissions
from core.forms import MentorshipDatesForm, MentorshipForm
from core.views.members import _add_errors, _location_with_perm


def _location(request, location_id):
    return _location_with_perm(request, location_id, permissions.MANAGE_MENTORSHIPS)


@login_required
def mentorship_list(request, location_id):
    location = _location(request, location_id)
    context = {"location": location, "mentorships": mentorships.current(location)}
    return render(request, "core/mentorship_list.html", context)


@login_required
def mentorship_add(request, location_id):
    location = _location(request, location_id)
    form = MentorshipForm(
        request.POST or None,
        mentors=mentorships.possible_mentors(location),
        mentees=mentorships.possible_mentees(location),
    )
    if form.is_valid():
        data = form.cleaned_data
        try:
            mentorships.create_mentorship(
                request.user,
                location,
                mentor=data["mentor"],
                mentee=data["mentee"],
                start=data["start_date"],
                end=data["end_date"],
            )
        except ValidationError as error:
            _add_errors(form, error, fields=set(form.fields))
        else:
            messages.success(request, _("The mentorship was added."))
            return redirect("mentorship_list", location.pk)
    return render(request, "core/mentorship_form.html", {"location": location, "form": form})


@login_required
def mentorship_edit(request, location_id, mentorship_id):
    location = _location(request, location_id)
    mentorship = get_object_or_404(mentorships.current(location), pk=mentorship_id)
    form = MentorshipDatesForm(request.POST or None, mentorship=mentorship)
    if form.is_valid():
        try:
            mentorships.change_mentorship(
                request.user,
                mentorship,
                start=form.cleaned_data["start_date"],
                end=form.cleaned_data["end_date"],
            )
        except ValidationError as error:
            _add_errors(form, error, fields=set(form.fields))
        else:
            messages.success(request, _("The mentorship was changed."))
            return redirect("mentorship_list", location.pk)
    context = {"location": location, "mentorship": mentorship, "form": form}
    return render(request, "core/mentorship_form.html", context)


@require_POST
@login_required
def mentorship_end(request, location_id, mentorship_id):
    location = _location(request, location_id)
    mentorship = get_object_or_404(mentorships.current(location), pk=mentorship_id)
    mentorships.end_mentorship(request.user, mentorship)
    messages.success(request, _("The mentorship was ended."))
    return redirect("mentorship_list", location.pk)
