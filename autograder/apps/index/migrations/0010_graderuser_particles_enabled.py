# Generated by Django 5.1.7 on 2025-07-16 17:34

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("index", "0009_graderuser_usaco_rating"),
    ]

    operations = [
        migrations.AddField(
            model_name="graderuser",
            name="particles_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
