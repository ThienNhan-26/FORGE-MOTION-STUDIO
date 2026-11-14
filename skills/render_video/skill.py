from __future__ import annotations
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from production.remotion.adapter import RemotionAdapter


class RemotionSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="render_video", version="1.0.0",
            description="Render video motion graphic bằng Remotion; nhận VideoSpec JSON trong input_data.spec.",
            input_schema={"spec": "VideoSpec object"},
            permissions=["workspace_read", "workspace_write", "remotion_render"],
        )

    def execute(self, params: dict) -> ExecutionResult:
        spec = params.get("spec")
        if spec is None and params.get("spec_filename"):
            return RemotionAdapter.render_video_file(str(params["spec_filename"]), str(params.get("task_id", "task")))
        return RemotionAdapter.render_video(spec, str(params.get("task_id", "task")))
