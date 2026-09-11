from django.core.management.base import BaseCommand
from django.core.management import call_command

from ....index.models import GraderUser


class Command(BaseCommand):
    help = "Updates the user rankings based on contest performance and other metrics."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting user ranking update..."))

        users = GraderUser.objects.filter(is_tjioi=False, is_staff=False)

        for user in users:
            user.usaco_division = GraderUser.USACO_DIVISIONS[GraderUser.NOT_PARTICIPATED]
            user.usaco_rating = 800
            user.cf_rating = 0
            user.cf_handle = ""
            user.save()

        call_command("update_rankings")

        self.stdout.write(self.style.SUCCESS("Ranking reset complete."))
