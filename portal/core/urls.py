from django.contrib.auth import views as auth_views
from django.urls import path

from core.views import audit, auth, health, members, mentorships, two_factor

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
    path("conta/2fa/link/<uidb64>/<token>/", two_factor.link, name="two_factor_link"),
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
        "polos/<int:location_id>/membros/<int:user_id>/enviar-link-2fa/",
        members.account_send_two_factor_link,
        name="account_send_two_factor_link",
    ),
    path(
        "polos/<int:location_id>/filiacoes/<int:membership_id>/alterar/",
        members.membership_edit,
        name="membership_edit",
    ),
    path(
        "polos/<int:location_id>/orientacoes/",
        mentorships.mentorship_list,
        name="mentorship_list",
    ),
    path(
        "polos/<int:location_id>/orientacoes/nova/",
        mentorships.mentorship_add,
        name="mentorship_add",
    ),
    path(
        "polos/<int:location_id>/orientacoes/<int:mentorship_id>/alterar/",
        mentorships.mentorship_edit,
        name="mentorship_edit",
    ),
    path(
        "polos/<int:location_id>/orientacoes/<int:mentorship_id>/terminar/",
        mentorships.mentorship_end,
        name="mentorship_end",
    ),
    path("polos/<int:location_id>/auditoria/", audit.audit_list, name="audit_list"),
    path(
        "polos/<int:location_id>/profissionais/",
        members.professional_list,
        name="professional_list",
    ),
]
