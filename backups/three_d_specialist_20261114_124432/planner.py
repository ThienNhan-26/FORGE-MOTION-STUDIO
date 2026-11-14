from __future__ import annotations

import json
import re
import uuid
from typing import Any

from core.ollama import OllamaClient
from core.skill_registry import SkillRegistry
from config import OLLAMA_MODEL


class PlannerError(RuntimeError):
    pass


class PlannerAgent:
    def __init__(self, client: OllamaClient | None = None):
        # Director / Planner: Gemma 4 E4B
        self.llm = client or OllamaClient(model=OLLAMA_MODEL)

    @staticmethod
    def _extract_json(content: str) -> Any:
        text = content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)

        start_candidates = [
            i for i in (text.find("["), text.find("{"))
            if i >= 0
        ]

        if start_candidates:
            text = text[min(start_candidates):]

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise PlannerError(
                f"Planner trả về JSON lỗi: {exc}. "
                f"Phần đầu phản hồi: {content[:500]}"
            ) from exc

    def create_task_graph(self, user_request: str) -> list[dict[str, Any]]:
        SkillRegistry.discover_skills()
        manifests = SkillRegistry.get_manifests()

        if not manifests:
            raise PlannerError(
                "Không có skill nào được nạp. "
                "Kiểm tra thư mục skills/."
            )

        system = (
            "Bạn là Planner của FORGE, một hệ thống agent chạy local. "
            "Chỉ lập kế hoạch bằng các skill có trong danh sách được cung cấp. "
            "Không giả vờ có công cụ không tồn tại. "
            "Đầu ra phải là JSON hợp lệ."
        )

        user = f"""NHIỆM VỤ NGƯỜI DÙNG:
{user_request}

SKILLS ĐANG CÓ:
{json.dumps(manifests, ensure_ascii=False, indent=2)}

Hãy lập DAG gồm các task nhỏ, độc lập khi có thể. Trả về duy nhất JSON theo cấu trúc:
{{
  "tasks": [
    {{
      "task_id": "t1",
      "title": "Tiêu đề ngắn",
      "task_type": "PYTHON|VIDEO|GENERAL",
      "skill_name": "tên skill đúng chính tả",
      "description": "mục đích và yêu cầu đầy đủ",
      "input_data": {{}},
      "dependencies": []
    }}
  ]
}}

Quy tắc:
- skill_name bắt buộc phải có trong danh sách skill hiện có.
- inspect_files: ONLY for read-only inspection of files/directories. input_data MUST include action (read|list|metadata), scope (workspace|source), and path (or paths). Use scope="source" for approved project source files such as agents/planner.py and core/skill_registry.py; use scope="workspace" for runtime workspace data. NEVER use python_task to read or inspect files.
- task_type is descriptive metadata only. Never use task_type (including GENERAL) as skill_name. skill_name MUST exactly match one of the names in SKILLS currently available.
- python_task: input_data gồm prompt (yêu cầu viết/chạy chương trình) và filename (tên .py tương đối trong workspace).
- write_file: input_data gồm filename và content; không ghi đè file đã có.
- render_video: input_data gồm spec là VideoSpec với project_id, title, scenes; mỗi scene có duration_seconds, bg_color1, bg_color2, camera_motion, layers; camera_motion CHỈ được dùng một trong: none, zoom_in, zoom_out, pan_left, pan_right; layers hiện hỗ trợ type=text hoặc particles. Mỗi layer phải có color là chuỗi màu hex; content luôn phải là chuỗi, không bao giờ dùng null. Với layer particles, dùng content là chuỗi rỗng ''. Với layer text, content phải chứa nội dung chữ.
- create_3d_scene: input_data.scene phải là một object Scene3DSpec v1 hoàn chỉnh để tạo thế giới 3D trong Motion Studio. Các trường cấp cao: project_id, title, style (hiện chỉ hỗ trợ low_poly), width, height, fps, duration_seconds, environment, camera, objects. Camera gồm position, end_position, target, end_target (mỗi giá trị là mảng 3 số), fov và motion (none|push_in|orbit). Mỗi object gồm id duy nhất an toàn, name, kind (island|tree|pine|house|cloud|rock|crystal|cube|sphere), position/rotation/scale (mảng 3 số), color #RRGGBB, visible và animation (none|float|rotate|pulse). Giới hạn tối đa 250 objects.
- render_3d_scene: input_data.project_id là project_id của scene đã tạo bằng create_3d_scene; cần có file workspace/projects/<project_id>/scene.json và dependencies Remotion đã được cài. Khi người dùng yêu cầu tạo và xuất video 3D, tạo task create_3d_scene trước rồi render_3d_scene phụ thuộc vào task đó.
- Không tạo task cho thao tác không có skill hỗ trợ. Nếu nhiệm vụ có nhiều phần, tách thành task và khai báo dependencies bằng task_id.
- Không dùng shell, không yêu cầu cài package, không tuyên bố đã thực thi.
- Đảm bảo mọi dependency trỏ tới một task_id có trong danh sách; không tạo chu trình.
"""

        content = self.llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            json_mode=True,
        )

        parsed = self._extract_json(content)
        tasks = parsed.get("tasks") if isinstance(parsed, dict) else parsed

        if not isinstance(tasks, list) or not tasks:
            raise PlannerError(
                "Planner không tạo task nào. "
                "Hãy diễn đạt nhiệm vụ cụ thể hơn."
            )

        allowed = {m["name"] for m in manifests}
        normalized: list[dict[str, Any]] = []
        used_ids: set[str] = set()

        for index, item in enumerate(tasks, 1):
            if not isinstance(item, dict):
                raise PlannerError(
                    f"Task thứ {index} không phải object JSON."
                )

            task_id = str(item.get("task_id") or f"t{index}").strip()

            if not task_id or task_id in used_ids:
                task_id = f"t{index}_{uuid.uuid4().hex[:4]}"

            used_ids.add(task_id)

            skill_name = str(item.get("skill_name", "")).strip()

            if skill_name not in allowed:
                raise PlannerError(
                    f"Planner chọn skill '{skill_name}' "
                    f"không có trong registry. "
                    f"Skills hợp lệ: {', '.join(sorted(allowed))}"
                )

            input_data = item.get("input_data", {})

            if not isinstance(input_data, dict):
                raise PlannerError(
                    f"input_data của task {task_id} phải là object JSON."
                )

            normalized.append({
                "task_id": task_id,
                "title": str(
                    item.get("title") or f"Task {index}"
                )[:180],
                "task_type": str(
                    item.get("task_type") or "GENERAL"
                ).upper(),
                "skill_name": skill_name,
                "description": str(item.get("description") or ""),
                "input_data": input_data,
                "dependencies": [
                    str(x)
                    for x in item.get("dependencies", [])
                    if isinstance(x, (str, int))
                ],
            })

        valid_ids = {item["task_id"] for item in normalized}

        for item in normalized:
            unknown = set(item["dependencies"]) - valid_ids

            if unknown:
                raise PlannerError(
                    f"Task {item['task_id']} tham chiếu dependency "
                    f"không tồn tại: {', '.join(sorted(unknown))}"
                )

            if item["task_id"] in item["dependencies"]:
                raise PlannerError(
                    f"Task {item['task_id']} phụ thuộc chính nó."
                )

        return normalized