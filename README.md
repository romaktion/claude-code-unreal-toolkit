# Claude Code Unreal Toolkit

[![Toolkit CI](https://github.com/romaktion/claude-code-unreal-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/romaktion/claude-code-unreal-toolkit/actions/workflows/ci.yml)

A local MCP server, two project hooks, and three Claude Code skills for UE5 C++ development. Build a discovered target, run a named Unreal Automation suite, and return diagnostics with source locations and paths to the full logs.

## Try it without Unreal Engine

Requires Python 3.11 or newer. The demo starts the same stdio MCP server configured for Claude Code, creates a temporary project with a sample Clang diagnostic, and calls `project_info` and `analyze_log`.

```sh
git clone https://github.com/romaktion/claude-code-unreal-toolkit.git
cd claude-code-unreal-toolkit
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python examples/demo.py
python -m pytest -q
```

Use any supported Python to create the environment. On Windows PowerShell, use `py -3.12 -m venv .venv` and `& .\.venv\Scripts\Activate.ps1`.

```text
Project: Demo.uproject | targets: DemoEditor
error: Source/Demo/Player.cpp:27: use of undeclared identifier 'AmmoCount'
```

## Connect Claude Code to a UE5 project

1. Install the toolkit in a virtual environment as above. From the UE project directory, activate that same environment so both MCP and the hooks resolve `python`.
2. Copy [`.mcp.json`](.mcp.json) and the [`.claude`](.claude/) settings and skills into the UE project root. If those files already exist, merge the `ue5-toolkit` server and hook entries into the existing JSON and add the skill folders.
3. Launch `claude` in that root and approve the project MCP server when prompted. Check `/mcp` or `claude mcp list` for its status.
4. Start with “Call `project_info`” or `/ue5-debug Saved/Logs/MyGame.log`. Engine execution is off by default. To opt in, set the variables below **before** starting Claude Code.

```sh
export UE_ENGINE_ROOT="/path/to/UE_5.x" # Directory containing Engine/
export UE_TOOLKIT_ENABLE_RUNS=1
claude
```

In PowerShell, use `$env:UE_ENGINE_ROOT = "C:\path\to\UE_5.x"` and `$env:UE_TOOLKIT_ENABLE_RUNS = "1"`. The workspace should have one top-level `.uproject`. Set `UE_PROJECT_FILE` to a workspace-relative path when there are multiple descriptors or the project is nested.

| MCP tool | Example arguments | Result |
| --- | --- | --- |
| `project_info` | `{}` | Descriptor, discovered `*.Target.cs` files, host and execution status |
| `build_project` | `{"target":"MyGameEditor","configuration":"Development"}` | Native UBT result, diagnostics, and process log |
| `run_automation_tests` | `{"test_filter":"MyGame.Inventory"}` | Outcome based on UE's JSON report, with counts and test names |
| `analyze_log` | `{"relative_path":"Saved/Logs/MyGame.log"}` | Deduplicated MSVC, Clang, and UE diagnostics from the last 1 MiB |

Use `/ue5-build [target] [configuration]` to build, `/ue5-debug [log path]` to triage, and `/ue5-code-review [paths or revision range]` to review UE C++. To run automation, ask Claude Code to call `run_automation_tests` with one dotted test name, suite prefix, or `Group:Name`. Build first so the editor loads the current test code.

The [pre-tool hook](src/ue_toolkit/hooks.py) blocks direct edits to binary assets and generated paths, plus common destructive Bash commands such as `rm -rf` and `git reset --hard`. The post-tool hook gives an advisory when a reflected C++ header appears to be missing its own `.generated.h` include or places another include after it.

## Run the included UE5 C++ example

With UE5 and its native C++ toolchain installed, run this from the toolkit checkout:

```sh
UE_ENGINE_ROOT="/path/to/UE_5.x" python examples/demo.py --engine
```

The script opens a real MCP session, builds [ToolkitSmokeEditor](examples/engine_smoke/), runs `ToolkitSmoke.Math.ClampAmmo`, checks the exported report, and verifies that an unmatched filter never reports success. The sample contains just an editor target, a runtime module, and one automation test. It uses the engine's built-in Entry map.

Verified on **macOS arm64 with UE 5.8.4**: UBT returned success; the exported report showed one test passed, zero failed. The engine-free tests cover stdio tool discovery, diagnostics, report interpretation, timeout handling, path restrictions and the hook input/output format. CI exercises these tests without installing Unreal on Linux, macOS and Windows. Real engine execution on Windows and Linux has not been verified.

## Boundaries

- Engine operations run locally under your account. Use trusted engine and project code; build rules and project modules execute code. Hooks catch a subset of common mistakes and do not sandbox shell commands.
- Builds target the native host. The automation launcher uses NullRHI and is meant for tests that can run without rendering. Each server allows one engine job at a time.
- Full process logs and automation reports stay under `Saved/ClaudeUnrealToolkit/` in the UE project. Review logs before sharing them. A missing or incomplete automation report cannot turn a zero editor exit code into a pass.
- Diagnostic output is bounded; check the full log if the root cause is earlier. Generated include hints do not parse preprocessor branches or replace UHT. Windows build paths with CMD metacharacters such as `%` or `!` are rejected.

References: [Claude Code hooks](https://code.claude.com/docs/en/hooks), [MCP configuration](https://code.claude.com/docs/en/mcp), [Claude Code skills](https://code.claude.com/docs/en/skills), [MCP Python SDK 1.x](https://py.sdk.modelcontextprotocol.io/v1/), and [Unreal Automation command line](https://dev.epicgames.com/documentation/unreal-engine/run-automation-tests-in-unreal-engine).

Developed with AI coding assistance. Licensed under [MIT](LICENSE).
