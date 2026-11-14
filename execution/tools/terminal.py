from __future__ import annotations
import os, subprocess, sys
from config import WORKSPACE_DIR, FORGE_ENABLE_PYTHON_EXECUTION, FORGE_ALLOW_UNSANDBOXED_PYTHON, FORGE_PYTHON_TIMEOUT_SECONDS
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation

def run_python_script(filename: str, timeout: int | None = None) -> ExecutionResult:
    try:
        if not isinstance(filename, str) or not filename.lower().endswith(".py"):
            return ExecutionResult(ExecutionStatus.DENIED, "Chỉ hỗ trợ file .py.")
        if not FORGE_ENABLE_PYTHON_EXECUTION:
            return ExecutionResult(ExecutionStatus.DENIED, "Python execution đang tắt.")
        if not FORGE_ALLOW_UNSANDBOXED_PYTHON:
            return ExecutionResult(ExecutionStatus.DENIED, "Từ chối chạy Python: chưa có OS-level sandbox. Workspace path validation không cô lập được tiến trình Python.")
        path = PermissionEngine.validate_path(filename)
        if not path.is_file(): return ExecutionResult(ExecutionStatus.FAILED, f"Không tồn tại file: {filename}")
        limit = FORGE_PYTHON_TIMEOUT_SECONDS
        run_timeout = limit if timeout is None else min(limit, max(1, int(timeout)))
        safe_env = {k:v for k,v in os.environ.items() if k.upper() in {"PATH","SYSTEMROOT","WINDIR","TEMP","TMP","SYSTEMDRIVE","COMSPEC","PATHEXT"}}
        safe_env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run([sys.executable, "-I", str(path)], cwd=str(WORKSPACE_DIR), capture_output=True, text=True, timeout=run_timeout, check=False, env=safe_env, shell=False)
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return ExecutionResult(ExecutionStatus.SUCCESS if proc.returncode == 0 else ExecutionStatus.FAILED, output[-5000:], exit_code=proc.returncode, evidence=str(path))
    except SecurityViolation as exc: return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except subprocess.TimeoutExpired: return ExecutionResult(ExecutionStatus.FAILED, "Python script vượt quá giới hạn thời gian.")
    except Exception as exc: return ExecutionResult(ExecutionStatus.FAILED, f"Lỗi runtime: {exc}")
