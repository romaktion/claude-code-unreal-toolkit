---
name: ue5-build
description: Build the current Unreal Engine 5 project for the native host and triage UBT diagnostics.
argument-hint: "[target] [Development|DebugGame]"
disable-model-invocation: true
---

Build request: $ARGUMENTS

1. Call `mcp__ue5-toolkit__project_info`. Confirm the descriptor, native platform, and intended target. For an unspecified target, use the server's editor target default. Ask which target to use if the default is ambiguous.
2. If execution is disabled or no engine is configured, report the setup issue from the server and stop. If the editor is open and Live Coding owns the build, ask the user to close it or use their existing Live Coding flow.
3. Call `mcp__ue5-toolkit__build_project` with the requested target and configuration. Treat timeout, busy, and missing tooling as distinct from a compilation failure.
4. Report the target, outcome, and log path. For failures, prioritize the first actionable UHT, compiler, or linker diagnostic and cite the file and line when available.
5. Suggest the smallest next change. Only modify project code or run another build if the user's request includes that work.
