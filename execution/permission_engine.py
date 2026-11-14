from __future__ import annotations
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from config import WORKSPACE_DIR, FORGE_PERMISSION_MODE

class SecurityViolation(Exception):
    """Raised when a requested operation violates FORGE's security policy."""

class PermissionEngine:
    SAFE = "SAFE"
    WORKSPACE_YOLO = "WORKSPACE_YOLO"

    @classmethod
    def mode(cls) -> str:
        return FORGE_PERMISSION_MODE

    @classmethod
    def is_yolo(cls) -> bool:
        return cls.mode() == cls.WORKSPACE_YOLO

    @staticmethod
    def _parts(value: str | Path) -> tuple[str, ...]:
        raw = str(value)
        if not raw or not raw.strip() or "\x00" in raw:
            raise SecurityViolation("Đường dẫn không hợp lệ hoặc để trống.")
        win = PureWindowsPath(raw)
        if win.is_absolute() or win.drive or raw.startswith(("\\\\", "//")):
            raise SecurityViolation("Chỉ chấp nhận đường dẫn tương đối bên trong workspace.")
        posix = PurePosixPath(raw.replace("\\", "/"))
        if posix.is_absolute() or any(part == ".." for part in posix.parts):
            raise SecurityViolation("Đường dẫn tuyệt đối hoặc traversal '..' bị từ chối.")
        parts = tuple(part for part in posix.parts if part not in {"", "."})
        if not parts:
            raise SecurityViolation("Phải chỉ định một đường dẫn bên trong workspace.")
        return parts

    @staticmethod
    def _has_link(root: Path, parts: tuple[str, ...]) -> bool:
        current = root
        for part in parts:
            current = current / part
            try:
                if current.is_symlink() or os.path.islink(str(current)):
                    return True
            except OSError:
                return True
        return False

    @classmethod
    def validate_path(cls, relative_path: str | Path) -> Path:
        parts = cls._parts(relative_path)
        root = WORKSPACE_DIR.resolve()
        if cls._has_link(root, parts):
            raise SecurityViolation("Không cho phép truy cập qua symbolic link/junction.")
        target = root.joinpath(*parts).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise SecurityViolation(f"Từ chối truy cập ngoài workspace: {target}") from exc
        return target

    @classmethod
    def ensure_parent(cls, relative_path: str | Path) -> Path:
        target = cls.validate_path(relative_path)
        root = WORKSPACE_DIR.resolve()
        try:
            target.parent.relative_to(root)
        except ValueError as exc:
            raise SecurityViolation("Thư mục cha nằm ngoài workspace.") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        return cls.validate_path(relative_path)

    @classmethod
    def authorize_write(cls, relative_path: str | Path, overwrite: bool = False) -> Path:
        target = cls.ensure_parent(relative_path)
        if target.exists() and not target.is_file():
            raise SecurityViolation("Chỉ được ghi file thường; không ghi đè thư mục.")
        if overwrite and not cls.is_yolo():
            raise SecurityViolation("Ghi đè chỉ được phép trong WORKSPACE_YOLO.")
        if target.exists() and not overwrite:
            raise SecurityViolation(f"File đã tồn tại: {target}")
        return target

    @classmethod
    def authorize_delete(cls, relative_path: str | Path) -> Path:
        if not cls.is_yolo():
            raise SecurityViolation("Xóa file chỉ được phép trong WORKSPACE_YOLO.")
        target = cls.validate_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Không tồn tại file: {relative_path}")
        if not target.is_file():
            raise SecurityViolation("Chỉ cho phép xóa file thường; không xóa thư mục.")
        return target
