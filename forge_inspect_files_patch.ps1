$ErrorActionPreference = 'Stop'

$Root = (Get-Location).Path
if ((Split-Path $Root -Leaf) -ne 'FORGE_MOTION_STUDIO_G1_FINAL') {
    throw "Run from D:\FORGE_MOTION_STUDIO_G1_FINAL. Current directory: $Root"
}

$PlannerPath = Join-Path $Root 'agents\planner.py'
$SkillDir = Join-Path $Root 'skills\inspect_files'
if (!(Test-Path -LiteralPath $PlannerPath -PathType Leaf)) { throw "Planner source not found: $PlannerPath" }
if (Test-Path -LiteralPath $SkillDir) { throw "Source skill directory already exists; refusing to overwrite: $SkillDir" }

$RunningForge = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^python(\.exe)?$' -and $_.CommandLine -and
    $_.CommandLine.Contains($Root) -and $_.CommandLine -match 'main\.py'
}
if ($RunningForge) {
    $RunningForge | Select-Object ProcessId, Name, CommandLine | Format-List | Out-String | Write-Host
    throw 'Close FORGE (python main.py) before applying this source patch.'
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$PlannerOriginal = [System.IO.File]::ReadAllText($PlannerPath, [System.Text.Encoding]::UTF8)
$Anchor = [regex]'(?m)^(\s*-\s*python_task:.*)$'
if (!$Anchor.IsMatch($PlannerOriginal)) { throw 'Planner prompt anchor "- python_task:" not found. No files changed.' }
if ($PlannerOriginal -match 'inspect_files: ONLY for read-only inspection') { throw 'Planner routing already contains inspect_files. No files changed.' }

$RoutingRules = @'
- inspect_files: ONLY for read-only inspection of files/directories. input_data MUST include action (read|list|metadata), scope (workspace|source), and path (or paths). Use scope="source" for approved project source files such as agents/planner.py and core/skill_registry.py; use scope="workspace" for runtime workspace data. NEVER use python_task to read or inspect files.
- task_type is descriptive metadata only. Never use task_type (including GENERAL) as skill_name. skill_name MUST exactly match one of the names in SKILLS currently available.
'@
$PlannerUpdated = $Anchor.Replace(
    $PlannerOriginal,
    ($RoutingRules.TrimEnd() + "`r`n" + '$1'),
    1
)

$Manifest = @'
{
  "name": "inspect_files",
  "version": "1.0.0",
  "description": "Read-only inspection of approved source files and workspace files/directories. Never executes or modifies files.",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": {"type": "string", "enum": ["read", "list", "metadata"]},
      "scope": {"type": "string", "enum": ["workspace", "source"]},
      "path": {"type": "string"},
      "paths": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["action", "scope"]
  },
  "permissions": ["workspace_read", "source_read"]
}
'@

$SkillCode = @'
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config import ROOT_DIR, WORKSPACE_DIR
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


class InspectFilesSkill(BaseSkill):
    MAX_FILE_BYTES = 1_048_576
    MAX_FILES = 10
    MAX_DIRECTORY_ENTRIES = 200

    SOURCE_DIRS = {
        "agents", "core", "execution", "skills", "contracts",
        "adapters", "production", "scripts", "storage",
    }
    SOURCE_ROOT_FILES = {
        "config.py", "main.py", "readme.md", "pyproject.toml",
        "requirements.txt",
    }
    SOURCE_EXTENSIONS = {
        ".py", ".json", ".md", ".toml", ".txt", ".yaml", ".yml",
        ".ini", ".js", ".jsx", ".ts", ".tsx", ".css", ".html",
    }
    DENIED_PARTS = {
        ".git", ".venv", "venv", "node_modules", "__pycache__",
        ".pytest_cache", ".mypy_cache", ".idea",
    }
    DENIED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"}

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="inspect_files",
            version="1.0.0",
            description=(
                "Read-only inspection of approved source files and workspace files/directories. "
                "Supports read, list and metadata; never executes or modifies files."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "list", "metadata"]},
                    "scope": {"type": "string", "enum": ["workspace", "source"]},
                    "path": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["action", "scope"],
            },
            permissions=["workspace_read", "source_read"],
        )

    @staticmethod
    def _is_sensitive_name(name: str) -> bool:
        lowered = name.lower()
        return (
            lowered == ".env"
            or lowered.startswith(".env.")
            or lowered in {"credentials", "credentials.json", "secrets.json", "id_rsa"}
            or any(marker in lowered for marker in ("secret", "credential", "password"))
            or lowered.endswith((".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"))
        )

    @classmethod
    def _validate_relative(cls, value: Any) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise SecurityViolation("Path must be a non-empty relative string.")
        raw = Path(value.strip())
        if raw.is_absolute() or any(part == ".." for part in raw.parts):
            raise SecurityViolation("Absolute paths and parent traversal are not allowed.")
        if any(part.lower() in cls.DENIED_PARTS for part in raw.parts):
            raise SecurityViolation("Access to this protected directory is denied.")
        if any(cls._is_sensitive_name(part) for part in raw.parts):
            raise SecurityViolation("Access to sensitive files is denied.")
        return raw

    @staticmethod
    def _has_symlink(base: Path, relative: Path) -> bool:
        current = base
        for part in relative.parts:
            if part == ".":
                continue
            current = current / part
            if current.is_symlink() or os.path.islink(str(current)):
                return True
        return False

    @classmethod
    def _resolve_path(cls, scope: str, value: Any) -> Path:
        raw = cls._validate_relative(value)

        if scope == "workspace":
            base = WORKSPACE_DIR.resolve()
            if cls._has_symlink(base, raw):
                raise SecurityViolation("Symbolic links are not allowed for inspection.")
            target = PermissionEngine.validate_path(raw)
            if not target.is_relative_to(base):
                raise SecurityViolation("Workspace path escape rejected.")
            return target

        if scope != "source":
            raise SecurityViolation("scope must be 'workspace' or 'source'.")
        if not raw.parts:
            raise SecurityViolation("A source path is required.")

        first = raw.parts[0].lower()
        if len(raw.parts) == 1:
            if first not in cls.SOURCE_ROOT_FILES:
                raise SecurityViolation("This root-level source file is not allowlisted.")
        elif first not in cls.SOURCE_DIRS:
            raise SecurityViolation("This source directory is not allowlisted.")

        base = ROOT_DIR.resolve()
        if cls._has_symlink(base, raw):
            raise SecurityViolation("Symbolic links are not allowed for source inspection.")
        target = (base / raw).resolve(strict=False)
        if not target.is_relative_to(base):
            raise SecurityViolation("Source path escape rejected.")
        if target.is_file() and target.suffix.lower() not in cls.SOURCE_EXTENSIONS:
            raise SecurityViolation("This source file type is not allowlisted.")
        return target

    @classmethod
    def _read_one(cls, scope: str, value: str) -> dict[str, Any]:
        target = cls._resolve_path(scope, value)
        if not target.exists() or not target.is_file():
            raise ValueError(f"Not a regular file: {value}")
        if target.stat().st_size > cls.MAX_FILE_BYTES:
            raise ValueError(f"File exceeds {cls.MAX_FILE_BYTES} byte limit: {value}")

        with target.open("rb") as handle:
            data = handle.read(cls.MAX_FILE_BYTES + 1)
        if len(data) > cls.MAX_FILE_BYTES:
            raise ValueError(f"File grew beyond size limit while reading: {value}")
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8 text: {value}") from exc

        return {"path": value, "size_bytes": len(data), "content": content}

    @classmethod
    def _metadata_one(cls, scope: str, value: str) -> dict[str, Any]:
        target = cls._resolve_path(scope, value)
        if not target.exists():
            raise ValueError(f"Path does not exist: {value}")
        stat = target.stat()
        return {
            "path": value,
            "kind": "directory" if target.is_dir() else "file",
            "size_bytes": stat.st_size if target.is_file() else None,
            "modified_time": stat.st_mtime,
        }

    @classmethod
    def _list_one(cls, scope: str, value: str) -> dict[str, Any]:
        target = cls._resolve_path(scope, value)
        if not target.exists() or not target.is_dir():
            raise ValueError(f"Not a directory: {value}")

        entries = []
        for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
            if entry.is_symlink() or os.path.islink(str(entry)):
                continue
            if cls._is_sensitive_name(entry.name) or entry.name.lower() in cls.DENIED_PARTS:
                continue
            if scope == "source" and entry.is_file() and entry.suffix.lower() not in cls.SOURCE_EXTENSIONS:
                continue
            try:
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "kind": "directory" if entry.is_dir() else "file",
                    "size_bytes": stat.st_size if entry.is_file() else None,
                })
            except OSError:
                continue
            if len(entries) >= cls.MAX_DIRECTORY_ENTRIES:
                break

        return {
            "path": value,
            "entries": entries,
            "truncated": len(entries) >= cls.MAX_DIRECTORY_ENTRIES,
        }

    def execute(self, params: dict[str, Any]) -> ExecutionResult:
        try:
            action = params.get("action")
            scope = params.get("scope", "workspace")
            if action not in {"read", "list", "metadata"}:
                return ExecutionResult(ExecutionStatus.FAILED, "action must be read, list or metadata.")
            if scope not in {"workspace", "source"}:
                return ExecutionResult(ExecutionStatus.FAILED, "scope must be workspace or source.")

            if action == "list":
                path = params.get("path", ".")
                result = self._list_one(scope, path)
                return ExecutionResult(
                    ExecutionStatus.SUCCESS,
                    json.dumps(result, ensure_ascii=False),
                    evidence=f"{scope}:{path}",
                )

            paths = params.get("paths")
            if paths is None:
                path = params.get("path")
                paths = [path] if path is not None else []
            if not isinstance(paths, list) or not paths or len(paths) > self.MAX_FILES:
                return ExecutionResult(
                    ExecutionStatus.FAILED,
                    f"Provide 1-{self.MAX_FILES} paths for {action}.",
                )
            if any(not isinstance(item, str) for item in paths):
                return ExecutionResult(ExecutionStatus.FAILED, "Every path must be a string.")

            if action == "read":
                results = [self._read_one(scope, item) for item in paths]
            else:
                results = [self._metadata_one(scope, item) for item in paths]

            output = {"action": action, "scope": scope, "results": results}
            return ExecutionResult(
                ExecutionStatus.SUCCESS,
                json.dumps(output, ensure_ascii=False),
                evidence=", ".join(f"{scope}:{item}" for item in paths),
            )
        except (SecurityViolation, PermissionError) as exc:
            return ExecutionResult(ExecutionStatus.DENIED, str(exc))
        except (OSError, ValueError, TypeError) as exc:
            return ExecutionResult(ExecutionStatus.FAILED, str(exc))
'@

# Prepare and verify a real backup before any source file is changed.
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupDir = Join-Path $Root 'backups\source_patches'
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$BackupPath = Join-Path $BackupDir "planner.py.$Timestamp.bak"
Copy-Item -LiteralPath $PlannerPath -Destination $BackupPath
$OriginalHash = (Get-FileHash -LiteralPath $PlannerPath -Algorithm SHA256).Hash
$BackupHash = (Get-FileHash -LiteralPath $BackupPath -Algorithm SHA256).Hash
if ($OriginalHash -ne $BackupHash) { throw 'Backup hash verification failed. No source code was modified.' }

New-Item -ItemType Directory -Path $SkillDir | Out-Null
[System.IO.File]::WriteAllText((Join-Path $SkillDir 'manifest.json'), $Manifest, $Utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $SkillDir 'skill.py'), $SkillCode, $Utf8NoBom)

$PlannerTemp = "$PlannerPath.$Timestamp.tmp"
[System.IO.File]::WriteAllText($PlannerTemp, $PlannerUpdated, $Utf8NoBom)
Move-Item -LiteralPath $PlannerTemp -Destination $PlannerPath -Force

Write-Host ''
Write-Host 'PATCH APPLIED' -ForegroundColor Green
Write-Host "Skill manifest : $SkillDir\manifest.json"
Write-Host "Skill code     : $SkillDir\skill.py"
Write-Host "Planner backup : $BackupPath"
Write-Host "Backup SHA256  : $BackupHash"
Write-Host 'Planner routing rules inserted.'
Write-Host 'Next: run the verification script/commands before launching FORGE.' -ForegroundColor Yellow
