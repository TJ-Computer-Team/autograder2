import subprocess
import os
import re
import shutil
from pathlib import Path
from .runner import run_code
from .interactive_checker import run_interactive_problem
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


JAVA_PACKAGE_RE = re.compile(r"^\s*package\s+[\w.]+\s*;", re.MULTILINE)
JAVA_NOISE_RE = re.compile(
    r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.DOTALL
)
JAVA_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+(?:(?:final|abstract)\s+)*class\s+(\w+)")
JAVA_CLASS_RE = re.compile(r"\bclass\s+(\w+)")
JAVA_MAIN_RE = re.compile(r"\bstatic\s+void\s+main\s*\(")


def prepare_java_source(code):
    """Return (main class name, code) so any class name works and packages are ignored.

    javac needs the file named after the public class, and `java` needs the
    class to sit in the default package, so we detect the name and strip any
    package declaration rather than forcing everyone to write `usercode`.
    """
    code = JAVA_PACKAGE_RE.sub("", code, count=1)
    # Ignore "class" appearing in comments or string literals.
    stripped = JAVA_NOISE_RE.sub(" ", code)

    match = JAVA_PUBLIC_CLASS_RE.search(stripped)
    if match:
        return match.group(1), code

    # No public class: use the last class declared before main.
    main = JAVA_MAIN_RE.search(stripped)
    classes = JAVA_CLASS_RE.findall(stripped[: main.start()] if main else stripped)
    if classes:
        return classes[-1], code

    return "usercode", code


def write_source(subdir, lang, code):
    """Write the submission into subdir; returns (source path, base name)."""
    if lang == "java":
        name, code = prepare_java_source(code)
        sol_path = subdir / f"{name}.java"
    else:
        extension = {"python": "py", "cpp": "cpp"}[lang]
        name = "usercode"
        sol_path = subdir / f"usercode.{extension}"

    try:
        sol_path.write_text(code)
    except Exception as e:
        logger.error(f"Failed to write to file: {e}")
        raise

    return sol_path, name


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

    has_interactor = (
        (problem_base_path / "interactor.py").exists() or
        (problem_base_path / "interactor").exists()
    )
    
    if has_interactor:
        return run_interactive_handler(tl, ml, lang, pid, sid, code)

    checker_path = problem_base_path / "default_checker.py"
    test_dir = problem_base_path / "test"

    subdir = Path("/home/tjctgrader/submissions") / str(sid)
    subdir.mkdir(parents=True, exist_ok=True)

    sol_path, main_name = write_source(subdir, lang, code)
    sol_filename = sol_path.name

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
            sol_path = subdir / main_name
            sol_filename = main_name

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
        test_name = file_path.stem
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
        if output_text == "Memory Limit Exceeded":
            verdict_overall = f"Memory Limit Exceeded on test {test_name}"
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
                file_path.name,
                pid,
            )
            insight_overall = check_out
        except Exception as e:
            verdict_overall = f"Checker Error: {e}"
            break

        if check_out.strip().lower() not in ("ac", "accepted"):
            verdict_overall = f"Wrong Answer on test {test_name}"
            break

    # cleanup
    try:
        shutil.rmtree(subdir)
    except Exception:
        pass

    broadcast_status_update(submission.id, verdict_overall, runtime=overall_time)

    return {
        "verdict": verdict_overall,
        "output": insight_overall,
        "runtime": overall_time,
    }


def run_interactive_handler(tl, ml, lang, pid, sid, code):
    submission = Submission.objects.get(pk=sid)
    if lang not in ["python", "cpp", "java"]:
        return {"error": "Unacceptable code language"}

    if not pid:
        return {"error": "You didn't select an actual problem"}

    problem_base_path = Path("/home/tjctgrader/problems") / Path(str(pid))
    if not problem_base_path.exists():
        return {"error": "Problem does not exist on coderunner filesystem"}

    test_dir = problem_base_path / "test"
    
    subdir = Path("/home/tjctgrader/submissions") / str(sid)
    subdir.mkdir(parents=True, exist_ok=True)

    sol_path, main_name = write_source(subdir, lang, code)
    sol_filename = sol_path.name

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
            sol_path = subdir / main_name
            sol_filename = main_name

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
        test_name = entry.stem
        broadcast_status_update(submission.id, f"Running on test {test_name}")

        try:
            verdict, message, time_used = run_interactive_problem(
                user_executable=str(sol_path),
                user_lang=lang,
                problem_dir=str(problem_base_path),
                test_input_path=str(entry),
                time_limit_ms=tl,
                memory_limit_mb=ml,
            )
        except Exception as e:
            verdict_overall = "Grader Error"
            insight_overall = f"Grader Error: {e}"
            break

        overall_time = max(overall_time, time_used)

        if verdict != "Accepted":
            verdict_overall = f"{verdict} on test {test_name}"
            insight_overall = message
            break

    try:
        shutil.rmtree(subdir)
    except Exception:
        pass

    broadcast_status_update(submission.id, verdict_overall, runtime=overall_time)

    return {
        "verdict": verdict_overall,
        "output": insight_overall,
        "runtime": overall_time,
    }
