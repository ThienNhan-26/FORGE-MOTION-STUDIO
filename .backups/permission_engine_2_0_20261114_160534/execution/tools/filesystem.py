from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


def write_file(filename: str, content: str) -> ExecutionResult:
    try:
        target = PermissionEngine.ensure_parent(filename)
        if target.exists():
            return ExecutionResult(ExecutionStatus.DENIED, f"File đã tồn tại: {target}")
        target.write_text(content, encoding="utf-8")
        return ExecutionResult(ExecutionStatus.SUCCESS, f"Đã tạo {target}", evidence=str(target))
    except SecurityViolation as exc:
        return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except Exception as exc:
        return ExecutionResult(ExecutionStatus.FAILED, str(exc))
