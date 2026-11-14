from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
from agents.coder import CoderAgent
from config import FORGE_ENABLE_PYTHON_EXECUTION, FORGE_MAX_REPAIR_ROUNDS, WORKSPACE_DIR
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


class PythonTaskSkill(BaseSkill):
    def __init__(self):
        self.coder = CoderAgent()
        super().__init__()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="python_task", version="1.0.0",
            description="Dùng Coder tạo file .py, thực thi bằng Python và tự sửa lỗi có giới hạn.",
            input_schema={"prompt": "string", "filename": "string"},
            permissions=["workspace_write", "python_execute"],
        )

    def execute(self, params: dict) -> ExecutionResult:
        if not FORGE_ENABLE_PYTHON_EXECUTION:
            return ExecutionResult(
                ExecutionStatus.DENIED,
                "Python execution đang tắt. Đọc README và đặt FORGE_ENABLE_PYTHON_EXECUTION=true trong .env nếu chấp nhận chạy mã do AI sinh trên máy này.",
            )
        prompt = str(params.get("prompt") or params.get("description") or "").strip()
        filename = str(params.get("filename") or f"task_{params.get('task_id', 'generated')}.py")
        if not prompt:
            return ExecutionResult(ExecutionStatus.FAILED, "Thiếu prompt mô tả chương trình.")
        if not filename.lower().endswith(".py"):
            return ExecutionResult(ExecutionStatus.DENIED, "Tên file phải có đuôi .py.")
        try:
            target = PermissionEngine.ensure_parent(filename)
            if target.exists():
                return ExecutionResult(ExecutionStatus.APPROVAL_REQUIRED, f"File đã tồn tại, không ghi đè: {target}")
            code = self.coder.generate_code(prompt)
            target.write_text(code + "\n", encoding="utf-8")
            last_output = ""
            for attempt in range(FORGE_MAX_REPAIR_ROUNDS + 1):
                result = subprocess.run(
                    [sys.executable, str(target)], cwd=str(WORKSPACE_DIR),
                    capture_output=True, text=True, timeout=45, check=False,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                last_output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
                if result.returncode == 0:
                    return ExecutionResult(
                        ExecutionStatus.SUCCESS,
                        f"Chương trình chạy thành công (lượt {attempt + 1}).\n{last_output[-3000:]}",
                        exit_code=0, evidence=str(target),
                    )
                if attempt >= FORGE_MAX_REPAIR_ROUNDS:
                    return ExecutionResult(ExecutionStatus.FAILED,
                                           f"Đã thử {attempt + 1} lượt nhưng chương trình vẫn lỗi.\n{last_output[-3000:]}",
                                           exit_code=result.returncode, evidence=str(target))
                code = self.coder.generate_code(prompt, previous_code=code, error=last_output[-5000:])
                target.write_text(code + "\n", encoding="utf-8")
            return ExecutionResult(ExecutionStatus.FAILED, last_output, evidence=str(target))
        except SecurityViolation as exc:
            return ExecutionResult(ExecutionStatus.DENIED, str(exc))
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Script vượt quá giới hạn 45 giây: {exc}", evidence=str(target))
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Python task lỗi: {exc}")
