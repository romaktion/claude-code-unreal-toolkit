"""Exercise the published .mcp.json entry over stdio, with or without UE installed."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]


async def demo(workspace: Path, *, real_engine: bool) -> None:
    config = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["ue5-toolkit"]
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(workspace),
        "UE_PROJECT_FILE": "examples/engine_smoke/ToolkitSmoke.uproject" if real_engine else "",
        "UE_TOOLKIT_ENABLE_RUNS": "1" if real_engine else "0",
    }
    params = StdioServerParameters(
        command=sys.executable, args=config["args"], env=env, cwd=str(workspace)
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            async def call(tool: str, **arguments: object) -> dict:
                result = await session.call_tool(tool, arguments)
                if result.isError or result.structuredContent is None:
                    raise RuntimeError(f"{tool}: {result.content}")
                return result.structuredContent

            info = await call("project_info")
            print(f"Project: {info['project']} | targets: {', '.join(info['targets'])}", flush=True)
            if real_engine:
                built = await call("build_project")
                print(f"UBT: {built['target']} -> {built['status']}", flush=True)
                if built["status"] != "passed":
                    raise RuntimeError(f"{built['log_path']}\n{built['tail']}")
                tested = await call("run_automation_tests", test_filter="ToolkitSmoke")
                print(
                    f"Automation: {tested['status']} | {tested['automation'].get('tests', [])}",
                    flush=True,
                )
                print(f"Report: examples/engine_smoke/{tested['report_path']}", flush=True)
                if tested["status"] != "passed":
                    raise RuntimeError(f"{tested['log_path']}\n{tested['tail']}")

                empty = await call(
                    "run_automation_tests",
                    test_filter="ToolkitSmoke.NoSuchTest",
                    timeout_seconds=120,
                )
                if empty["status"] not in {"failed", "inconclusive"}:
                    raise RuntimeError(f"Unexpected result for an unmatched filter: {empty}")
                print(f"Unmatched test filter: {empty['status']}", flush=True)
            else:
                tool = await call("analyze_log", relative_path="Saved/Logs/demo.log")
                diag = tool["diagnostics"][0]
                print(f"{diag['severity']}: {diag['file']}:{diag['line']}: {diag['message']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", action="store_true", help="build and test with UE_ENGINE_ROOT")
    args = parser.parse_args()
    if args.engine:
        asyncio.run(demo(REPO, real_engine=True))
        return
    with TemporaryDirectory(prefix="ue-toolkit-demo-") as directory:
        workspace = Path(directory)
        (workspace / "Demo.uproject").write_text("{}\n", encoding="utf-8")
        (workspace / "Source").mkdir()
        (workspace / "Source/DemoEditor.Target.cs").touch()
        logs = workspace / "Saved/Logs"
        logs.mkdir(parents=True)
        (logs / "demo.log").write_text(
            "Source/Demo/Player.cpp:27:9: error: use of undeclared identifier 'AmmoCount'\n",
            encoding="utf-8",
        )
        asyncio.run(demo(workspace, real_engine=False))


if __name__ == "__main__":
    main()
