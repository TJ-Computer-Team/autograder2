# Generated by Django 5.1.7 on 2025-07-13 00:50

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("problems", "0001_initial"),
        ("runtests", "0004_remove_submission_problemid_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="submission",
            name="problem",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="problems.problem"
            ),
        ),
    ]
