from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import WORKSPACE_DIR
from contracts.scene3d import Scene3DSpec
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus


class Create3DSceneSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="create_3d_scene",
            description="Validate and save a Motion Studio SceneSpec v1 to workspace/projects/<project_id>/scene.json.",
            input_schema={"scene": "complete Scene3DSpec v1 object"},
            permissions=["workspace:write"],
        )

    def execute(self, params: dict[str, Any]) -> ExecutionResult:
        raw = params.get("scene")
        if not isinstance(raw, dict):
            return ExecutionResult(ExecutionStatus.FAILED, "Thiếu input_data.scene dạng object Scene3DSpec.")
        try:
            scene = Scene3DSpec.model_validate(raw)
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"SceneSpec không hợp lệ: {exc}")

        from execution.tools.filesystem import write_file
        relative_path = f"projects/{scene.project_id}/scene.json"
        payload = json.dumps(scene.model_dump(mode="json"), ensure_ascii=False, indent=2)
        result = write_file(relative_path, payload)
        if result.status == ExecutionStatus.SUCCESS:
            result.output = f"Đã lưu SceneSpec '{scene.title}' với {len(scene.objects)} object."
        return result
