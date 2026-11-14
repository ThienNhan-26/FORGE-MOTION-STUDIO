from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any

from config import OLLAMA_MODEL, WORKSPACE_DIR
from contracts.scene3d import Scene3DSpec
from core.ollama import OllamaClient
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus


class SceneSpecGenerationError(RuntimeError):
    """SceneSpec generation failed before the scene could be saved."""


class Create3DSceneSkill(BaseSkill):
    """Create a validated scene using Planner output or the existing Planner model.

    The skill deliberately does not depend on a dedicated 3D model. If the
    Planner supplies a complete `scene` object, no extra LLM call is made.
    If it supplies `prompt` + `project_id`, the regular Planner model creates
    the declarative SceneSpec. Geometry generation/rendering remain separate.
    """

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="create_3d_scene",
            description=(
                "Create a SceneSpec v1 using the normal FORGE Planner model when needed, "
                "validate it with Pydantic, and save workspace/projects/<project_id>/scene.json."
            ),
            input_schema={
                "scene": "optional complete SceneSpec v1 object",
                "prompt": "natural-language scene description when scene is not supplied",
                "project_id": "safe project id; required with prompt",
            },
            permissions=["workspace:write", "ollama:planner"],
        )

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise SceneSpecGenerationError("Planner model không trả về JSON object.")
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise SceneSpecGenerationError(f"JSON SceneSpec không hợp lệ: {exc}") from exc
        if not isinstance(value, dict):
            raise SceneSpecGenerationError("SceneSpec phải là JSON object.")
        return value

    @classmethod
    def _generate_scene(cls, prompt: str, project_id: str) -> Scene3DSpec:
        prompt = str(prompt or "").strip()
        project_id = str(project_id or "").strip()
        if not prompt:
            raise SceneSpecGenerationError("Thiếu input_data.prompt.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project_id):
            raise SceneSpecGenerationError("project_id phải gồm 1-64 ký tự ASCII, số, _ hoặc -.")

        system = f"""
Bạn là Scene Designer của FORGE Motion Studio. Tạo duy nhất một JSON SceneSpec v1.
Không trả markdown, code, giải thích hoặc trường ngoài schema.
Contract:
- schema_version=1; project_id="{project_id}"; style="low_poly".
- width 640..3840; height 360..2160; fps 24..60; duration_seconds 3..120.
- environment gồm background, fog_color (#RRGGBB), fog_near, fog_far,
  ambient_intensity, sun_intensity; fog_far phải lớn hơn fog_near.
- camera gồm position, end_position, target, end_target (mỗi giá trị 3 số),
  fov 20..100, motion thuộc none|push_in|orbit; camera không nhìn vào chính nó.
- objects là danh sách 1..250 object. Mỗi object có id, name, kind,
  position, rotation, scale, color, visible, animation.
- kind chỉ thuộc island|tree|pine|house|cloud|rock|crystal|cube|sphere.
- animation chỉ thuộc none|float|rotate|pulse.
- id chỉ dùng chữ ASCII, số, _ hoặc -; id phải duy nhất.
- scale mỗi chiều lớn hơn 0 và không quá 100; color là #RRGGBB.
- Tạo bố cục có chiều sâu điện ảnh, tiền cảnh/trung cảnh/hậu cảnh rõ ràng.
  Chọn camera và animation phù hợp với mô tả; tránh bố cục như catalog vật thể.
- Chỉ tạo số object cần thiết (ưu tiên 8-35), không thêm vật thể vô nghĩa.
Trả về JSON đầy đủ, có thể parse trực tiếp.
"""
        user = f"PROJECT_ID: {project_id}\nYÊU CẦU CẢNH:\n{prompt}"
        raw = OllamaClient(model=OLLAMA_MODEL).chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            json_mode=True,
        )
        payload = cls._extract_json(raw)
        payload["project_id"] = project_id
        return Scene3DSpec.model_validate(payload)

    @staticmethod
    def _validate_scene(raw: Any, params: dict[str, Any]) -> Scene3DSpec:
        if not isinstance(raw, dict):
            raise ValueError("Thiếu input_data.scene dạng object SceneSpec v1.")
        scene = Scene3DSpec.model_validate(raw)
        requested_id = str(params.get("project_id") or "").strip()
        if requested_id and requested_id != scene.project_id:
            raise ValueError(
                f"project_id không khớp: task yêu cầu '{requested_id}', "
                f"nhưng SceneSpec chứa '{scene.project_id}'."
            )
        return scene

    def execute(self, params: dict[str, Any]) -> ExecutionResult:
        try:
            raw = params.get("scene")
            if isinstance(raw, dict):
                scene = self._validate_scene(raw, params)
            else:
                prompt = str(params.get("prompt") or params.get("description") or "").strip()
                project_id = str(params.get("project_id") or "").strip()
                scene = self._generate_scene(prompt, project_id)
        except Exception as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Không tạo được SceneSpec: {exc}",
            )

        workspace = WORKSPACE_DIR.resolve()
        project_dir = (workspace / "projects" / scene.project_id).resolve()
        try:
            project_dir.relative_to(workspace)
        except ValueError:
            return ExecutionResult(ExecutionStatus.DENIED, "project_id vượt khỏi workspace.")

        temp_name = None
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            target = project_dir / "scene.json"
            payload = json.dumps(
                scene.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            fd, temp_name = tempfile.mkstemp(
                prefix=".scene-",
                suffix=".tmp",
                dir=str(project_dir),
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
            temp_name = None
            return ExecutionResult(
                ExecutionStatus.SUCCESS,
                f"Đã lưu SceneSpec '{scene.title}' với {len(scene.objects)} object.",
                exit_code=0,
                evidence=str(target),
            )
        except OSError as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Không thể ghi SceneSpec: {exc}",
            )
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
