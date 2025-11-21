# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("problems", "0013_problem_interactor_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="problem",
            name="pid",
            field=models.IntegerField(blank=True, null=True, unique=True),
        ),
    ]

