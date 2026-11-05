from core.permissions import upcoming_two_factor_roles


def two_factor_notice(request):
    """Plan, section 5: until a role requiring 2FA starts, remind the person to set it up."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or user.is_verified():
        return {}
    return {"upcoming_two_factor_roles": list(upcoming_two_factor_roles(user))}
