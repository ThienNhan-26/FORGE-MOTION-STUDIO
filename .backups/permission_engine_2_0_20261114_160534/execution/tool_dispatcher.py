from __future__ import annotations
import json
from core.task import ExecutionResult, ExecutionStatus
from core.skill_registry import SkillRegistry
from storage.database import log_execution


class ToolDispatcher:
    """Compatibility dispatcher. New code should call skills through TaskScheduler."""
    def __init__(self, task_id: str, agent_name: str):
        self.task_id = task_id
        self.agent_name = agent_name

    def execute(self, tool_name: str, arguments: dict) -> ExecutionResult:
        legacy = {"write_file": "write_file", "run_python_script": "run_python", "render_remotion_video": "render_video"}
        skill_name = legacy.get(tool_name, tool_name)
        skill = SkillRegistry.get_skill(skill_name)
        if skill is None:
            SkillRegistry.discover_skills()
            skill = SkillRegistry.get_skill(skill_name)
        if skill is None:
            return ExecutionResult(ExecutionStatus.DENIED, f"Không có skill/tool '{tool_name}'.")
        try:
            result = skill.execute(arguments)
            log_execution(self.task_id, self.agent_name, tool_name,
                          json.dumps(arguments, ensure_ascii=False), result.status.value, result.output)
            return result
        except Exception as exc:
            log_execution(self.task_id, self.agent_name, tool_name,
                          json.dumps(arguments, ensure_ascii=False), "FAILED", str(exc))
            return ExecutionResult(ExecutionStatus.FAILED, str(exc))
