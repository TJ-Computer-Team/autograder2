from django.db import migrations, models


def backfill_numbers(apps, schema_editor):
    Problem = apps.get_model("problems", "Problem")
    for number, problem in enumerate(Problem.objects.order_by("id"), start=1):
        problem.number = number
        problem.save(update_fields=["number"])


class Migration(migrations.Migration):
    dependencies = [
        ("problems", "0015_alter_problem_contest"),
    ]

    operations = [
        migrations.AddField(
            model_name="problem",
            name="number",
            field=models.IntegerField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="problem",
            name="number",
            field=models.IntegerField(editable=False, unique=True),
        ),
    ]
