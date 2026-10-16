from django.conf import settings
from django.db import migrations, models


def allow_existing_admins(apps, schema_editor):
    # Existing contests keep today's behaviour: every current admin can see them.
    Contest = apps.get_model("contests", "Contest")
    GraderUser = apps.get_model("index", "GraderUser")
    staff = list(GraderUser.objects.filter(is_staff=True))
    for contest in Contest.objects.all():
        contest.visible_to.add(*staff)


class Migration(migrations.Migration):

    dependencies = [
        ("contests", "0003_contest_writers"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="contest",
            name="visible_to",
            field=models.ManyToManyField(
                blank=True,
                related_name="visible_contests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(allow_existing_admins, migrations.RunPython.noop),
    ]
