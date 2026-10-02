from django.db import models, transaction


def renumber_problems(ordered_pks):
    """Give ``ordered_pks`` the problem numbers they currently hold, reassigned
    top-down in the given order (first pk gets the highest of those numbers).

    Numbers are only permuted among these problems, so the full set stays a
    dense 1..n however many (or few) rows the admin had on screen.
    """
    with transaction.atomic():
        current = dict(
            Problem.objects.select_for_update()
            .filter(pk__in=ordered_pks)
            .values_list("pk", "number")
        )
        if set(current) != set(ordered_pks) or len(ordered_pks) != len(current):
            raise ValueError("Unknown or duplicate problem ids")
        numbers = sorted(current.values(), reverse=True)
        _assign_numbers(dict(zip(ordered_pks, numbers)), current)


def compact_problem_numbers():
    """Close any holes so numbers run 1..n, keeping the existing order."""
    with transaction.atomic():
        current = dict(
            Problem.objects.select_for_update()
            .order_by("number")
            .values_list("pk", "number")
        )
        _assign_numbers({pk: i for i, pk in enumerate(current, start=1)}, current)


def _assign_numbers(wanted, current):
    changed = {pk: n for pk, n in wanted.items() if current[pk] != n}
    if not changed:
        return
    # `number` is unique and Postgres checks that per row, so swapping values
    # directly collides. Park the moving rows on negatives first.
    for pk in changed:
        Problem.objects.filter(pk=pk).update(number=-pk)
    for pk, n in changed.items():
        Problem.objects.filter(pk=pk).update(number=n)


class Problem(models.Model):
    # Internal and stable: URLs, submissions and the coderunner's
    # /home/tjctgrader/problems/<id> directories all key on it.
    id = models.IntegerField(primary_key=True)
    # The number shown to people. Always a dense 1..n, set by drag-and-drop
    # in the admin; new problems go on top as n+1.
    number = models.IntegerField(unique=True, editable=False)
    name = models.CharField(max_length=255)
    # Null for lecture-only problems: a problem written for a lecture set never
    # belongs to a contest, and inventing a placeholder contest for it was the
    # exact workaround lecture sets exist to remove.
    contest = models.ForeignKey(
        "contests.Contest", on_delete=models.CASCADE, null=True, blank=True
    )
    points = models.IntegerField()
    contest_letter = models.CharField(max_length=1, default="A")

    statement = models.TextField()
    inputtxt = models.TextField()
    outputtxt = models.TextField()
    samples = models.TextField()

    tl = models.IntegerField(null=True, blank=True)
    ml = models.IntegerField(null=True, blank=True)

    interactive = models.BooleanField(default=False)
    secret = models.BooleanField(default=False)

    testcases_zip = models.FileField(upload_to="problem_testcases/", blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from django.db.models import Max

        # Auto-increment id if this is a new object and id wasn't provided
        if not self.pk and self.id is None:
            max_id = Problem.objects.aggregate(Max("id"))["id__max"]
            self.id = (max_id or 0) + 1
        if self.number is None:
            max_number = Problem.objects.aggregate(Max("number"))["number__max"]
            self.number = (max_number or 0) + 1
        super().save(*args, **kwargs)
        if self.interactive and self.testcases_zip:
            self._process_interactive_problem()

    def _process_interactive_problem(self):
        import zipfile
        import os
        import subprocess
        from pathlib import Path

        problem_dir = Path(f"/home/tjctgrader/problems/{self.id}")
        problem_dir.mkdir(parents=True, exist_ok=True)
        test_dir = problem_dir / "test"
        answer_dir = problem_dir / "answer"
        queries_dir = problem_dir / "queries"
        test_dir.mkdir(parents=True, exist_ok=True)
        answer_dir.mkdir(parents=True, exist_ok=True)
        queries_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(self.testcases_zip.path, "r") as zip_ref:
            for file_info in zip_ref.filelist:
                filename = os.path.basename(file_info.filename)
                if not filename:
                    continue

                if filename.startswith("interactor."):
                    interactor_content = zip_ref.read(file_info.filename)

                    if filename.endswith(".py"):
                        interactor_path = problem_dir / "interactor.py"
                        interactor_path.write_bytes(interactor_content)
                        os.chmod(interactor_path, 0o755)

                    elif filename.endswith(".cpp"):
                        cpp_path = problem_dir / "interactor.cpp"
                        cpp_path.write_bytes(interactor_content)

                        result = subprocess.run(
                            [
                                "/usr/bin/g++",
                                "-std=c++17",
                                "-O2",
                                "-o",
                                str(problem_dir / "interactor"),
                                str(cpp_path),
                            ],
                            capture_output=True,
                        )

                        if result.returncode == 0:
                            cpp_path.unlink()
                        else:
                            raise Exception(
                                f"C++ compilation failed: {result.stderr.decode()}"
                            )

                    elif filename.endswith(".java"):
                        java_path = problem_dir / "Interactor.java"
                        java_path.write_bytes(interactor_content)

                        result = subprocess.run(
                            ["/usr/bin/javac", str(java_path)],
                            capture_output=True,
                            cwd=str(problem_dir),
                        )

                        if result.returncode == 0:
                            wrapper_path = problem_dir / "interactor"
                            wrapper_path.write_text(
                                f'#!/bin/bash\njava -cp {problem_dir} Interactor "$@"\n'
                            )
                            os.chmod(wrapper_path, 0o755)
                        else:
                            raise Exception(
                                f"Java compilation failed: {result.stderr.decode()}"
                            )

                elif filename.endswith("_answer.txt"):
                    # Secret answer files for interactor
                    test_content = zip_ref.read(file_info.filename)
                    (answer_dir / filename).write_bytes(test_content)

                elif filename.endswith("_queries.txt"):
                    # Query limit files (optional)
                    test_content = zip_ref.read(file_info.filename)
                    (queries_dir / filename).write_bytes(test_content)

                elif filename.endswith(".txt"):
                    # Public input files for user
                    test_content = zip_ref.read(file_info.filename)
                    (test_dir / filename).write_bytes(test_content)
