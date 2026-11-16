import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ue_toolkit.hooks import guard_shell, header_hint, pre

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "command",
    [
        "git status && git -C Game reset --hard HEAD",
        "git clean -xdf",
        "cd Game\n/bin/rm -fr Content",
        "env VAR=value /bin/rm Content/Map.umap",
        "rm -- Config/../Content/MyActor.uasset",
    ],
)
def test_guard_rejects_common_destructive_commands(command):
    assert guard_shell(command)


@pytest.mark.parametrize(
    "command",
    ["git clean -ndf", "git diff -- Source", "echo 'rm -rf Content'", "rm Saved/Logs/old.log"],
)
def test_guard_allows_routine_commands(command):
    assert guard_shell(command) is None


def test_hook_config_and_stdio_payload_contract(tmp_path):
    source = tmp_path / "Source"
    source.mkdir()
    (source / "Player.h").write_text(
        '#include "Player.generated.h"\n#include "CoreMinimal.h"\n', encoding="utf-8"
    )
    hooks = json.loads((REPO / ".claude/settings.json").read_text())["hooks"]

    def invoke(event, tool, **inputs):
        command = hooks[event][0]["hooks"][0]["command"].split()
        assert command[0] == "python"
        return subprocess.run(
            [sys.executable, *command[1:]],
            input=json.dumps(
                {
                    "hook_event_name": event,
                    "cwd": str(tmp_path),
                    "tool_name": tool,
                    "tool_input": inputs,
                }
            ),
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    denied = invoke("PreToolUse", "Write", file_path="Content/MyActor.uasset")
    assert denied.returncode == 2 and "binary assets" in denied.stderr
    assert invoke("PreToolUse", "Edit", file_path="Source/Player.h").returncode == 0
    checked = invoke("PostToolUse", "Edit", file_path="Source/Player.h")
    assert checked.returncode == 0
    output = json.loads(checked.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "PostToolUse"
    assert 'move "Player.generated.h"' in output["additionalContext"]


def test_header_hint_ignores_commented_out_includes_and_macros():
    assert header_hint('// GENERATED_BODY()\n/* #include "Other.generated.h" */', "Player") is None
    assert header_hint("struct FPlayer {\n GENERATED_BODY()\n};", "Player")
    assert (
        header_hint(
            '#include "CoreMinimal.h"\n#include "Player.generated.h" // always last\n'
            '// #include "NotActuallyIncluded.h"\n',
            "Player",
        )
        is None
    )


def test_guard_resolves_alias_into_binary_asset(tmp_path):
    (tmp_path / "Example.uasset").touch()
    try:
        (tmp_path / "Alias.txt").symlink_to("Example.uasset")
    except OSError:
        pytest.skip("symlinks unavailable")
    assert pre(
        {"cwd": str(tmp_path), "tool_name": "Write", "tool_input": {"file_path": "Alias.txt"}},
        tmp_path.resolve(),
    )
