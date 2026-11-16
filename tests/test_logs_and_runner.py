import json
import sys

import pytest

from ue_toolkit.logs import MAX_LOG_BYTES, summarize
from ue_toolkit.project import Engine, Project
from ue_toolkit.runner import automation_args, make_run_dir, read_automation_report, run


def test_log_summary_reports_locations_and_deduplicates(tmp_path):
    path = tmp_path / "output.log"
    path.write_text(
        ("\n" * MAX_LOG_BYTES)
        + "[1.00][  0]LogTemp: Warning: no ammo\n"
        + "\x1b[31mSource/Player.cpp:27:9: error: undeclared AmmoCount\x1b[0m\n" * 2
        + r"C:\My Game\Source\Player.cpp(48,3): error C2143: syntax error"
        + "\n"
        + "LogAutomationController: Display: Test Completed. Result={Fail} "
        + "Name={ClampAmmo} Path={ToolkitSmoke.Math.ClampAmmo}\n",
        encoding="utf-8",
    )
    summary = summarize(path)
    assert summary["truncated"]
    clang, msvc, warning = summary["diagnostics"]
    assert (clang["file"], clang["line"], clang["column"]) == ("Source/Player.cpp", 27, 9)
    assert (msvc["code"], msvc["line"]) == ("C2143", 48)
    assert warning["category"] == "LogTemp"
    assert summary["automation_results"] == [
        {"name": "ToolkitSmoke.Math.ClampAmmo", "state": "Fail"}
    ]


@pytest.mark.parametrize(
    ("counters", "status"),
    [
        ({"succeeded": 1}, "passed"),
        ({"succeededWithWarnings": 1}, "passed"),
        ({"succeeded": 1, "failed": 1}, "failed"),
        ({"succeeded": 1, "notRun": 1}, "inconclusive"),
        ({}, "inconclusive"),
    ],
)
def test_automation_verdict_comes_from_report(tmp_path, counters, status):
    report = tmp_path / "index.json"
    counts = dict.fromkeys(
        ("succeeded", "succeededWithWarnings", "failed", "notRun", "inProcess"), 0
    )
    counts.update(counters)
    tests = [{"fullTestPath": "Example.Suite.Test", "state": "Success"}] if counters else []
    report.write_text(json.dumps({"tests": tests, **counts}), encoding="utf-8-sig")
    assert read_automation_report(report)["status"] == status


def test_report_absence_and_corruption_are_inconclusive(tmp_path):
    report = tmp_path / "index.json"
    assert read_automation_report(report)["status"] == "inconclusive"
    report.write_text('{"succeeded": true}', encoding="utf-8")
    assert read_automation_report(report)["status"] == "inconclusive"


def test_timeout_retains_process_output(tmp_path):
    project = Project(tmp_path, tmp_path / "Demo.uproject")
    folder = make_run_dir(project)
    result = run(
        [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(30)"],
        project,
        folder,
        timeout=1,
    )
    assert result["status"] == "timeout"
    assert "started" in result["tail"]
    assert (tmp_path / result["log_path"]).is_file()


def test_automation_rejects_console_command_injection(tmp_path):
    project = Project(tmp_path, tmp_path / "Demo.uproject")
    with pytest.raises(ValueError, match="dotted test name"):
        automation_args(Engine(tmp_path, "Mac"), project, "Suite;open /Game/Example", tmp_path)
