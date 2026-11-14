from __future__ import annotations

import json
import os
import tempfile
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

        project_dir = (WORKSPACE_DIR / "projects" / scene.project_id).resolve()
        try:
            project_dir.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            return ExecutionResult(ExecutionStatus.DENIED, "project_id vượt khỏi workspace.")

        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            target = project_dir / "scene.json"
            payload = json.dumps(scene.model_dump(mode="json"), ensure_ascii=False, indent=2)
            fd, temp_name = tempfile.mkstemp(prefix=".scene-", suffix=".tmp", dir=str(project_dir))
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, target)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            return ExecutionResult(
                ExecutionStatus.SUCCESS,
                f"Đã lưu SceneSpec '{scene.title}' với {len(scene.objects)} object.",
                exit_code=0,
                evidence=str(target),
            )
        except OSError as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Không thể ghi SceneSpec: {exc}")
