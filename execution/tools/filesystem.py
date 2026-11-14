from __future__ import annotations
import os, tempfile
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation

def write_file(filename: str, content: str) -> ExecutionResult:
    try:
        if not isinstance(content, str):
            return ExecutionResult(ExecutionStatus.FAILED, "content phải là chuỗi.")
        target = PermissionEngine.authorize_write(filename, overwrite=PermissionEngine.is_yolo())
        fd, temp_name = tempfile.mkstemp(prefix=".forge-write-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content); handle.flush(); os.fsync(handle.fileno())
            if PermissionEngine.validate_path(filename) != target:
                raise SecurityViolation("Đường dẫn thay đổi trong lúc ghi.")
            if target.exists() and not PermissionEngine.is_yolo():
                raise SecurityViolation("File vừa được tạo bởi tiến trình khác; từ chối ghi đè.")
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)
        return ExecutionResult(ExecutionStatus.SUCCESS, f"Đã ghi {target}", evidence=str(target))
    except SecurityViolation as exc:
        return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except Exception as exc:
        return ExecutionResult(ExecutionStatus.FAILED, str(exc))

def delete_file(filename: str) -> ExecutionResult:
    try:
        target = PermissionEngine.authorize_delete(filename)
        target = PermissionEngine.validate_path(filename)
        if not target.is_file(): raise SecurityViolation("Đối tượng cần xóa không còn là file thường.")
        target.unlink()
        return ExecutionResult(ExecutionStatus.SUCCESS, f"Đã xóa {target}", evidence=str(target))
    except SecurityViolation as exc:
        return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except FileNotFoundError as exc:
        return ExecutionResult(ExecutionStatus.FAILED, str(exc))
    except Exception as exc:
        return ExecutionResult(ExecutionStatus.FAILED, str(exc))
