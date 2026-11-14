from __future__ import annotations
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


class WriteFileSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="write_file", version="1.0.0",
            description="Tạo file mới bên trong workspace. Không ghi đè file đã tồn tại.",
            input_schema={"filename": "string", "content": "string"},
            permissions=["workspace_write"],
        )

    def execute(self, params: dict) -> ExecutionResult:
        filename = params.get("filename")
        content = params.get("content")
        if not isinstance(filename, str) or not filename.strip() or not isinstance(content, str):
            return ExecutionResult(ExecutionStatus.FAILED, "Thiếu filename hoặc content dạng chuỗi.")
        try:
            target = PermissionEngine.ensure_parent(filename)
            if target.exists():
                return ExecutionResult(ExecutionStatus.DENIED,
                                       f"File đã tồn tại: {target}. Hãy chọn tên mới; FORGE không tự ghi đè.")
            target.write_text(content, encoding="utf-8", newline="\n")
            return ExecutionResult(ExecutionStatus.SUCCESS, f"Đã tạo {target.name} ({target.stat().st_size} bytes).", evidence=str(target))
        except SecurityViolation as exc:
            return ExecutionResult(ExecutionStatus.DENIED, str(exc))
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Không thể tạo file: {exc}")
