"""Launch Unreal tools with fixed argument shapes and retain a transcript for each run."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from .logs import summarize
from .project import RUN_DIR, Engine, Project

FILTER = re.compile(r"(?:Group:)?[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*")
REPORT_KEYS = ("succeeded", "succeededWithWarnings", "failed", "notRun", "inProcess")
MAX_REPORT_BYTES = 16 * 1024 * 1024


def make_run_dir(project: Project) -> Path:
    path = project.saved_directory(RUN_DIR) / uuid4().hex
    path.mkdir(parents=True)
    return path


def build_args(
    engine: Engine, project: Project, target: str, configuration: str, run_dir: Path
) -> list[str]:
    directory = engine.root / "Engine/Build/BatchFiles"
    launcher = directory / ("Build.bat" if engine.host == "Win64" else f"{engine.host}/Build.sh")
    if not launcher.is_file():
        raise ValueError(f"Could not find the {engine.host} Unreal build launcher")
    args = [
        str(launcher),
        target,
        engine.host,
        configuration,
        f"-Project={project.descriptor}",
        f"-Log={run_dir / 'ubt.log'}",
        "-Unattended",
        "-NoHotReloadFromIDE",
    ]
    # Epic's batch script forwards args through CALL with delayed expansion enabled.
    if engine.host == "Win64" and any(re.search(r'[%!"^&|<>\r\n]', arg) for arg in args):
        raise ValueError("Windows build paths may not contain %, !, quotes or cmd metacharacters")
    return args


def automation_args(engine: Engine, project: Project, test_filter: str, run_dir: Path) -> list[str]:
    if len(test_filter) > 160 or not FILTER.fullmatch(test_filter):
        raise ValueError("Use one dotted test name, suite prefix, or Group:Name")
    paths = {
        "Mac": "Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor",
        "Linux": "Linux/UnrealEditor",
        "Win64": "Win64/UnrealEditor-Cmd.exe",
    }
    editor = engine.root / "Engine/Binaries" / paths[engine.host]
    if not editor.is_file():
        raise ValueError(f"Could not find the {engine.host} Unreal Editor executable")
    return [
        str(editor),
        str(project.descriptor),
        f"-ExecCmds=Automation RunTests {test_filter};Quit",
        f"-ReportExportPath={run_dir / 'report'}",
        f"-ABSLOG={run_dir / 'editor.log'}",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-nullrhi",
        "-nosound",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def stop_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            taskkill = Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"
            subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run(argv: list[str], project: Project, run_dir: Path, timeout: int) -> dict:
    command: str | list[str] = argv
    if os.name == "nt" and argv[0].lower().endswith(".bat"):
        cmd = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
        quoted_args = " ".join(f'"{arg}"' for arg in argv)
        command = f'{subprocess.list2cmdline([str(cmd)])} /d /v:off /s /c "{quoted_args}"'

    log = run_dir / "process.log"
    started = time.monotonic()
    timed_out = False
    with log.open("xb") as output:
        with subprocess.Popen(
            command,
            cwd=project.root,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
        ) as process:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_tree(process)

    return {
        "status": "timeout" if timed_out else ("passed" if process.returncode == 0 else "failed"),
        "exit_code": process.returncode,
        "duration_seconds": round(time.monotonic() - started, 2),
        "log_path": log.relative_to(project.root).as_posix(),
        **summarize(log),
    }


def read_automation_report(path: Path) -> dict:
    """Fail closed when the editor produced no usable report, even if it exited 0."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("report exceeds the 16 MiB parsing limit")
        report = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(report, dict):
            raise ValueError("report must be a JSON object")
        counts = {key: report.get(key) for key in REPORT_KEYS}
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("invalid test counts")
        tests = report.get("tests")
        if not isinstance(tests, list) or (sum(counts.values()) and not tests):
            raise ValueError("missing tests list")
    except (OSError, ValueError) as error:
        return {"status": "inconclusive", "reason": f"No usable automation report: {error}"}

    completed = counts["succeeded"] + counts["succeededWithWarnings"] + counts["failed"]
    if counts["failed"]:
        status, reason = "failed", "At least one automation test failed."
    elif not completed:
        status, reason = "inconclusive", "No automation tests completed. Check the test filter."
    elif counts["notRun"] or counts["inProcess"]:
        status, reason = "inconclusive", "The automation report contains unfinished tests."
    else:
        status, reason = "passed", "All selected automation tests completed without failures."

    results = [
        {"name": item["fullTestPath"][:250], "state": item["state"][:60]}
        for item in tests
        if isinstance(item, dict)
        and isinstance(item.get("fullTestPath"), str)
        and isinstance(item.get("state"), str)
    ]
    results.sort(key=lambda item: item["state"].lower() == "success")
    return {"status": status, "reason": reason, "counts": counts, "tests": results[:30]}
