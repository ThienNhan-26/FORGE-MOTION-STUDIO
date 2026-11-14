from __future__ import annotations

import os
import subprocess
import sys

from config import (
    WORKSPACE_DIR,
    FORGE_ENABLE_PYTHON_EXECUTION,
    FORGE_ALLOW_UNSANDBOXED_PYTHON,
    FORGE_PYTHON_TIMEOUT_SECONDS,
)
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


def run_python_script(filename: str, timeout: int | None = None) -> ExecutionResult:
    """Run a workspace Python file only when explicitly enabled.

    IMPORTANT: this launches the host Python interpreter. Workspace cwd and path
    validation do not sandbox Python. The extra UNSANDBOXED opt-in is deliberately
    required until a real OS-level sandbox adapter is installed.
    """
    try:
        if not isinstance(filename, str) or not filename.lower().endswith(".py"):
            return ExecutionResult(ExecutionStatus.DENIED, "Chỉ hỗ trợ file .py.")

        if not FORGE_ENABLE_PYTHON_EXECUTION:
            return ExecutionResult(
                ExecutionStatus.DENIED,
                "Python execution đang tắt (FORGE_ENABLE_PYTHON_EXECUTION=false).",
            )

        if not FORGE_ALLOW_UNSANDBOXED_PYTHON:
            return ExecutionResult(
                ExecutionStatus.DENIED,
                "Python chưa được chạy vì chưa có OS sandbox. "
                "Không bật thực thi Python không cô lập chỉ để sử dụng YOLO.",
            )

        path = PermissionEngine.validate_path(filename)
        if not path.exists() or not path.is_file():
            return ExecutionResult(ExecutionStatus.FAILED, f"Không tồn tại file: {filename}")

        run_timeout = FORGE_PYTHON_TIMEOUT_SECONDS if timeout is None else min(
            FORGE_PYTHON_TIMEOUT_SECONDS, max(1, int(timeout))
        )

        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {
                "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
                "SYSTEMDRIVE", "COMSPEC", "PATHEXT",
            }
        }
        proc = subprocess.run(
            [sys.executable, "-I", str(path)],
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=run_timeout,
            check=False,
            env=env,
            shell=False,
        )
        output = (proc.stdout or "")
        if proc.stderr:
            output += "\n" + proc.stderr
        return ExecutionResult(
            ExecutionStatus.SUCCESS if proc.returncode == 0 else ExecutionStatus.FAILED,
            output[-5000:],
            exit_code=proc.returncode,
            evidence=str(path),
        )
    except SecurityViolation as exc:
        return ExecutionResult(ExecutionStatus.DENIED, str(exc))
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            ExecutionStatus.FAILED,
            f"Script vượt quá giới hạn {run_timeout} giây.",
        )
    except (TypeError, ValueError) as exc:
        return ExecutionResult(ExecutionStatus.FAILED, f"Tham số không hợp lệ: {exc}")
    except Exception as exc:
        return ExecutionResult(ExecutionStatus.FAILED, f"Lỗi runtime: {exc}")
