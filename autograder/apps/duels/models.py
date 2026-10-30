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

    # Set when this duel is a Blitz Cup match. A match can take more than one duel
    # (a sudden-death rematch after a draw).
    bracket_match = models.ForeignKey(
        "CupMatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duels",
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
        if self.bracket_match_id:
            from .cup import duel_finished

            duel_finished(self)


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


class Ladder(models.Model):
    """A fixed sequence of Codeforces problems that everyone climbs at their own pace.

    Solving your current rung reveals the next one. Most solves when time runs out
    wins; ties go to whoever got there first. A skip moves you up without a point.
    Like duels, nothing is graded here -- everything is read back from the CF API.
    """

    PENDING = "pending"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    STATUS_CHOICES = (
        (PENDING, "Waiting to start"),
        (ACTIVE, "In progress"),
        (FINISHED, "Finished"),
        (CANCELLED, "Cancelled"),
    )

    host = models.ForeignKey(
        "index.GraderUser", on_delete=models.CASCADE, related_name="ladders_hosted"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)

    # Rung ratings ramp evenly from rating_min to rating_max.
    rating_min = models.IntegerField(default=800)
    rating_max = models.IntegerField(default=1600)
    rung_count = models.PositiveIntegerField(default=8)
    tags = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated Codeforces tags."
    )
    duration_minutes = models.PositiveIntegerField(default=60)
    skips = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(default=timezone.now)
    start_requested_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    selection_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Ladder {self.pk} by {self.host} ({self.status})"

    @property
    def deadline(self):
        if self.started_at is None:
            return None
        return self.started_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_overdue(self):
        deadline = self.deadline
        return deadline is not None and timezone.now() >= deadline

    def standings(self):
        """Most solves first; among equals, whoever reached that count earliest."""
        return self.entries.select_related("user").order_by(
            "-solved",
            models.F("last_solve_at").asc(nulls_last=True),
            "joined_at",
        )

    def finish(self):
        self.status = self.FINISHED
        self.ended_at = timezone.now()
        self.save(update_fields=["status", "ended_at"])


class LadderRung(models.Model):
    ladder = models.ForeignKey(Ladder, on_delete=models.CASCADE, related_name="rungs")
    # 1-based.
    position = models.PositiveIntegerField()
    cf_contest_id = models.IntegerField()
    cf_index = models.CharField(max_length=5)
    cf_name = models.CharField(max_length=200, blank=True)
    cf_rating = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("ladder", "position")
        constraints = [
            models.UniqueConstraint(
                fields=("ladder", "position"), name="ladderrung_unique_position"
            )
        ]

    def __str__(self):
        return f"#{self.position} {self.cf_contest_id}{self.cf_index}"

    @property
    def problem_url(self):
        return (
            f"https://codeforces.com/problemset/problem/"
            f"{self.cf_contest_id}/{self.cf_index}"
        )


class LadderEntry(models.Model):
    ladder = models.ForeignKey(Ladder, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey("index.GraderUser", on_delete=models.CASCADE)
    joined_at = models.DateTimeField(default=timezone.now)

    # The rung you are on (1-based). Past the last rung means you are done.
    position = models.PositiveIntegerField(default=1)
    solved = models.PositiveIntegerField(default=0)
    skips_used = models.PositiveIntegerField(default=0)
    # CF time of your latest accepted rung; the tiebreak.
    last_solve_at = models.DateTimeField(null=True, blank=True)
    # CF time of every accepted rung, oldest first, as ISO strings. Drives the graph.
    solve_times = models.JSONField(default=list, blank=True)
    # When you reached the current rung. Only submissions after this count, so an
    # accepted run from before you could see the problem never advances you.
    reached_at = models.DateTimeField(null=True, blank=True)
    # Rungs a late joiner had already solved on CF before joining. They are passed
    # over without a point, or the joiner could paste an old solution.
    presolved = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("ladder", "joined_at")
        constraints = [
            models.UniqueConstraint(
                fields=("ladder", "user"), name="ladderentry_unique_user"
            )
        ]

    def __str__(self):
        return f"{self.user} on rung {self.position}"

    @property
    def presolved_positions(self):
        return {int(p) for p in self.presolved.split(",") if p}

    @property
    def is_done(self):
        return self.position > self.ladder.rung_count

    @property
    def skips_left(self):
        return max(0, self.ladder.skips - self.skips_used)

    def move_up(self):
        """Advance one rung, passing over any rungs solved before joining."""
        presolved = self.presolved_positions
        self.position += 1
        while self.position in presolved:
            self.position += 1
        self.reached_at = timezone.now()


class Cup(models.Model):
    """A live single-elimination tournament of 1v1 duels, run by staff.

    Every match in a round is played at the same time; staff start each round once
    the previous one is done. A match is an ordinary Duel, so the duel page, winner
    detection and forfeits all work unchanged.
    """

    REGISTRATION = "registration"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    STATUS_CHOICES = (
        (REGISTRATION, "Registration open"),
        (RUNNING, "In progress"),
        (FINISHED, "Finished"),
        (CANCELLED, "Cancelled"),
    )

    name = models.CharField(max_length=100, default="Blitz Cup")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=REGISTRATION
    )
    created_by = models.ForeignKey(
        "index.GraderUser", on_delete=models.SET_NULL, null=True, related_name="+"
    )

    # Round 1 draws from rating_min-rating_max; each later round adds rating_step.
    rating_min = models.IntegerField(default=800)
    rating_max = models.IntegerField(default=1100)
    rating_step = models.IntegerField(default=200)
    duel_minutes = models.PositiveIntegerField(default=15)
    sudden_death_minutes = models.PositiveIntegerField(default=10)

    # 0 until the bracket is drawn. A round is "started" once its duels exist.
    current_round = models.PositiveIntegerField(default=0)
    round_count = models.PositiveIntegerField(default=0)
    champion = models.ForeignKey(
        "index.GraderUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Why the last round could not start, shown to staff on the bracket.
    error = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} ({self.status})"

    def rating_range(self, round_number):
        bump = self.rating_step * (round_number - 1)
        return self.rating_min + bump, self.rating_max + bump

    def round_name(self, round_number):
        from_end = self.round_count - round_number
        return {0: "Final", 1: "Semifinals", 2: "Quarterfinals"}.get(
            from_end, f"Round {round_number}"
        )


class CupEntry(models.Model):
    cup = models.ForeignKey(Cup, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey("index.GraderUser", on_delete=models.CASCADE)
    seed = models.PositiveIntegerField(null=True, blank=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("cup", "seed", "joined_at")
        constraints = [
            models.UniqueConstraint(fields=("cup", "user"), name="cupentry_unique_user")
        ]

    def __str__(self):
        return f"{self.user} (seed {self.seed})"


class CupMatch(models.Model):
    """One slot in the bracket. The winner moves to match slot // 2 of the next round."""

    cup = models.ForeignKey(Cup, on_delete=models.CASCADE, related_name="matches")
    round = models.PositiveIntegerField()
    # 0-based, top to bottom within the round.
    slot = models.PositiveIntegerField()
    player_a = models.ForeignKey(
        "index.GraderUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    player_b = models.ForeignKey(
        "index.GraderUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # A round-1 match with one player is a bye and is won the moment it is drawn.
    is_bye = models.BooleanField(default=False)
    winner = models.ForeignKey(
        "index.GraderUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # How it was decided when it wasn't a plain solve: bye, seed, staff.
    decided_by = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ("cup", "round", "slot")
        constraints = [
            models.UniqueConstraint(
                fields=("cup", "round", "slot"), name="cupmatch_unique_slot"
            )
        ]

    def __str__(self):
        return f"R{self.round} #{self.slot}: {self.player_a} vs {self.player_b}"

    @property
    def players(self):
        return [p for p in (self.player_a, self.player_b) if p is not None]

    def loser(self):
        if self.winner_id is None:
            return None
        return self.player_b if self.winner_id == self.player_a_id else self.player_a
