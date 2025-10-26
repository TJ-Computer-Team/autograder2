from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.contrib.postgres.fields import ArrayField


class GraderUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class GraderUser(AbstractBaseUser, PermissionsMixin):
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"
    PLATINUM = "Platinum"
    NOT_PARTICIPATED = "Not Participated"
    USACO_DIVISIONS = {
        BRONZE: "Bronze",
        SILVER: "Silver",
        GOLD: "Gold",
        PLATINUM: "Platinum",
        NOT_PARTICIPATED: "Not Participated",
    }

    email = models.EmailField()
    personal_email = models.EmailField(blank=True, null=True)
    display_name = models.CharField(max_length=30)
    username = models.CharField(max_length=30, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    usaco_division = models.CharField(
        max_length=20, choices=USACO_DIVISIONS, default=BRONZE
    )
    usaco_rating = models.IntegerField(default=800)
    cf_handle = models.CharField(max_length=30, blank=True, null=True)
    cf_rating = models.IntegerField(blank=True, null=True, default=0)
    grade = models.CharField(max_length=10, default="N/A")
    first_time = models.BooleanField(default=True)
    is_tjioi = models.BooleanField(default=False)
    author_drops = models.IntegerField(default=0)

    inhouses = ArrayField(
        models.DecimalField(max_digits=10, decimal_places=3), default=list
    )
    inhouse = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    index = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    use_writer_formula = models.BooleanField(default=False)

    particles_enabled = models.BooleanField(default=True)

    objects = GraderUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]  # for createsuperuser

    def __str__(self):
        return self.email
