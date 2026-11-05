from django.contrib.auth import views as auth_views
from django.urls import path

from core.views import auth, health, members, two_factor

urlpatterns = [
    path("healthz/", health.healthz, name="healthz"),
    path("", auth.home, name="home"),
    path("conta/entrar/", auth.LoginView.as_view(), name="login"),
    path("conta/sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("conta/palavra-passe/", auth.PasswordChangeView.as_view(), name="password_change"),
    path("conta/definir/<uidb64>/<token>/", auth.PasswordSetView.as_view(), name="password_set"),
    path("conta/recuperar/", auth.SelfPasswordResetView.as_view(), name="password_reset"),
    path("conta/2fa/configurar/", two_factor.setup, name="two_factor_setup"),
    path("conta/2fa/ativar/", two_factor.enrol, name="two_factor_enrol"),
    path("conta/2fa/verificar/", two_factor.verify, name="two_factor_verify"),
    path("polos/<int:location_id>/membros/", members.member_list, name="member_list"),
    path("polos/<int:location_id>/membros/novo/", members.member_add, name="member_add"),
    path(
        "polos/<int:location_id>/membros/<int:user_id>/remover/",
        members.member_remove,
        name="member_remove",
    ),
    path(
        "polos/<int:location_id>/membros/<int:user_id>/desativar/",
        members.account_deactivate,
        name="account_deactivate",
    ),
    path(
        "polos/<int:location_id>/membros/<int:user_id>/reativar/",
        members.account_reactivate,
        name="account_reactivate",
    ),
    path(
        "polos/<int:location_id>/membros/<int:user_id>/repor-2fa/",
        members.account_reset_two_factor,
        name="account_reset_two_factor",
    ),
    path(
        "polos/<int:location_id>/membros/<int:user_id>/enviar-link/",
        members.account_send_link,
        name="account_send_link",
    ),
    path(
        "polos/<int:location_id>/profissionais/",
        members.professional_list,
        name="professional_list",
    ),
]
