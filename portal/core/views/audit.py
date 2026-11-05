import datetime

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils.formats import date_format

from core import permissions
from core.audit import events_in
from core.forms import AuditFilterForm
from core.models import Role, Subrole
from core.views.members import _location_with_perm

PAGE_SIZE = 50


@login_required
def audit_list(request, location_id):
    """Coordination's view of the account audit, limited to the location's members (plan, 11)."""
    location = _location_with_perm(request, location_id, permissions.VIEW_AUDIT)
    events = events_in(location)
    people = permissions.members_of(location).order_by("full_name")
    form = AuditFilterForm(request.GET or None, people=people)
    if form.is_valid():
        if form.cleaned_data["person"]:
            events = events.filter(target=form.cleaned_data["person"])
        if form.cleaned_data["action"]:
            events = events.filter(action=form.cleaned_data["action"])
    page = Paginator(events, PAGE_SIZE).get_page(request.GET.get("pagina"))
    for event in page:
        event.snapshots = {
            key: _snapshot_text(event.details[key])
            for key in ("before", "after")
            if isinstance(event.details.get(key), dict)
        }
    query = request.GET.copy()
    query.pop("pagina", None)
    context = {"location": location, "form": form, "page": page, "query": query.urlencode()}
    return render(request, "core/audit_list.html", context)


def _day(value):
    if not value:
        return "…"
    return date_format(datetime.date.fromisoformat(value), "SHORT_DATE_FORMAT")


def _snapshot_text(snapshot):
    """A membership or mentorship as it was recorded, in the words of the screens."""
    if "mentor" in snapshot:
        subject = f"{snapshot['mentor']} → {snapshot['mentee']}"
    else:
        subject = Role(snapshot["role"]).label if snapshot.get("role") in Role.values else ""
        if snapshot.get("subrole") in Subrole.values:
            subject = f"{subject} ({Subrole(snapshot['subrole']).label})"
    return f"{subject}, {_day(snapshot.get('start_date'))} – {_day(snapshot.get('end_date'))}"
