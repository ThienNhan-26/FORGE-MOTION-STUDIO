from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import WORKSPACE_DIR
from contracts.scene3d import Scene3DSpec
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from production.remotion.three_adapter import ThreeRemotionAdapter


class Render3DSceneSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="render_3d_scene",
            description="Render an existing workspace/projects/<project_id>/scene.json to an MP4 using Remotion Three.js.",
            input_schema={"project_id": "existing safe project id"},
            permissions=["workspace:read", "workspace:write", "process:remotion-render"],
        )

    def execute(self, params: dict[str, Any]) -> ExecutionResult:
        project_id = str(params.get("project_id", "")).strip()
        if not project_id or not all(ch.isalnum() or ch in "-_" for ch in project_id):
            return ExecutionResult(ExecutionStatus.DENIED, "project_id không hợp lệ.")
        scene_path = (WORKSPACE_DIR / "projects" / project_id / "scene.json").resolve()
        try:
            scene_path.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            return ExecutionResult(ExecutionStatus.DENIED, "Scene nằm ngoài workspace.")
        if not scene_path.is_file():
            return ExecutionResult(ExecutionStatus.FAILED, f"Không tìm thấy scene: {scene_path}")
        try:
            raw = json.loads(scene_path.read_text(encoding="utf-8"))
            spec = Scene3DSpec.model_validate(raw)
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"SceneSpec không thể đọc/validate: {exc}")
        if spec.project_id != project_id:
            return ExecutionResult(ExecutionStatus.DENIED, "project_id trong scene không khớp thư mục project.")
        return ThreeRemotionAdapter.render_scene(spec.model_dump(mode="json"), str(params.get("task_id", "render-3d")))
