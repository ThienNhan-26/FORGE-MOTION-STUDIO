from __future__ import annotations
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.tools.filesystem import write_file
class WriteFileSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(name="write_file", version="2.0.0", description="Tạo hoặc cập nhật file trong workspace theo Permission Engine.", input_schema={"filename":"string","content":"string"}, permissions=["workspace_write"])
    def execute(self, params: dict) -> ExecutionResult:
        filename, content = params.get("filename"), params.get("content")
        if not isinstance(filename,str) or not filename.strip() or not isinstance(content,str):
            return ExecutionResult(ExecutionStatus.FAILED,"Thiếu filename hoặc content dạng chuỗi.")
        return write_file(filename,content)
