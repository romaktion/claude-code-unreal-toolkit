import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ue_toolkit.project import Project

REPO = Path(__file__).resolve().parents[1]


def test_mcp_stdio_discovery_diagnostics_and_execution_gate(tmp_path):
    async def exercise():
        (tmp_path / "Game.uproject").touch()
        (tmp_path / "Source").mkdir()
        (tmp_path / "Source/GameEditor.Target.cs").touch()
        logs = tmp_path / "Saved/Logs"
        logs.mkdir(parents=True)
        (logs / "Game.log").write_text("LogTemp: Error: unable to spawn actor\n", encoding="utf-8")
        config = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["ue5-toolkit"]
        params = StdioServerParameters(
            command=sys.executable,
            args=config["args"],
            cwd=str(tmp_path.parent),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path), "UE_TOOLKIT_ENABLE_RUNS": "0"},
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert {tool.name for tool in tools} == {
                    "project_info",
                    "analyze_log",
                    "build_project",
                    "run_automation_tests",
                }
                info = await session.call_tool("project_info")
                assert info.structuredContent["targets"] == ["GameEditor"]
                result = await session.call_tool(
                    "analyze_log", {"relative_path": "Saved/Logs/Game.log"}
                )
                assert (
                    result.structuredContent["diagnostics"][0]["message"] == "unable to spawn actor"
                )
                outside = await session.call_tool(
                    "analyze_log", {"relative_path": "../outside.log"}
                )
                assert outside.isError
                denied = await session.call_tool("build_project")
                assert denied.isError and "execution is disabled" in denied.content[0].text

    asyncio.run(asyncio.wait_for(exercise(), timeout=20))


def test_log_path_rejects_symlink_outside_project(tmp_path):
    project = tmp_path / "Game"
    logs = project / "Saved/Logs"
    logs.mkdir(parents=True)
    secret = tmp_path / "outside.log"
    secret.touch()
    try:
        (logs / "linked.log").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="escapes"):
        Project(project.resolve(), project / "Game.uproject").log_path("Saved/Logs/linked.log")


def test_project_discovery_requires_disambiguation(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("UE_PROJECT_FILE", raising=False)
    (tmp_path / "One.uproject").touch()
    (tmp_path / "Two.uproject").touch()
    with pytest.raises(ValueError, match="Expected one"):
        Project.load()
    monkeypatch.setenv("UE_PROJECT_FILE", "One.uproject")
    assert Project.load().descriptor.name == "One.uproject"
