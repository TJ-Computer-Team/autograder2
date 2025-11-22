from django.db import models
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
    writers = models.ManyToManyField(GraderUser, blank=True, related_name='writers')

    def __str__(self):
        return self.name
