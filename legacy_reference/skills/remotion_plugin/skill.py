from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult
from production.remotion.adapter import RemotionAdapter
import os

class RemotionSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="render_video",
            description="Render video motion graphic bằng Remotion.",
            input_schema={"spec_filename": "string", "task_id": "string"}
        )

    def execute(self, params: dict) -> ExecutionResult:
        spec_file = params.get("spec_filename")
        task_id = params.get("task_id")
        return RemotionAdapter.render_video(spec_file, task_id)