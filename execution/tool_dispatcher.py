from __future__ import annotations
import json
from typing import Any
from core.task import ExecutionResult, ExecutionStatus
from core.skill_registry import SkillRegistry
from storage.database import log_execution
class ToolDispatcher:
    LEGACY_NAMES={"write_file":"write_file","run_python_script":"run_python","render_remotion_video":"render_video"}
    def __init__(self,task_id:str,agent_name:str): self.task_id=task_id; self.agent_name=agent_name
    def _log(self,name:str,args:dict[str,Any],status:str,output:str)->None:
        try: log_execution(self.task_id,self.agent_name,name,json.dumps(args,ensure_ascii=False,default=str),status,str(output))
        except Exception: pass
    def execute(self,tool_name:str,arguments:dict)->ExecutionResult:
        if not isinstance(tool_name,str) or not tool_name.strip(): return ExecutionResult(ExecutionStatus.DENIED,"Tên tool không hợp lệ.")
        if not isinstance(arguments,dict): return ExecutionResult(ExecutionStatus.DENIED,"Arguments phải là dict.")
        name=self.LEGACY_NAMES.get(tool_name,tool_name)
        skill=SkillRegistry.get_skill(name)
        if skill is None:
            SkillRegistry.discover_skills(); skill=SkillRegistry.get_skill(name)
        if skill is None:
            result=ExecutionResult(ExecutionStatus.DENIED,f"Không có skill/tool '{tool_name}'.")
            self._log(tool_name,arguments,result.status.value,result.output); return result
        try:
            result=skill.execute(arguments)
            if not isinstance(result,ExecutionResult): result=ExecutionResult(ExecutionStatus.FAILED,"Skill trả về kết quả không hợp lệ.")
            self._log(tool_name,arguments,result.status.value,result.output); return result
        except Exception as exc:
            self._log(tool_name,arguments,"FAILED",str(exc)); return ExecutionResult(ExecutionStatus.FAILED,str(exc))
