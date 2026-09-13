"""Fold the three ProblemOfTheWeek rows into a single POTW LectureSet.

ProblemOfTheWeek stores one row per level and is overwritten every week, so it has
no history. Representing a week as a LectureSet with three external entries keeps
the same page working while making past weeks browsable.

The ProblemOfTheWeek model is deliberately left in place; it is removed in a later
change so that rolling this back does not need the table recreated.
"""

from django.db import migrations

_LEVEL_TO_DIFFICULTY = {
    "beginner": "easy",
    "intermediate": "medium",
    "advanced": "hard",
}
_LEVEL_ORDER = ("beginner", "intermediate", "advanced")

SLUG = "problem-of-the-week"


def absorb(apps, schema_editor):
    ProblemOfTheWeek = apps.get_model("index", "ProblemOfTheWeek")
    LectureSet = apps.get_model("lectures", "LectureSet")
    LectureSetEntry = apps.get_model("lectures", "LectureSetEntry")

    rows = {p.level: p for p in ProblemOfTheWeek.objects.all()}
    # Only carry over levels that actually have a link; a row with no link is a
    # placeholder, and an entry with neither problem nor url violates the
    # internal-xor-external constraint.
    usable = [lvl for lvl in _LEVEL_ORDER if lvl in rows and rows[lvl].link]
    if not usable:
        return

    lecture_set, _ = LectureSet.objects.get_or_create(
        slug=SLUG,
        defaults={
            "title": "Problem of the Week",
            "kind": "potw",
            "label_style": "none",
            "published": True,
        },
    )

    for order, level in enumerate(usable):
        row = rows[level]
        LectureSetEntry.objects.get_or_create(
            lecture_set=lecture_set,
            external_url=row.link,
            defaults={
                "order": order,
                "difficulty": _LEVEL_TO_DIFFICULTY[level],
                "external_title": row.title or f"Problem of the Week: {level.title()}",
            },
        )


def unabsorb(apps, schema_editor):
    LectureSet = apps.get_model("lectures", "LectureSet")
    # Entries cascade with the set.
    LectureSet.objects.filter(slug=SLUG, kind="potw").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("lectures", "0001_initial"),
        ("index", "0013_add_intermediate_potw"),
    ]

    operations = [migrations.RunPython(absorb, unabsorb)]
