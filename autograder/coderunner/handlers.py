import subprocess
import os
import re
from pathlib import Path
from .runner import run_code
from ..apps.runtests.models import Submission
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

import logging

logger = logging.getLogger(__name__)

env_copy = os.environ.copy()

env_copy["PATH"] = "/usr/bin:" + env_copy["PATH"]


def natural_key(s):
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", s.name)
    ]


def broadcast_status_update(submission_id, new_message, runtime=-1):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"submission_{submission_id}",
        {
            "type": "submission_status",
            "submission_id": submission_id,
            "message": new_message,
            "runtime": runtime,
        },
    )


def run_code_handler(tl, ml, lang, pid, sid, code):
    submission = Submission.objects.get(pk=sid)
    if lang not in ["python", "cpp", "java"]:
        return {"error": "Unacceptable code language"}

    if not pid:
        return {"error": "You didn't select an actual problem"}

    problem_base_path = Path("/home/tjctgrader/problems") / Path(str(pid))
    if not problem_base_path.exists():
        os.listdir(str(problem_base_path))
        return {"error": "Problem does not exist on coderunner filesystem"}

    checker_path = problem_base_path / "default_checker.py"
    test_dir = problem_base_path / "test"

    subdir = Path("/home/tjctgrader/submissions") / str(sid)
    subdir.mkdir(parents=True, exist_ok=True)

    extension = {"python": "py", "java": "java", "cpp": "cpp"}[lang]
    sol_filename = f"usercode.{extension}"
    sol_path = subdir / sol_filename

    try:
        sol_path.write_text(code)
    except Exception as e:
        logger.error(f"Failed to write to file: {e}")
        raise

    if lang in ["cpp", "java"]:
        broadcast_status_update(submission.id, "Compiling")
        if lang == "cpp":
            output = subprocess.run(
                [
                    "/usr/bin/g++",
                    "-std=c++17",
                    "-O2",
                    "-o",
                    str(subdir / "usercode"),
                    str(sol_path),
                ],
                env=env_copy,
                capture_output=True,
            )
            sol_path = subdir / "usercode"
            sol_filename = "usercode"
        elif lang == "java":
            output = subprocess.run(
                ["/usr/bin/javac", str(sol_path)], env=env_copy, capture_output=True
            )
            sol_path = subdir / "usercode"
            sol_filename = "usercode"

        if output.returncode != 0:
            return {
                "verdict": "Compilation Error",
                "output": output.stderr.decode("utf-8", errors="ignore"),
                "runtime": 0,
            }

    verdict_overall = "Accepted"
    insight_overall = ""
    overall_time = 0

    try:
        entries = sorted(test_dir.iterdir(), key=natural_key)
    except Exception:
        return {"error": "Test cases not found"}

    if lang == "java":
        tl *= 2
    elif lang == "python":
        tl *= 3

    for entry in entries:
        file_path = entry
        test_name = file_path.name
        broadcast_status_update(submission.id, f"Running on test {test_name}")

        try:
            output_text, insight, time_used = run_code(
                subdir,
                file_path,
                lang,
                sol_path,
                sol_filename,
                tl,
                ml,
                False,
                None,
                None,
            )
        except Exception as e:
            verdict_overall = "Grader Error"
            insight_overall = f"Grader Error: {e}"
            break

        overall_time = max(overall_time, time_used)

        if output_text == "Runtime Error":
            verdict_overall = "Runtime Error"
            insight_overall = insight
            break
        if output_text == "Time Limit Exceeded":
            verdict_overall = f"Time Limit Exceeded on test {test_name}"
            insight_overall = insight
            break

        # run checker
        try:
            check_out, _, _ = run_code(
                subdir,
                None,
                "python",
                checker_path,
                "default_checker.py",
                20000,
                1024,
                True,
                test_name,
                pid,
            )
        except Exception as e:
            verdict_overall = f"Checker Error: {e}"
            break

        if check_out.strip().lower() not in ("ac", "accepted"):
            verdict_overall = f"Wrong Answer on test {test_name}"
            break

    # # cleanup
    # try:
    #     shutil.rmtree(subdir)
    # except Exception:
    #     pass

    broadcast_status_update(submission.id, verdict_overall, runtime=overall_time)

    return {
        "verdict": verdict_overall,
        "output": insight_overall,
        "runtime": overall_time,
    }
