from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView

urlpatterns = [
    # One sign-in page for everyone: the backoffice's own would skip the lockout.
    path(
        "admin/login/",
        RedirectView.as_view(url=reverse_lazy("login"), query_string=True),
    ),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
