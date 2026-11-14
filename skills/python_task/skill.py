from __future__ import annotations
from agents.coder import CoderAgent
from config import FORGE_MAX_REPAIR_ROUNDS
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine
from execution.tools.filesystem import write_file
from execution.tools.terminal import run_python_script
class PythonTaskSkill(BaseSkill):
    def __init__(self): self.coder=CoderAgent(); super().__init__()
    def get_manifest(self)->SkillManifest:
        return SkillManifest(name="python_task",version="2.0.0",description="Tạo file Python, chạy qua execution gate và tự sửa lỗi có giới hạn.",input_schema={"prompt":"string","filename":"string"},permissions=["workspace_write","python_execute"])
    def execute(self,params:dict)->ExecutionResult:
        prompt=str(params.get("prompt") or params.get("description") or "").strip()
        filename=str(params.get("filename") or f"task_{params.get('task_id','generated')}.py")
        if not prompt: return ExecutionResult(ExecutionStatus.FAILED,"Thiếu prompt mô tả chương trình.")
        if not filename.lower().endswith(".py"): return ExecutionResult(ExecutionStatus.DENIED,"Tên file phải có đuôi .py.")
        try:
            target=PermissionEngine.validate_path(filename)
            if target.exists() and not PermissionEngine.is_yolo(): return ExecutionResult(ExecutionStatus.DENIED,f"File đã tồn tại: {target}. SAFE không cho ghi đè.")
            code=self.coder.generate_code(prompt)
            wr=write_file(filename,code.rstrip()+"\n")
            if wr.status!=ExecutionStatus.SUCCESS: return wr
            for attempt in range(FORGE_MAX_REPAIR_ROUNDS+1):
                result=run_python_script(filename)
                if result.status==ExecutionStatus.SUCCESS: return ExecutionResult(ExecutionStatus.SUCCESS,f"Chương trình chạy thành công (lượt {attempt+1}).\n{result.output}",exit_code=0,evidence=str(target))
                if result.status==ExecutionStatus.DENIED: return ExecutionResult(ExecutionStatus.DENIED,f"Code đã tạo tại {target}; thực thi bị chặn: {result.output}",evidence=str(target))
                if attempt>=FORGE_MAX_REPAIR_ROUNDS: return ExecutionResult(ExecutionStatus.FAILED,f"Đã tạo code nhưng không chạy thành công.\n{result.output}",exit_code=result.exit_code,evidence=str(target))
                code=self.coder.generate_code(prompt,previous_code=code,error=result.output[-5000:])
                wr=write_file(filename,code.rstrip()+"\n")
                if wr.status!=ExecutionStatus.SUCCESS: return wr
            return ExecutionResult(ExecutionStatus.FAILED,"Python task kết thúc không có kết quả.")
        except Exception as exc: return ExecutionResult(ExecutionStatus.FAILED,f"Python task lỗi: {exc}")
