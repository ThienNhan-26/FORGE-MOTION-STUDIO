from __future__ import annotations

import os
import tempfile

from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


def write_file(filename: str, content: str) -> ExecutionResult:
    """Create a file in SAFE; create or overwrite a file in WORKSPACE_YOLO."""
    try:
        if not isinstance(content, str):
            return ExecutionResult(ExecutionStatus.FAILED, "content phải là chuỗi văn bản.")

        target = PermissionEngine.authorize_write(
            filename,
            overwrite=PermissionEngine.is_yolo(),
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temporary sibling and atomically replace the destination.
        # The temporary file remains inside the already validated workspace folder.
        fd, temp_name = tempfile.mkstemp(prefix=".forge_write_", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

            # Revalidate immediately before replacement.
            checked_target = PermissionEngine.validate_path(filename)
            if checked_target != target:
                raise SecurityViolation("Đường dẫn thay đổi trong lúc ghi file.")
            if target.exists() and not PermissionEngine.is_yolo():
                raise SecurityViolation("File vừa được tạo bởi tiến trình khác; từ chối ghi đè.")
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        return ExecutionResult(
            ExecutionStatus.SUCCESS,
            f"Đã ghi file: {target}",
            evidence=str(target),
        )
    except SecurityViolation as exc:
        return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except Exception as exc:
        return ExecutionResult(ExecutionStatus.FAILED, str(exc))


def delete_file(filename: str) -> ExecutionResult:
    """Delete one regular file in WORKSPACE_YOLO. Directory deletion is prohibited."""
    try:
        target = PermissionEngine.authorize_delete(filename)
        # Revalidate immediately before unlinking.
        target = PermissionEngine.validate_path(filename)
        if not target.is_file():
            raise SecurityViolation("Đối tượng cần xóa không còn là file thường.")
        target.unlink()
        return ExecutionResult(
            ExecutionStatus.SUCCESS,
            f"Đã xóa file: {target}",
            evidence=str(target),
        )
    except SecurityViolation as exc:
        return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except FileNotFoundError as exc:
        return ExecutionResult(ExecutionStatus.FAILED, str(exc))
    except Exception as exc:
        return ExecutionResult(ExecutionStatus.FAILED, str(exc))
