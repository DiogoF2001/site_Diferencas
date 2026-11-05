from django.contrib import admin, messages
from django.contrib.admin import AdminSite
from django.contrib.auth.models import Group
from django.utils.translation import gettext as _
from django_otp import user_has_device
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import accounts
from core.audit import Action, membership_snapshot, mentorship_snapshot, record
from core.models import AuditEvent, Location, Membership, Mentorship, User

# Access comes from memberships in a location, never from Django groups.
admin.site.unregister(Group)
# The device admin would show other people's secrets; 2FA is reset from the portal or reset_2fa.
admin.site.unregister(TOTPDevice)


def _has_permission(request):
    """Besides TwoFactorMiddleware: the backoffice never opens without the second factor."""
    return AdminSite.has_permission(admin.site, request) and request.user.is_verified()


admin.site.has_permission = _has_permission


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Not Django's UserAdmin: nobody sets another person's password, not even the admin."""

    list_display = ["email", "full_name", "is_active", "is_superuser", "two_factor"]
    list_filter = ["is_active", "is_superuser"]
    search_fields = ["email", "full_name"]
    fields = ["email", "full_name", "is_active", "is_superuser", "date_joined", "last_login"]
    readonly_fields = ["is_superuser", "date_joined", "last_login"]

    @admin.display(boolean=True, description="2FA")
    def two_factor(self, obj):
        return user_has_device(obj)

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        return [*readonly, "is_active"] if obj and obj.is_superuser else readonly

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)
        if change and "is_active" in form.changed_data:
            action = Action.ACCOUNT_REACTIVATED if obj.is_active else Action.ACCOUNT_DEACTIVATED
            record(action, actor=request.user, target=obj)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "location", "role", "subrole", "start_date", "end_date"]
    list_filter = ["location", "role", "subrole"]
    search_fields = ["user__email", "user__full_name"]
    autocomplete_fields = ["user"]

    def save_model(self, request, obj, form, change):
        before = membership_snapshot(Membership.objects.get(pk=obj.pk)) if change else None
        super().save_model(request, obj, form, change)
        action = Action.MEMBERSHIP_CHANGED if change else Action.MEMBERSHIP_CREATED
        details = {"after": membership_snapshot(obj)}
        if before:
            details["before"] = before
        record(action, actor=request.user, target=obj.user, location=obj.location, **details)
        if before is None or before["role"] != obj.role:
            self._send_two_factor_link(request, obj)

    def _send_two_factor_link(self, request, membership):
        """As in the portal: the role stands, and a failed email is audited and warned about."""
        sent = accounts.offer_two_factor_link(request, membership, actor=request.user)
        if sent == Action.TWO_FACTOR_LINK_FAILED:
            self.message_user(request, accounts.LINK_FAILED_MESSAGE, messages.WARNING)
        elif sent:
            self.message_user(request, _("The link to set up 2FA was sent by email."))

    def delete_model(self, request, obj):
        before = membership_snapshot(obj)
        super().delete_model(request, obj)
        record(
            Action.MEMBERSHIP_DELETED,
            actor=request.user,
            target=obj.user,
            location=obj.location,
            before=before,
        )

    def delete_queryset(self, request, queryset):
        for membership in queryset:
            self.delete_model(request, membership)


@admin.register(Mentorship)
class MentorshipAdmin(admin.ModelAdmin):
    list_display = ["mentor", "mentee", "location", "start_date", "end_date"]
    list_filter = ["location"]
    search_fields = ["mentor__email", "mentee__email"]
    autocomplete_fields = ["mentor", "mentee"]

    def save_model(self, request, obj, form, change):
        before = mentorship_snapshot(Mentorship.objects.get(pk=obj.pk)) if change else None
        super().save_model(request, obj, form, change)
        action = Action.MENTORSHIP_CHANGED if change else Action.MENTORSHIP_CREATED
        details = {"after": mentorship_snapshot(obj)}
        if before:
            details["before"] = before
        record(action, actor=request.user, target=obj.mentee, location=obj.location, **details)

    def delete_model(self, request, obj):
        before = mentorship_snapshot(obj)
        super().delete_model(request, obj)
        record(
            Action.MENTORSHIP_DELETED,
            actor=request.user,
            target=obj.mentee,
            location=obj.location,
            before=before,
        )

    def delete_queryset(self, request, queryset):
        for mentorship in queryset:
            self.delete_model(request, mentorship)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Read-only: the history is only ever added to."""

    list_display = ["created_at", "action", "actor", "target", "location", "email"]
    list_filter = ["action", "location"]
    search_fields = ["target__email", "actor__email", "email"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
