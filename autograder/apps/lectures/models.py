import re
import string

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# Matches both Codeforces problem URL shapes:
#   /problemset/problem/1234/A
#   /contest/1234/problem/A   (also /gym/1234/problem/A)
_CF_URL_RE = re.compile(
    r"codeforces\.com/(?:problemset/problem/|(?:contest|gym)/)"
    r"(?P<contest>\d+)/(?:problem/)?(?P<index>[A-Za-z]\d*)",
    re.IGNORECASE,
)


def parse_codeforces_url(url):
    """(contest_id, index) for a Codeforces problem URL, else (None, None)."""
    if not url:
        return None, None
    match = _CF_URL_RE.search(url)
    if not match:
        return None, None
    return int(match.group("contest")), match.group("index").upper()


class LectureSet(models.Model):
    LECTURE = "lecture"
    POTW = "potw"
    KIND_CHOICES = (
        (LECTURE, "Lecture"),
        (POTW, "Problem of the Week"),
    )

    LETTERS = "letters"
    NUMBERS = "numbers"
    NONE = "none"
    LABEL_STYLE_CHOICES = (
        (LETTERS, "Letters (A, B, C)"),
        (NUMBERS, "Numbers (1, 2, 3)"),
        (NONE, "No labels"),
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=LECTURE)

    topic = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField(
        null=True, blank=True, help_text="Lecture date, or the week for a POTW set."
    )

    label_style = models.CharField(
        max_length=10, choices=LABEL_STYLE_CHOICES, default=LETTERS
    )
    published = models.BooleanField(
        default=False, help_text="Unpublished sets are only visible to staff."
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-created_at")

    def __str__(self):
        return self.title

    def label_for(self, index):
        """Label for the entry at 0-based position `index`, per this set's style."""
        if self.label_style == self.NUMBERS:
            return str(index + 1)
        if self.label_style == self.LETTERS:
            # Past Z, continue AA, AB, ... rather than running out.
            letters = string.ascii_uppercase
            label = ""
            n = index
            while True:
                label = letters[n % 26] + label
                n = n // 26 - 1
                if n < 0:
                    break
            return label
        return ""


class LectureSetEntry(models.Model):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    DIFFICULTY_CHOICES = (
        (EASY, "Easy"),
        (MEDIUM, "Medium"),
        (HARD, "Hard"),
    )

    lecture_set = models.ForeignKey(
        LectureSet, on_delete=models.CASCADE, related_name="entries"
    )
    order = models.PositiveIntegerField(default=0)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, blank=True)
    note = models.CharField(max_length=300, blank=True)

    # Exactly one of these two sides is used. An internal problem keeps its own
    # contest FK untouched, so the same problem can appear in any number of sets.
    problem = models.ForeignKey(
        "problems.Problem", on_delete=models.CASCADE, null=True, blank=True
    )
    external_title = models.CharField(max_length=200, blank=True)
    external_url = models.URLField(blank=True)

    # Parsed from external_url on save. Stored for a later "solved on Codeforces"
    # feature; nothing reads these yet.
    cf_contest_id = models.IntegerField(null=True, blank=True)
    cf_index = models.CharField(max_length=5, blank=True)

    class Meta:
        ordering = ("order", "id")
        verbose_name_plural = "entries"
        constraints = [
            models.CheckConstraint(
                # Exactly one side: an internal problem or an external link.
                condition=(
                    models.Q(problem__isnull=False, external_url="")
                    | models.Q(problem__isnull=True) & ~models.Q(external_url="")
                ),
                name="problemsetentry_internal_xor_external",
            )
        ]

    def __str__(self):
        return f"{self.lecture_set.title}: {self.display_title}"

    @property
    def is_external(self):
        return self.problem_id is None

    @property
    def display_title(self):
        if self.problem_id is not None:
            return self.problem.name
        return self.external_title or self.external_url

    def clean(self):
        if self.problem_id is not None and self.external_url:
            raise ValidationError(
                "Choose either an internal problem or an external link, not both."
            )
        if self.problem_id is None and not self.external_url:
            raise ValidationError("Set either an internal problem or an external link.")

    def save(self, *args, **kwargs):
        if self.external_url:
            self.cf_contest_id, self.cf_index = parse_codeforces_url(self.external_url)
            self.cf_index = self.cf_index or ""
        else:
            self.cf_contest_id, self.cf_index = None, ""
        super().save(*args, **kwargs)
