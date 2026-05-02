import os
import logging
import zipfile
import tempfile
import shutil
from django.conf import settings
from pathlib import Path
from ..apps.problems.models import Problem

logger = logging.getLogger(__name__)


def add_problem_to_coderunner(pid: int):
    loc = Path("/home/tjctgrader/problems") / str(pid)

    try:
        loc.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Dir error for adding problem {pid}: {e}")
        return

    try:
        script_dir = Path(__file__).parent
        checker_path = script_dir / "default_checker.py"
        checker = checker_path.read_text()
        (loc / "default_checker.py").write_text(checker)
    except Exception as e:
        logger.error(f"Write error: {e}")
        return

    logger.info(f"Added problem {pid} to filesystem")


def add_tests_to_coderunner(pid: int):
    try:
        problem = Problem.objects.get(id=pid)
        if not problem.testcases_zip or not hasattr(problem.testcases_zip, "path"):
            logger.warning(f"No zip file found for problem {pid}.")
            return

        base_path = Path(settings.BASE_DIR).parent / "problems" / str(pid)
        sol_dir = base_path / "sol"
        test_dir = base_path / "test"

        try:
            if sol_dir.exists():
                shutil.rmtree(sol_dir)
            if test_dir.exists():
                shutil.rmtree(test_dir)
            sol_dir.mkdir(parents=True, exist_ok=True)
            test_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Dir error: {e}")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(problem.testcases_zip.path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)
                names = zip_ref.namelist()

            testcases = {}
            for name in names:
                full_path = os.path.join(tmpdir, name)
                if not os.path.isfile(full_path):
                    continue

                base, ext = os.path.splitext(name)
                if not base.isdigit() or ext not in [".in", ".out"]:
                    logger.error(f"Invalid file name: {name}")
                    return

                tid = int(base)
                if tid not in testcases:
                    testcases[tid] = {}

                with open(full_path, "r") as f:
                    content = f.read()
                    if ext == ".in":
                        testcases[tid]["test"] = content
                    else:
                        testcases[tid]["out"] = content

            for tid, tc in testcases.items():
                try:
                    (test_dir / str(tid)).write_text(tc["test"])
                    (sol_dir / str(tid)).write_text(tc["out"])
                except Exception as e:
                    logger.error(f"Write error for test {tid}: {e}")
                    return

    except Problem.DoesNotExist:
        logger.error(f"Problem {pid} not found for test upload.")
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during test upload for {pid}: {e}"
        )

    logger.info(f"Added tests for problem {pid}")
