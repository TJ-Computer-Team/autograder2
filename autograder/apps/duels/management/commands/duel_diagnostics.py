from django.core.management.base import BaseCommand

from ....index.models import GraderUser


class Command(BaseCommand):
    help = (
        "Read-only. Reports why the duels page may say nobody has a verified "
        "handle. Duelling needs BOTH cf_handle and cf_verified_at; several code "
        "paths clear one without the other."
    )

    def handle(self, *args, **options):
        users = GraderUser.objects.filter(is_active=True, is_tjioi=False)

        verified = users.filter(cf_verified_at__isnull=False)
        with_handle = users.exclude(cf_handle__isnull=True).exclude(cf_handle="")
        can_duel = verified.exclude(cf_handle__isnull=True).exclude(cf_handle="")

        self.stdout.write(f"active non-tjioi users:      {users.count()}")
        self.stdout.write(f"  cf_verified_at set:        {verified.count()}")
        self.stdout.write(f"  cf_handle set:             {with_handle.count()}")
        self.stdout.write(f"  BOTH (can duel):           {can_duel.count()}")

        # The telling case: verified but the handle was wiped from under them.
        orphaned = verified.filter(cf_handle__isnull=True) | verified.filter(
            cf_handle=""
        )
        orphaned_count = orphaned.distinct().count()
        if orphaned_count:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  {orphaned_count} users are verified but have NO handle."
                )
            )
            self.stdout.write(
                "  That is the signature of a bulk handle wipe: either "
                "reset_rankings, or toggling enforce_cf_handle_name_match in the "
                "admin, which runs GraderUser.objects.all().update(cf_handle=None)."
            )

        self.stdout.write("\nwho can duel:")
        for u in can_duel.order_by("username")[:25]:
            self.stdout.write(f"  {u.username:20} {u.cf_handle}")
        if not can_duel.exists():
            self.stdout.write("  (nobody)")
