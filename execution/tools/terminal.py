from __future__ import annotations
import os
import subprocess
import sys
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation
from config import WORKSPACE_DIR


def run_python_script(filename: str, timeout: int = 45) -> ExecutionResult:
    try:
        if not filename.lower().endswith(".py"):
            return ExecutionResult(ExecutionStatus.DENIED, "Chỉ hỗ trợ file .py")
        path = PermissionEngine.validate_path(filename)
        if not path.is_file():
            return ExecutionResult(ExecutionStatus.FAILED, f"Không tồn tại file: {filename}")
        proc = subprocess.run([sys.executable, str(path)], cwd=str(WORKSPACE_DIR), capture_output=True,
                              text=True, timeout=timeout, check=False, env=os.environ.copy())
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return ExecutionResult(ExecutionStatus.SUCCESS if proc.returncode == 0 else ExecutionStatus.FAILED,
                               output[-5000:], exit_code=proc.returncode, evidence=str(path))
    except SecurityViolation as exc:
        return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except subprocess.TimeoutExpired:
        return ExecutionResult(ExecutionStatus.FAILED, f"Script vượt quá {timeout} giây.")
    except Exception as exc:
        return ExecutionResult(ExecutionStatus.FAILED, f"Lỗi runtime: {exc}")
