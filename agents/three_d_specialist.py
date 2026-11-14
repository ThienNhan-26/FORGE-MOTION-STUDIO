from __future__ import annotations

import json
import re
from typing import Any

from config import FORGE_MAX_REPAIR_ROUNDS, OLLAMA_3D_MODEL
from contracts.scene3d import Scene3DSpec
from core.ollama import OllamaClient


class ThreeDSpecialistError(RuntimeError):
    pass


class ThreeDSpecialistAgent:
    """Generate declarative SceneSpec JSON; never emits Python/Blender code."""

    def __init__(self, client: OllamaClient | None = None):
        self.llm = client or OllamaClient(model=OLLAMA_3D_MODEL)

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        text = content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ThreeDSpecialistError("3D Specialist không trả về JSON object.")
        try:
            payload = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ThreeDSpecialistError(f"JSON SceneSpec bị lỗi: {exc}") from exc
        if not isinstance(payload, dict):
            raise ThreeDSpecialistError("SceneSpec phải là JSON object.")
        return payload

    def generate_scene(self, prompt: str, project_id: str) -> Scene3DSpec:
        prompt = str(prompt or "").strip()
        project_id = str(project_id or "").strip()
        if not prompt:
            raise ThreeDSpecialistError("Thiếu mô tả thế giới 3D.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project_id):
            raise ThreeDSpecialistError("project_id không hợp lệ.")

        system = f"""
Bạn là 3D World Builder của FORGE Motion Studio.
Nhiệm vụ: chuyển mô tả thành duy nhất một JSON SceneSpec v1 hợp lệ.
TUYỆT ĐỐI không trả mã Python, JavaScript, Blender bpy, markdown hay giải thích.

RÀNG BUỘC CONTRACT:
- schema_version: 1; project_id bắt buộc đúng là "{project_id}".
- style chỉ được là "low_poly".
- width 640..3840; height 360..2160; fps 24..60; duration_seconds 3..120.
- environment: background và fog_color dạng #RRGGBB; fog_far > fog_near.
- camera: position, end_position, target, end_target là mảng 3 số; fov 20..100;
  motion chỉ là none, push_in hoặc orbit; camera không được trùng target.
- objects: từ 1 đến 250 phần tử; id duy nhất, chỉ gồm chữ ASCII/số/_/-;
  kind chỉ thuộc island, tree, pine, house, cloud, rock, crystal, cube, sphere;
  position/rotation/scale là mảng 3 số; scale mỗi chiều >0 và <=100;
  color là #RRGGBB; animation chỉ là none, float, rotate, pulse.
- Không thêm trường ngoài schema. Dùng tọa độ và tỷ lệ có tính nhất quán không gian.
- Tạo bố cục có chủ đích, phân lớp tiền cảnh/trung cảnh/hậu cảnh;
  tránh đặt vật thể chồng lên nhau vô nghĩa. Tạo đủ chi tiết theo yêu cầu,
  nhưng không vượt 250 objects.
- JSON phải parse được trực tiếp.
CẤU TRÚC:
{{
  "schema_version": 1,
  "project_id": "{project_id}",
  "title": "Tên cảnh",
  "style": "low_poly",
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "duration_seconds": 18,
  "environment": {{
    "background": "#B9DCE7",
    "fog_color": "#B9DCE7",
    "fog_near": 18,
    "fog_far": 65,
    "ambient_intensity": 1.25,
    "sun_intensity": 2.2
  }},
  "camera": {{
    "position": [9, 7, 11],
    "end_position": [7, 5, 9],
    "target": [0, 1, 0],
    "end_target": [0, 1, 0],
    "fov": 42,
    "motion": "push_in"
  }},
  "objects": [
    {{
      "id": "main_island",
      "name": "Main Island",
      "kind": "island",
      "position": [0, 0, 0],
      "rotation": [0, 0, 0],
      "scale": [6, 1.5, 6],
      "color": "#7DA45B",
      "visible": true,
      "animation": "none"
    }}
  ]
}}
"""
        user = f"PROJECT_ID: {project_id}\nMÔ TẢ CẢNH:\n{prompt}\n\nHãy tạo SceneSpec hoàn chỉnh."
        content = self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.15,
            json_mode=True,
        )

        attempts = max(0, int(FORGE_MAX_REPAIR_ROUNDS)) + 1
        last_error = ""
        for attempt in range(attempts):
            try:
                raw = self._extract_json(content)
                raw["project_id"] = project_id
                return Scene3DSpec.model_validate(raw)
            except Exception as exc:
                last_error = str(exc)
                if attempt + 1 >= attempts:
                    break
                content = self.llm.chat(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": (
                            f"JSON SceneSpec trước đó không hợp lệ.\nLỖI VALIDATION:\n{last_error}\n"
                            "Hãy sửa toàn bộ JSON theo contract. Chỉ trả JSON object hoàn chỉnh."
                        )},
                    ],
                    temperature=0.05,
                    json_mode=True,
                )
        raise ThreeDSpecialistError(
            f"Không thể tạo SceneSpec hợp lệ sau {attempts} lượt: {last_error}"
        )
