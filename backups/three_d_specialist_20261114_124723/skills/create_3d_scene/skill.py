from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from config import WORKSPACE_DIR
from contracts.scene3d import Scene3DSpec
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from agents.three_d_specialist import ThreeDSpecialistAgent


class Create3DSceneSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="create_3d_scene",
            description=(
                "Use the dedicated 3D Specialist to generate a SceneSpec v1 from a natural-language "
                "world description, validate it, and save workspace/projects/<project_id>/scene.json. "
                "A prebuilt scene object may also be supplied."
            ),
            input_schema={
                "prompt": "natural-language 3D world description (preferred)",
                "project_id": "safe project id, ASCII letters/numbers/_/-",
                "scene": "optional complete Scene3DSpec v1 object",
            },
            permissions=["workspace:write", "ollama:3d-specialist"],
        )

    def execute(self, params: dict[str, Any]) -> ExecutionResult:
        raw = params.get("scene")
        try:
            if isinstance(raw, dict):
                scene = Scene3DSpec.model_validate(raw)
            else:
                prompt = str(params.get("prompt") or params.get("description") or "").strip()
                project_id = str(params.get("project_id") or "").strip()
                if not project_id:
                    return ExecutionResult(
                        ExecutionStatus.FAILED,
                        "Thiếu input_data.project_id cho 3D Specialist.",
                    )
                scene = ThreeDSpecialistAgent().generate_scene(prompt, project_id)
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Không tạo được SceneSpec: {exc}")

        project_dir = (WORKSPACE_DIR / "projects" / scene.project_id).resolve()
        try:
            project_dir.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            return ExecutionResult(ExecutionStatus.DENIED, "project_id vượt khỏi workspace.")

        temp_name = None
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            target = project_dir / "scene.json"
            payload = json.dumps(scene.model_dump(mode="json"), ensure_ascii=False, indent=2)
            fd, temp_name = tempfile.mkstemp(prefix=".scene-", suffix=".tmp", dir=str(project_dir))
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
            temp_name = None
            return ExecutionResult(
                ExecutionStatus.SUCCESS,
                f"3D Specialist đã tạo và lưu SceneSpec '{scene.title}' với {len(scene.objects)} object.",
                exit_code=0,
                evidence=str(target),
            )
        except OSError as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Không thể ghi SceneSpec: {exc}")
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
