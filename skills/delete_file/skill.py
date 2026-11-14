from __future__ import annotations
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.tools.filesystem import delete_file
class DeleteFileSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(name="delete_file", version="1.0.0", description="Xóa một file thường trong workspace; chỉ hoạt động ở WORKSPACE_YOLO.", input_schema={"filename":"string"}, permissions=["workspace_delete"])
    def execute(self, params: dict) -> ExecutionResult:
        filename=params.get("filename")
        if not isinstance(filename,str) or not filename.strip(): return ExecutionResult(ExecutionStatus.FAILED,"Thiếu filename.")
        return delete_file(filename)
