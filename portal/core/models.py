from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    def get_by_natural_key(self, email):
        return super().get_by_natural_key(email.lower())

    def create_user(self, email, full_name, password=None, **extra_fields):
        """Without a password the account cannot log in until the person sets one."""
        user = self.model(email=email, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password, **extra_fields):
        return self.create_user(email, full_name, password, is_superuser=True, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=150)
    is_active = models.BooleanField(_("active"), default=True)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["email"]
        constraints = [
            # Together with unique=True, this makes e-mail addresses unique regardless of case.
            models.CheckConstraint(
                name="core_user_email_lowercase",
                condition=Q(email=Lower("email")),
                violation_error_message=_("The email address must be in lowercase."),
            ),
        ]

    @property
    def is_staff(self):
        """The backoffice is only for the admin, so this is not a separate flag."""
        return self.is_superuser

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    def clean(self):
        super().clean()
        self.email = self.email.lower()

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)


class Location(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    address = models.CharField(_("address"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("location")
        verbose_name_plural = _("locations")
        ordering = ["name"]

    def __str__(self):
        return self.name


class PeriodQuerySet(models.QuerySet):
    def active_on(self, date=None):
        """Rows in force on `date` (today in Lisbon by default). end_date is the last valid day."""
        date = date or timezone.localdate()
        return self.overlapping(date, date)

    def overlapping(self, start_date, end_date=None):
        """Rows sharing at least one day with the period; no end_date means open-ended."""
        rows = self.filter(Q(end_date__isnull=True) | Q(end_date__gte=start_date))
        if end_date is not None:
            rows = rows.filter(start_date__lte=end_date)
        return rows


class InclusiveDateRange(models.Func):
    function = "daterange"
    output_field = DateRangeField()

    def __init__(self, start, end):
        super().__init__(start, end, RangeBoundary(inclusive_upper=True))


def end_not_before_start_constraint(name):
    return models.CheckConstraint(
        name=name,
        condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
        violation_error_message=_("The end date cannot be before the start date."),
    )


class Period(models.Model):
    start_date = models.DateField(_("start date"), default=timezone.localdate)
    end_date = models.DateField(_("end date"), null=True, blank=True)

    objects = PeriodQuerySet.as_manager()

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        # On the field, not just the check constraint: the error excludes end_date from the
        # exclusion constraints, whose daterange() would otherwise raise on an inverted period.
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("The end date cannot be before the start date.")})


class Role(models.TextChoices):
    PROFESSIONAL = "professional", _("Professional")
    SECRETARIAT = "secretariat", _("Secretariat")
    COORDINATION = "coordination", _("Coordination / Technical direction")


class Subrole(models.TextChoices):
    RESIDENT = "resident", _("Resident")
    INTERN = "intern", _("Intern")


class Membership(Period):
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="memberships", verbose_name=_("user")
    )
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="memberships", verbose_name=_("location")
    )
    role = models.CharField(_("role"), max_length=20, choices=Role)
    subrole = models.CharField(_("subrole"), max_length=20, choices=Subrole, blank=True)

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        ordering = ["location", "user", "start_date"]
        constraints = [
            end_not_before_start_constraint("core_membership_end_not_before_start"),
            models.CheckConstraint(
                name="core_membership_subrole_matches_role",
                condition=(
                    Q(role=Role.PROFESSIONAL, subrole__in=Subrole.values)
                    | (~Q(role=Role.PROFESSIONAL) & Q(subrole=""))
                ),
                violation_error_message=_(
                    "A professional needs a subrole, and the other roles cannot have one."
                ),
            ),
            models.CheckConstraint(
                name="core_membership_intern_has_end_date",
                condition=~Q(subrole=Subrole.INTERN) | Q(end_date__isnull=False),
                violation_error_message=_("An intern's membership needs an end date."),
            ),
            ExclusionConstraint(
                name="core_membership_no_overlapping_role",
                expressions=[
                    ("user", RangeOperators.EQUAL),
                    ("location", RangeOperators.EQUAL),
                    ("role", RangeOperators.EQUAL),
                    (InclusiveDateRange("start_date", "end_date"), RangeOperators.OVERLAPS),
                ],
                violation_error_message=_(
                    "This person already has this role in this location on these dates."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.user} · {self.location} · {self.get_role_display()}"

    def clean(self):
        super().clean()
        # The admin is a technical account: no schedule, no hours, no place in a location.
        if self.user_id and self.user.is_superuser:
            raise ValidationError({"user": _("The admin account cannot have memberships.")})


class Mentorship(Period):
    mentor = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="mentorships_as_mentor",
        verbose_name=_("mentor"),
    )
    mentee = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="mentorships_as_mentee",
        verbose_name=_("mentee"),
    )
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="mentorships", verbose_name=_("location")
    )

    class Meta:
        verbose_name = _("mentorship")
        verbose_name_plural = _("mentorships")
        ordering = ["location", "mentor", "start_date"]
        constraints = [
            end_not_before_start_constraint("core_mentorship_end_not_before_start"),
            models.CheckConstraint(
                name="core_mentorship_mentor_is_not_mentee",
                condition=~Q(mentor=F("mentee")),
                violation_error_message=_("A person cannot mentor themselves."),
            ),
            ExclusionConstraint(
                name="core_mentorship_no_overlapping_pair",
                expressions=[
                    ("mentor", RangeOperators.EQUAL),
                    ("mentee", RangeOperators.EQUAL),
                    ("location", RangeOperators.EQUAL),
                    (InclusiveDateRange("start_date", "end_date"), RangeOperators.OVERLAPS),
                ],
                violation_error_message=_(
                    "This mentorship already exists in this location on these dates."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.mentor} → {self.mentee} · {self.location}"

    def clean(self):
        super().clean()
        if not self.location_id or not self.start_date:
            return
        professionals = Membership.objects.filter(
            location_id=self.location_id, role=Role.PROFESSIONAL
        ).overlapping(self.start_date, self.end_date)
        errors = {}
        if self.mentor_id and not professionals.filter(user_id=self.mentor_id).exists():
            errors["mentor"] = _(
                "The mentor needs a professional membership in this location on these dates."
            )
        if (
            self.mentee_id
            and not professionals.filter(user_id=self.mentee_id, subrole=Subrole.INTERN).exists()
        ):
            errors["mentee"] = _(
                "The mentee needs an intern membership in this location on these dates."
            )
        if errors:
            raise ValidationError(errors)


class AppendOnlyQuerySet(models.QuerySet):
    """History rows are never changed or removed; the database refuses it too (core.db)."""

    def update(self, **kwargs):
        raise TypeError(f"{self.model.__name__} rows cannot be changed.")

    def delete(self):
        raise TypeError(f"{self.model.__name__} rows cannot be deleted.")


class AppendOnlyModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError(f"{type(self).__name__} rows cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError(f"{type(self).__name__} rows cannot be deleted.")


class AuditEvent(AppendOnlyModel):
    """Account audit (plan, section 11): who did what to which account, and where."""

    class Action(models.TextChoices):
        INVITATION_SENT = "invitation_sent", _("Invitation sent")
        RECOVERY_LINK_SENT = "recovery_link_sent", _("Recovery link sent")
        PASSWORD_SET = "password_set", _("Password set")
        PASSWORD_CHANGED = "password_changed", _("Password changed")
        MEMBERSHIP_CREATED = "membership_created", _("Membership created")
        MEMBERSHIP_CHANGED = "membership_changed", _("Membership changed")
        MEMBERSHIP_ENDED = "membership_ended", _("Membership ended")
        MEMBERSHIP_DELETED = "membership_deleted", _("Membership deleted")
        ACCOUNT_DEACTIVATED = "account_deactivated", _("Account deactivated")
        ACCOUNT_REACTIVATED = "account_reactivated", _("Account reactivated")
        TWO_FACTOR_ENABLED = "two_factor_enabled", _("Two-factor authentication enabled")
        TWO_FACTOR_RESET = "two_factor_reset", _("Two-factor authentication reset")
        LOGIN_FAILED = "login_failed", _("Failed login")
        TWO_FACTOR_FAILED = "two_factor_failed", _("Failed two-factor code")

    created_at = models.DateTimeField(_("date and time"), default=timezone.now, db_index=True)
    action = models.CharField(_("action"), max_length=40, choices=Action)
    # Empty when nobody was signed in (a failed login) or the server did it (a management command).
    actor = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("done by"),
    )
    target = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("account"),
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("location"),
    )
    # The address typed in a failed login, which may not belong to any account.
    email = models.EmailField(_("email address"), blank=True)
    # {"before": {...}, "after": {...}} or other details of the action.
    details = models.JSONField(_("details"), default=dict, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name = _("account audit event")
        verbose_name_plural = _("account audit events")
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["email", "action", "created_at"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} · {self.get_action_display()}"
