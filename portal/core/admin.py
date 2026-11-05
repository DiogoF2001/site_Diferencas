from django.contrib import admin
from django.contrib.auth.models import Group

from core.models import Location, Membership, Mentorship, User

# Access comes from memberships in a location, never from Django groups.
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Not Django's UserAdmin: nobody sets another person's password, not even the admin."""

    list_display = ["email", "full_name", "is_active", "is_superuser"]
    list_filter = ["is_active", "is_superuser"]
    search_fields = ["email", "full_name"]
    fields = ["email", "full_name", "is_active", "is_superuser", "date_joined", "last_login"]
    readonly_fields = ["is_superuser", "date_joined", "last_login"]

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        return [*readonly, "is_active"] if obj and obj.is_superuser else readonly

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)


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


@admin.register(Mentorship)
class MentorshipAdmin(admin.ModelAdmin):
    list_display = ["mentor", "mentee", "location", "start_date", "end_date"]
    list_filter = ["location"]
    search_fields = ["mentor__email", "mentee__email"]
    autocomplete_fields = ["mentor", "mentee"]
