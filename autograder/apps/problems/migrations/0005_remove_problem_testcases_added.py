# Generated by Django 5.1.7 on 2025-07-17 22:19

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("problems", "0004_problem_testcases_added"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="problem",
            name="testcases_added",
        ),
    ]
