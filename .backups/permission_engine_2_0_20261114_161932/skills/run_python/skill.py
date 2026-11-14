from __future__ import annotations
from config import FORGE_ENABLE_PYTHON_EXECUTION
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.tools.terminal import run_python_script


class RunPythonSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="run_python", version="1.0.0",
            description="Chạy file .py đã có trong workspace và trả stdout/stderr.",
            input_schema={"filename": "string", "timeout": "integer optional"},
            permissions=["workspace_read", "python_execute"],
        )

    def execute(self, params: dict) -> ExecutionResult:
        if not FORGE_ENABLE_PYTHON_EXECUTION:
            return ExecutionResult(ExecutionStatus.DENIED,
                                  "Python execution đang tắt. Bật FORGE_ENABLE_PYTHON_EXECUTION=true trong .env sau khi đọc cảnh báo an toàn.")
        filename = params.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            return ExecutionResult(ExecutionStatus.FAILED, "Thiếu filename.")
        timeout = params.get("timeout", 45)
        try:
            timeout = max(1, min(int(timeout), 180))
        except (TypeError, ValueError):
            timeout = 45
        return run_python_script(filename, timeout=timeout)
