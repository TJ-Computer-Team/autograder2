from django.db import models
from django.utils import timezone
from ..index.models import GraderUser

class Contest(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    rated = models.BooleanField(default=False)
    season = models.IntegerField()
    tjioi = models.BooleanField(default=False)
    start = models.DateTimeField()
    end = models.DateTimeField()
    editorial = models.URLField(null=True, blank=True)
    writers = models.ManyToManyField(GraderUser)
    # The only admins who get admin privileges on this contest before it ends.
    # Every other admin is treated as a regular participant until then, and the
    # contest, its problems and its submissions are hidden from them in the
    # admin site, so a contest can't leak to admins who might compete in it.
    visible_to = models.ManyToManyField(
        GraderUser, related_name="visible_contests", blank=True
    )

    def __str__(self):
        return self.name

    @classmethod
    def locked_for(cls, user):
        """Contests ``user`` has no admin privileges on (yet)."""
        return cls.objects.filter(end__gt=timezone.now()).exclude(visible_to=user)

    def is_admin_for(self, user):
        """Whether ``user`` gets admin privileges on this contest.

        Use this instead of a bare ``user.is_staff`` for anything scoped to a
        contest. Once the contest ends there is nothing left to leak, so every
        admin regains access.
        """
        if not user.is_staff:
            return False
        if self.end <= timezone.now():
            return True
        return self.visible_to.filter(pk=user.pk).exists()
