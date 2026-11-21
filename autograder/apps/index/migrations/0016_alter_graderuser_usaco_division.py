from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("index", "0015_graderuser_cf_verified_at_attendancesession_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="graderuser",
            name="usaco_division",
            field=models.CharField(
                choices=[
                    ("Bronze", "Bronze"),
                    ("Silver", "Silver"),
                    ("Gold", "Gold"),
                    ("Platinum", "Platinum"),
                    ("Camper", "Camper"),
                    ("Not Participated", "Not Participated"),
                ],
                default="Bronze",
                max_length=20,
            ),
        ),
    ]
