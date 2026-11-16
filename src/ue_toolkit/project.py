"""Resolve paths within one Claude Code workspace."""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path

TARGET_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
HOSTS = {"Darwin": "Mac", "Linux": "Linux", "Windows": "Win64"}
RUN_DIR = Path("Saved/ClaudeUnrealToolkit")
LOG_DIR = Path("Saved/Logs")


def workspace_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()


def inside(root: Path, path: Path) -> Path:
    try:
        result = (root / path).resolve()
    except RuntimeError as error:
        raise ValueError("Could not resolve the workspace path") from error
    if not result.is_relative_to(root):
        raise ValueError("Path escapes the workspace")
    return result


@dataclass(frozen=True)
class Project:
    root: Path
    descriptor: Path

    @classmethod
    def load(cls) -> Project:
        workspace = workspace_root()
        override = os.environ.get("UE_PROJECT_FILE")
        if override:
            path = Path(override)
            if path.is_absolute():
                raise ValueError("UE_PROJECT_FILE must be relative to the Claude workspace")
            descriptor = inside(workspace, path)
        else:
            candidates = sorted(p for p in workspace.glob("*.uproject") if p.is_file())
            if len(candidates) != 1:
                raise ValueError(
                    "Expected one .uproject at the workspace root. Set UE_PROJECT_FILE "
                    "to a specific workspace-relative descriptor."
                )
            descriptor = inside(workspace, candidates[0])
        if not descriptor.is_file() or descriptor.suffix.lower() != ".uproject":
            raise ValueError("UE_PROJECT_FILE must point to an existing .uproject")
        return cls(descriptor.parent, descriptor)

    @property
    def targets(self) -> list[str]:
        names: set[str] = set()
        for path in (self.root / "Source").rglob("*.Target.cs"):
            name = path.name.removesuffix(".Target.cs")
            if path.is_file() and TARGET_NAME.fullmatch(name):
                try:
                    inside(self.root, path)
                except ValueError:
                    continue
                names.add(name)
        return sorted(names)

    def editor_target(self, requested: str | None) -> str:
        targets = self.targets
        if requested is not None:
            if requested in targets:
                return requested
            raise ValueError(f"Unknown target. Available targets: {', '.join(targets) or 'none'}")
        default = f"{self.descriptor.stem}Editor"
        if default in targets:
            return default
        editors = [target for target in targets if target.endswith("Editor")]
        if len(editors) == 1:
            return editors[0]
        raise ValueError("Could not infer an editor target. Pass a target from project_info.")

    def saved_directory(self, path: Path) -> Path:
        """Do not follow a link that redirects a Saved subtree elsewhere."""
        directory = self.root / path
        if inside(self.root, directory) != directory:
            raise ValueError(f"Symlinked {path.as_posix()} is not supported")
        return directory

    def log_path(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or path.suffix.lower() != ".log" or ".." in path.parts:
            raise ValueError(
                "Use a project-relative .log path under Saved/Logs or the run directory"
            )
        log = inside(self.root, path)
        for subtree in (LOG_DIR, RUN_DIR):
            if path.is_relative_to(subtree) and log.is_relative_to(self.saved_directory(subtree)):
                if log.suffix.lower() == ".log" and log.is_file():
                    return log
        raise ValueError("Log must exist under Saved/Logs or Saved/ClaudeUnrealToolkit")


@dataclass(frozen=True)
class Engine:
    root: Path
    host: str

    @classmethod
    def load(cls) -> Engine:
        configured = os.environ.get("UE_ENGINE_ROOT")
        if not configured or not Path(configured).is_absolute():
            raise ValueError("Set UE_ENGINE_ROOT to the absolute directory containing Engine/")
        root = Path(configured).resolve()
        if not (root / "Engine/Build/Build.version").is_file():
            raise ValueError("UE_ENGINE_ROOT does not contain Engine/Build/Build.version")
        host = HOSTS.get(platform.system())
        if not host:
            raise ValueError("Supported hosts are macOS, Linux, and Windows")
        return cls(root, host)
