import json
import unittest
from unittest.mock import Mock, patch

from agents.three_d_specialist import ThreeDSpecialistAgent


VALID = {
    "schema_version": 1,
    "project_id": "unit_scene",
    "title": "Unit Island",
    "style": "low_poly",
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "duration_seconds": 18,
    "environment": {
        "background": "#B9DCE7",
        "fog_color": "#B9DCE7",
        "fog_near": 18,
        "fog_far": 65,
        "ambient_intensity": 1.25,
        "sun_intensity": 2.2
    },
    "camera": {
        "position": [9, 7, 11],
        "end_position": [7, 5, 9],
        "target": [0, 1, 0],
        "end_target": [0, 1, 0],
        "fov": 42,
        "motion": "push_in"
    },
    "objects": [{
        "id": "island",
        "name": "Island",
        "kind": "island",
        "position": [0, 0, 0],
        "rotation": [0, 0, 0],
        "scale": [6, 1.5, 6],
        "color": "#7DA45B",
        "visible": True,
        "animation": "none"
    }]
}


class SpecialistTests(unittest.TestCase):
    def test_valid_scene_json_is_validated(self):
        client = Mock()
        client.chat.return_value = json.dumps(VALID)
        agent = ThreeDSpecialistAgent(client=client)
        scene = agent.generate_scene("floating island", "unit_scene")
        self.assertEqual(scene.project_id, "unit_scene")
        self.assertEqual(len(scene.objects), 1)

    def test_project_id_is_forced_to_requested_safe_id(self):
        client = Mock()
        wrong = dict(VALID)
        wrong["project_id"] = "wrong"
        client.chat.return_value = json.dumps(wrong)
        scene = ThreeDSpecialistAgent(client=client).generate_scene("island", "unit_scene")
        self.assertEqual(scene.project_id, "unit_scene")

    def test_invalid_json_fails_closed_after_repair_budget(self):
        client = Mock()
        client.chat.return_value = '{"not":'
        with patch("agents.three_d_specialist.FORGE_MAX_REPAIR_ROUNDS", 0):
            with self.assertRaises(Exception):
                ThreeDSpecialistAgent(client=client).generate_scene("island", "unit_scene")


if __name__ == "__main__":
    unittest.main()
