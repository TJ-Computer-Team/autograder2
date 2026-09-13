from datetime import timedelta

from django.db import models
from django.utils import timezone


class Duel(models.Model):
    """A race between two people to solve one Codeforces problem.

    Nothing is graded here: both players submit on codeforces.com and the server
    decides the winner by polling the CF API. The grader's own Submission model is
    untouched, so duels never reach the coderunner or affect contest standings.
    """

    PENDING = "pending"
    ACTIVE = "active"
    FINISHED = "finished"
    DECLINED = "declined"
    EXPIRED = "expired"
    STATUS_CHOICES = (
        (PENDING, "Waiting to be accepted"),
        (ACTIVE, "In progress"),
        (FINISHED, "Finished"),
        (DECLINED, "Declined"),
        (EXPIRED, "Expired"),
    )

    SOLVED = "solved"
    FORFEIT = "forfeit"
    TIMEOUT = "timeout"
    VOIDED = "voided"
    END_REASON_CHOICES = (
        (SOLVED, "Solved"),
        (FORFEIT, "Forfeit"),
        (TIMEOUT, "Ran out of time"),
        (VOIDED, "Voided by staff"),
    )

    # How long a challenge waits to be accepted before it stops cluttering the list.
    CHALLENGE_TTL = timedelta(minutes=5)

    challenger = models.ForeignKey(
        "index.GraderUser", on_delete=models.CASCADE, related_name="duels_challenged"
    )
    opponent = models.ForeignKey(
        "index.GraderUser", on_delete=models.CASCADE, related_name="duels_received"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)

    # Chosen by the challenger; the opponent sees these before accepting.
    rating_min = models.IntegerField(default=800)
    rating_max = models.IntegerField(default=1200)
    tags = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated Codeforces tags."
    )

    # Filled in once a problem has been drawn.
    cf_contest_id = models.IntegerField(null=True, blank=True)
    cf_index = models.CharField(max_length=5, blank=True)
    cf_name = models.CharField(max_length=200, blank=True)
    cf_rating = models.IntegerField(null=True, blank=True)

    duration_minutes = models.PositiveIntegerField(default=45)

    created_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    winner = models.ForeignKey(
        "index.GraderUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duels_won",
    )
    end_reason = models.CharField(max_length=20, choices=END_REASON_CHOICES, blank=True)
    selection_error = models.CharField(max_length=300, blank=True)

    # Reserved for the Blitz Cup so a bracket can attach later without a data
    # migration. Nothing reads it yet.
    bracket_match = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Unused; placeholder for the Blitz Cup bracket.",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.challenger} vs {self.opponent} ({self.status})"

    # -- participants ----------------------------------------------------------

    @property
    def players(self):
        return (self.challenger, self.opponent)

    def includes(self, user):
        return user.id in (self.challenger_id, self.opponent_id)

    def other_player(self, user):
        return self.opponent if user.id == self.challenger_id else self.challenger

    # -- timing ----------------------------------------------------------------

    @property
    def deadline(self):
        if self.started_at is None:
            return None
        return self.started_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_overdue(self):
        deadline = self.deadline
        return deadline is not None and timezone.now() >= deadline

    @property
    def challenge_is_stale(self):
        return (
            self.status == self.PENDING
            and timezone.now() >= self.created_at + self.CHALLENGE_TTL
        )

    @property
    def problem_url(self):
        if self.cf_contest_id is None or not self.cf_index:
            return ""
        return (
            f"https://codeforces.com/problemset/problem/"
            f"{self.cf_contest_id}/{self.cf_index}"
        )

    # -- transitions -----------------------------------------------------------

    def finish(self, winner, reason):
        self.winner = winner
        self.end_reason = reason
        self.status = self.FINISHED
        self.ended_at = timezone.now()
        self.save(update_fields=["winner", "end_reason", "status", "ended_at"])


class DuelSubmission(models.Model):
    """A Codeforces submission observed during a duel.

    Stored so the live view has something to render and the result stays auditable
    once the duel is over and the CF API window has moved on.
    """

    duel = models.ForeignKey(Duel, on_delete=models.CASCADE, related_name="submissions")
    user = models.ForeignKey("index.GraderUser", on_delete=models.CASCADE)
    cf_submission_id = models.BigIntegerField()
    # Null while Codeforces is still judging.
    verdict = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("duel", "cf_submission_id"),
                name="duelsubmission_unique_per_duel",
            )
        ]

    def __str__(self):
        return f"{self.user} {self.verdict or 'judging'} ({self.cf_submission_id})"

    @property
    def is_accepted(self):
        return self.verdict == "OK"
