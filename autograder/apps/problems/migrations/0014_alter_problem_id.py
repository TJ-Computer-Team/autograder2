# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("problems", "0013_problem_interactor_file"),
    ]

    operations = [
        migrations.AlterField(
            model_name="problem",
            name="id",
            field=models.IntegerField(primary_key=True, serialize=False),
        ),
    ]

