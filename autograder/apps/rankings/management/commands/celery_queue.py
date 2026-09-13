from django.core.management.base import BaseCommand

from autograder.celery import app


class Command(BaseCommand):
    help = (
        "Inspect or purge the Celery queue. Exists because the box is not "
        "SSH-reachable for most of the team, so a backed-up queue is otherwise "
        "invisible and unclearable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Discard every queued task. Safe: these are all retryable "
            "refresh/index jobs, not user data.",
        )

    def handle(self, *args, **options):
        with app.connection_for_read() as conn:
            depth = conn.default_channel.client.llen("default")
        self.stdout.write(f"default queue depth: {depth}")

        inspect = app.control.inspect(timeout=5)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        if not active and not reserved:
            self.stdout.write(self.style.WARNING("no workers replied"))
        for worker in set(active) | set(reserved):
            self.stdout.write(
                f"  {worker}: {len(active.get(worker, []))} active, "
                f"{len(reserved.get(worker, []))} reserved"
            )

        if options["purge"]:
            purged = app.control.purge()
            self.stdout.write(self.style.SUCCESS(f"purged {purged} tasks"))
            with app.connection_for_read() as conn:
                self.stdout.write(
                    f"depth now: {conn.default_channel.client.llen('default')}"
                )
