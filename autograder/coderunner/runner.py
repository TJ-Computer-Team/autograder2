import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def run_code(
    subdir: Path,
    input_path: Optional[Path],
    lang: str,
    source_path: Path,
    source_filename: str,
    tl: int,
    ml: int,  # in MB
    checker: bool,
    checker_testid: Optional[str],
    checker_problemid: Optional[str],
) -> Tuple[str, str, int]:
    if not settings.DEBUG:
        cmd = ["/usr/bin/sudo", "/usr/bin/nsjail"]
    else:
        cmd = ["/usr/bin/nsjail"]

    cmd += [
        "--quiet",
        "--time_limit",
        str(tl // 1000),
        "--cgroup_mem_max",
        str(ml * 1024 * 1024),
        "--cgroup_pids_max",
        "64",
    ]

    cfg = (
        "/home/tjctgrader/autograder/autograder/coderunner/"
        + {
            ("cpp", False): "nsjail_configs/executable.cfg",
            ("cpp", True): "nsjail_configs/executablechecker.cfg",
            ("python", False): "nsjail_configs/python.cfg",
            ("python", True): "nsjail_configs/pythonchecker.cfg",
            ("java", False): "nsjail_configs/java.cfg",
            ("java", True): "nsjail_configs/java.cfg",
        }[(lang, checker)]
    )

    cmd += ["--config", cfg]

    # mount code into jail
    if lang == "python":
        cmd += ["-R", f"{source_path}:{'/subcode/' + source_filename}"]
    elif lang == "cpp":
        cmd += ["-R", f"{subdir / 'usercode'}:/subcode/usercode"]
    elif lang == "java":
        class_dir = source_path.parent
        cmd += ["-R", f"{class_dir}:/subcode"]
    else:
        raise RuntimeError("Unsupported language")

    if checker:
        cmd += [
            "-R",
            f"/home/tjctgrader/problems/{checker_problemid}/sol/{checker_testid}:/subcode/sol.txt",
            "-R",
            f"/home/tjctgrader/problems/{checker_problemid}/test/{checker_testid}:/subcode/test.txt",
            "-R",
            f"{subdir}/output.txt:/subcode/output.txt",
        ]

    # command to run inside jail
    if lang == "cpp":
        cmd += ["/subcode/usercode"]
    elif lang == "python" and not checker:
        cmd += ["/usr/bin/python3", f"/subcode/{source_filename}"]
    elif lang == "python" and checker:
        cmd += ["/usr/bin/python3", "/subcode/default_checker.py"]
    elif lang == "java":
        class_name = source_filename.split(".")[0] or "usercode"
        cmd += ["/usr/bin/java", class_name]
    else:
        raise RuntimeError("Unsupported language")

    logger.error(f"Executing nsjail command: {' '.join(cmd)}")

    out_path = subdir / ("checker_output.txt" if checker else "output.txt")

    stdin_file = open(input_path, "rb") if input_path else None
    stdout_file = open(out_path, "wb")

    start = time.time()
    proc = subprocess.Popen(
        cmd,
        stdin=stdin_file,
        stdout=stdout_file,
        stderr=subprocess.PIPE,
    )
    _, stderr = proc.communicate()
    elapsed = int((time.time() - start) * 1000)

    if stdin_file:
        stdin_file.close()
    stdout_file.close()

    if elapsed >= tl:
        return "Time Limit Exceeded", "", tl

    if proc.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="ignore")
        logger.error(stderr)
        logger.error(proc.returncode)
        return "Runtime Error", stderr_text, elapsed

    try:
        output_text = out_path.read_text()
    except Exception:
        output_text = ""

    return output_text, "", elapsed
