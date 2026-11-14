from __future__ import annotations
from pathlib import Path
from config import WORKSPACE_DIR


class SecurityViolation(Exception):
    pass


class PermissionEngine:
    @staticmethod
    def validate_path(relative_path: str | Path) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute():
            raise SecurityViolation("Chỉ chấp nhận đường dẫn tương đối bên trong workspace.")
        root = WORKSPACE_DIR.resolve()
        target = (root / raw).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise SecurityViolation(f"Từ chối truy cập ngoài workspace: {target}") from exc
        return target

    @staticmethod
    def ensure_parent(relative_path: str | Path) -> Path:
        target = PermissionEngine.validate_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Resolve again after mkdir to guard against unexpected symlink traversal.
        return PermissionEngine.validate_path(target.relative_to(WORKSPACE_DIR.resolve()))
