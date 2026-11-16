"""Extract source locations and automation results from UE text logs."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import BinaryIO, TypedDict

MAX_LOG_BYTES = 1_048_576
MAX_DIAGNOSTICS = 30
MAX_MESSAGE = 500
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MSVC = re.compile(
    r"^\s*(?P<file>.+?)\((?P<line>\d+)(?:,(?P<column>\d+))?\)\s*:\s*"
    r"(?P<severity>fatal error|error|warning)\s*(?P<code>[A-Z]+\d+)?\s*:\s*(?P<message>.+)$"
)
CLANG = re.compile(
    r"^\s*(?P<file>.+?):(?P<line>\d+):(?:(?P<column>\d+):)?\s*"
    r"(?P<severity>fatal error|error|warning):\s*(?P<message>.+)$"
)
UE = re.compile(
    r"^(?:\[[^\]\r\n]+\]\s*)*(?P<category>Log\w+):\s*"
    r"(?P<severity>Error|Warning):\s*(?P<message>.+)$"
)
AUTOMATION = re.compile(
    r"LogAutomationController:.*?Test Completed\.\s*Result=\{([^{}]+)\}"
    r"\s*Name=\{[^{}]*\}\s*Path=\{([^{}]+)\}"
)


class Diagnostic(TypedDict):
    severity: str
    message: str
    file: str | None
    line: int | None
    column: int | None
    code: str | None
    category: str | None


def read_tail(stream: BinaryIO) -> tuple[str, bool]:
    size = stream.seek(0, os.SEEK_END)
    offset = max(0, size - MAX_LOG_BYTES)
    stream.seek(offset)
    data = stream.read(MAX_LOG_BYTES)
    if offset:
        # The first line in the window may start mid-message.
        _, _, data = data.partition(b"\n")
    return data.decode("utf-8-sig", errors="replace"), bool(offset)


def parse(text: str, limit: int = MAX_DIAGNOSTICS) -> list[Diagnostic]:
    results: list[Diagnostic] = []
    seen = set()
    for raw in text.splitlines():
        line = ANSI.sub("", raw[:8192])
        match = MSVC.match(line) or CLANG.match(line) or UE.match(line)
        if not match:
            continue
        fields = match.groupdict()
        location = fields.get("file")
        row = fields.get("line")
        col = fields.get("column")
        diagnostic: Diagnostic = {
            "severity": match["severity"].lower(),
            "message": match["message"][:MAX_MESSAGE],
            "file": location.strip()[:MAX_MESSAGE] if location else None,
            "line": int(row) if row and len(row) <= 9 else None,
            "column": int(col) if col and len(col) <= 9 else None,
            "code": fields.get("code"),
            "category": fields.get("category"),
        }
        key = tuple(diagnostic.values())
        if key not in seen:
            seen.add(key)
            results.append(diagnostic)
    # Put errors ahead of warnings, preserving the order within each severity.
    return sorted(results, key=lambda item: item["severity"] == "warning")[:limit]


def summarize(path: Path, limit: int = MAX_DIAGNOSTICS) -> dict:
    with path.open("rb") as stream:
        text, partial = read_tail(stream)
    return {
        "diagnostics": parse(text, limit),
        "automation_results": [
            {"name": name, "state": state} for name, state in automation_results(text).items()
        ][:30],
        "truncated": partial,
        "tail": "\n".join(text.splitlines()[-12:])[-3200:],
    }


def automation_results(text: str) -> dict[str, str]:
    return {match[2][:250]: match[1][:60] for match in AUTOMATION.finditer(text)}
