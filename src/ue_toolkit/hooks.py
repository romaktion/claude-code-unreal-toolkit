"""Claude Code pre-tool guard and post-edit advice for Unreal C++ headers."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

from .project import workspace_root

ASSETS = {".uasset", ".umap", ".ubulk", ".uexp"}
GENERATED_DIRS = {".git", "binaries", "intermediate", "deriveddatacache"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
SEPARATORS = set(";&|()\n")
COMMAND_WRAPPERS = {"command", "env", "sudo", "exec", "builtin", "time"}
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
COMMENT_OR_LITERAL = re.compile(
    r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', re.DOTALL
)
INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^">\n]+)[">]', re.MULTILINE)
GENERATED_BODY = re.compile(
    r"^\s*GENERATED_(?:(?:UCLASS|USTRUCT|IINTERFACE)_)?BODY\s*\(", re.MULTILINE
)
MAX_HEADER = 512 * 1024


def protected(path: Path) -> bool:
    return path.suffix.lower() in ASSETS or any(
        part.lower() in GENERATED_DIRS for part in path.parts
    )


def command_segments(command: str) -> list[list[str]]:
    # Conservative tokenization of simple shell commands, not a Bash interpreter.
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    try:
        for token in lexer:
            if token and set(token) <= SEPARATORS:
                segments.append([])
            else:
                segments[-1].append(token)
    except ValueError:
        return []
    return segments


def guard_shell(command: str) -> str | None:
    for segment in command_segments(command):
        words = iter(segment)
        executable = next(words, "")
        while ASSIGNMENT.match(executable) or Path(executable).name in COMMAND_WRAPPERS:
            executable = next(words, "")
        name = Path(executable).name
        args = list(words)
        if name == "rm":
            options = args[: args.index("--")] if "--" in args else args
            recursive = any(
                arg == "--recursive"
                or (
                    arg.startswith("-")
                    and not arg.startswith("--")
                    and any(c in arg[1:] for c in "rR")
                )
                for arg in options
            )
            if recursive or any(protected(Path(arg)) for arg in args):
                return "Recursive removal and deletion of Unreal assets or generated paths are guarded."
        if name == "git":
            tail = iter(args)
            action = next(tail, "")
            while action.startswith("-"):
                if action in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}:
                    next(tail, None)
                action = next(tail, "")
            rest = list(tail)
            if "--" in rest:
                rest = rest[: rest.index("--")]
            if action == "reset" and "--hard" in rest:
                return "git reset --hard can discard work. Use a targeted change."
            if (
                action == "clean"
                and not any(
                    arg in {"--dry-run", "--interactive"}
                    or (
                        arg.startswith("-")
                        and not arg.startswith("--")
                        and any(c in arg[1:] for c in "ni")
                    )
                    for arg in rest
                )
                and any(
                    arg == "--force"
                    or (arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:])
                    for arg in rest
                )
            ):
                return "Forced git clean can delete untracked files. Preview with git clean -n."
    return None


def pre(payload: dict, root: Path) -> str | None:
    tool = payload.get("tool_name")
    inputs = payload.get("tool_input") or {}
    if tool == "Bash" and isinstance(inputs.get("command"), str):
        return guard_shell(inputs["command"])
    if tool in EDIT_TOOLS and isinstance(inputs.get("file_path"), str):
        try:
            candidate = Path(payload["cwd"]) / inputs["file_path"]
            paths = (Path(os.path.abspath(candidate)), candidate.resolve())
        except (KeyError, OSError, RuntimeError, ValueError):
            return None
        if any(path.is_relative_to(root) and protected(path.relative_to(root)) for path in paths):
            return (
                "Edit binary assets in Unreal Editor. Regenerate build files with Unreal tooling."
            )
    return None


def header_hint(text: str, stem: str) -> str | None:
    def blank_comments(match: re.Match) -> str:
        value = match[0]
        return re.sub(r"[^\n]", " ", value) if value.startswith(("//", "/*")) else value

    source = COMMENT_OR_LITERAL.sub(blank_comments, text)
    includes = INCLUDE.findall(source)
    generated = [name for name in includes if name.endswith(".generated.h")]
    expected = f"{stem}.generated.h"
    if not generated:
        if GENERATED_BODY.search(source):
            return f'UHT check: add #include "{expected}" after the other includes.'
        return None
    if generated != [expected]:
        return f'UHT check: expected exactly one #include "{expected}" for this header.'
    if includes[-1] != expected:
        return f'UHT check: move "{expected}" after the other includes.'
    return None


def post(payload: dict, root: Path) -> str | None:
    if payload.get("tool_name") not in EDIT_TOOLS:
        return None
    inputs = payload.get("tool_input") or {}
    file_path = inputs.get("file_path")
    if not isinstance(file_path, str):
        return None
    try:
        resolved = (Path(payload["cwd"]) / file_path).resolve().relative_to(root)
        if (
            resolved.suffix.lower() not in {".h", ".hpp"}
            or "source" not in (part.lower() for part in resolved.parts[:-1])
            or protected(resolved)
        ):
            return None
        path = root / resolved
        if not path.is_file():
            return None
        with path.open("rb") as stream:
            raw = stream.read(MAX_HEADER + 1)
        if len(raw) > MAX_HEADER:
            return None
    except (KeyError, OSError, RuntimeError, ValueError):
        return None
    return header_hint(raw.decode("utf-8-sig", errors="replace"), resolved.stem)


def main() -> int:
    phase = sys.argv[1:]  # "pre" or "post"
    if phase not in (["pre"], ["post"]):
        print("Usage: python -m ue_toolkit.hooks {pre|post}", file=sys.stderr)
        return 1
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
            raise ValueError("expected a Claude Code tool payload")
    except (ValueError, UnicodeError):
        print("UE toolkit hook could not read the tool event.", file=sys.stderr)
        return 1
    root = workspace_root()
    if phase == ["pre"]:
        if reason := pre(payload, root):
            print(reason, file=sys.stderr)
            return 2
    elif hint := post(payload, root):
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": hint}}
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
