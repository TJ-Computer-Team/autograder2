# Generated by Django 5.1.7 on 2025-07-07 15:41

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="GraderUser",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                ("email", models.EmailField(max_length=254, unique=True)),
                (
                    "personal_email",
                    models.EmailField(blank=True, max_length=254, null=True),
                ),
                ("display_name", models.CharField(max_length=30)),
                ("username", models.CharField(max_length=30)),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                (
                    "usaco_division",
                    models.CharField(
                        choices=[
                            ("Bronze", "Bronze"),
                            ("Silver", "Silver"),
                            ("Gold", "Gold"),
                            ("Platinum", "Platinum"),
                            ("Not Participated", "Not Participated"),
                        ],
                        default="Bronze",
                        max_length=20,
                    ),
                ),
                ("cf_handle", models.CharField(blank=True, max_length=30, null=True)),
                ("cf_rating", models.IntegerField(blank=True, default=0, null=True)),
                ("grade", models.CharField(default="N/A", max_length=10)),
                ("first_time", models.BooleanField(default=True)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
