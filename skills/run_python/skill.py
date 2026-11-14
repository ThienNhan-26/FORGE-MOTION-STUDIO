from __future__ import annotations
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.tools.terminal import run_python_script
class RunPythonSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(name="run_python",version="2.0.0",description="Chạy file Python trong workspace khi chính sách cho phép.",input_schema={"filename":"string","timeout":"integer optional"},permissions=["workspace_read","python_execute"])
    def execute(self,params:dict)->ExecutionResult:
        filename=params.get("filename")
        if not isinstance(filename,str) or not filename.strip(): return ExecutionResult(ExecutionStatus.FAILED,"Thiếu filename.")
        try: timeout=None if params.get("timeout") is None else int(params["timeout"])
        except (TypeError,ValueError): return ExecutionResult(ExecutionStatus.FAILED,"timeout phải là số nguyên.")
        return run_python_script(filename,timeout=timeout)
