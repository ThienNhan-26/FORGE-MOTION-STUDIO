from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from contracts.scene3d import Scene3DSpec
from core.task import ExecutionStatus
from skills.create_3d_scene.skill import Create3DSceneSkill


def valid_scene(project_id: str = "unit_test_scene") -> dict:
    return {
        "schema_version": 1,
        "project_id": project_id,
        "title": "Unit Test Scene",
        "style": "low_poly",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "duration_seconds": 5,
        "environment": {
            "background": "#B9DCE7",
            "fog_color": "#B9DCE7",
            "fog_near": 10,
            "fog_far": 80,
            "ambient_intensity": 1.0,
            "sun_intensity": 2.0,
        },
        "camera": {
            "position": [8, 6, 9],
            "end_position": [6, 4, 7],
            "target": [0, 0, 0],
            "end_target": [0, 0, 0],
            "fov": 42,
            "motion": "push_in",
        },
        "objects": [{
            "id": "island_main",
            "name": "Main Island",
            "kind": "island",
            "position": [0, 0, 0],
            "rotation": [0, 0, 0],
            "scale": [5, 1, 5],
            "color": "#7DA45B",
            "visible": True,
            "animation": "float",
        }],
    }


def test_scene_dict_saves_without_loading_dedicated_model(tmp_path: Path):
    skill = Create3DSceneSkill()
    with patch("skills.create_3d_scene.skill.WORKSPACE_DIR", tmp_path):
        result = skill.execute({"scene": valid_scene(), "project_id": "unit_test_scene"})
    assert result.status == ExecutionStatus.SUCCESS
    saved = tmp_path / "projects" / "unit_test_scene" / "scene.json"
    assert saved.is_file()
    assert Scene3DSpec.model_validate(json.loads(saved.read_text(encoding="utf-8")))


def test_prompt_uses_regular_planner_model_not_3d_model(tmp_path: Path):
    class FakeClient:
        def __init__(self, model):
            assert model == "planner-model"

        def chat(self, messages, temperature=0.1, json_mode=False):
            assert json_mode is True
            return json.dumps(valid_scene("prompt_scene"))

    skill = Create3DSceneSkill()
    with (
        patch("skills.create_3d_scene.skill.WORKSPACE_DIR", tmp_path),
        patch("skills.create_3d_scene.skill.OLLAMA_MODEL", "planner-model"),
        patch("skills.create_3d_scene.skill.OllamaClient", FakeClient),
    ):
        result = skill.execute({
            "prompt": "Một hòn đảo bay với cây và camera tiến gần.",
            "project_id": "prompt_scene",
        })
    assert result.status == ExecutionStatus.SUCCESS
    assert (tmp_path / "projects" / "prompt_scene" / "scene.json").is_file()


def test_rejects_project_id_mismatch(tmp_path: Path):
    skill = Create3DSceneSkill()
    with patch("skills.create_3d_scene.skill.WORKSPACE_DIR", tmp_path):
        result = skill.execute({
            "scene": valid_scene("scene_a"),
            "project_id": "scene_b",
        })
    assert result.status == ExecutionStatus.FAILED
