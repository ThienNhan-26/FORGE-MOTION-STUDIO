
from __future__ import annotations

import unittest

from contracts.scene3d import Scene3DSpec
from production.remotion.scene_validator import SceneValidator


def make_scene() -> Scene3DSpec:
    return Scene3DSpec.model_validate({
        "schema_version": 1,
        "project_id": "validator-test",
        "title": "Validator Test",
        "style": "low_poly",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "duration_seconds": 10,
        "environment": {
            "background": "#172033",
            "fog_color": "#172033",
            "fog_near": 10,
            "fog_far": 100,
            "ambient_intensity": 1,
            "sun_intensity": 2,
        },
        "camera": {
            "position": [0, 5, 12],
            "end_position": [0, 5, 12],
            "target": [0, 1, 0],
            "end_target": [0, 1, 0],
            "fov": 50,
            "motion": "none",
        },
        "objects": [
            {
                "id": "island",
                "name": "Island",
                "kind": "island",
                "position": [0, 0, 0],
                "rotation": [0, 0, 0],
                "scale": [2.6, 1.7, 2.6],
                "color": "#6e8550",
                "visible": True,
                "animation": "none",
            },
            {
                "id": "house",
                "name": "House",
                "kind": "house",
                "position": [0, 2, 0],
                "rotation": [0, 0, 0],
                "scale": [0.7, 0.7, 0.7],
                "color": "#ecd5aa",
                "visible": True,
                "animation": "none",
            },
        ],
    })


class SceneValidatorTests(unittest.TestCase):

    def test_accepts_reasonable_scene(self):
        report = SceneValidator.validate(make_scene())

        self.assertTrue(report["passed"], report["errors"])
        self.assertTrue(report["checks"]["contract"])
        self.assertEqual(report["metadata"]["visible_object_count"], 2)

    def test_warns_when_camera_is_inside_object_bounds(self):
        scene = make_scene()
        scene.camera.position = (0, 0, 0)
        scene.camera.end_position = (0, 0, 0)
        scene.camera.target = (0, 0, -5)
        scene.camera.end_target = (0, 0, -5)

        report = SceneValidator.validate(scene)

        self.assertTrue(report["passed"], report["errors"])
        codes = {item["code"] for item in report["warnings"]}
        self.assertIn("CAMERA_INSIDE_OBJECT_BOUNDS", codes)

    def test_rejects_scene_without_visible_objects(self):
        scene = make_scene()
        for obj in scene.objects:
            obj.visible = False

        report = SceneValidator.validate(scene)

        self.assertFalse(report["passed"])
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("NO_VISIBLE_OBJECTS", codes)

    def test_warns_about_object_beyond_camera_far_plane(self):
        scene = make_scene()
        scene.objects[1].position = (0, 0, 500)

        report = SceneValidator.validate(scene)

        codes = {item["code"] for item in report["warnings"]}
        self.assertIn("OBJECT_BEYOND_CAMERA_FAR", codes)

    def test_warns_about_extreme_scale_ratio(self):
        scene = make_scene()
        scene.objects[1].scale = (30, 1, 1)

        report = SceneValidator.validate(scene)

        codes = {item["code"] for item in report["warnings"]}
        self.assertIn("EXTREME_SCALE_RATIO", codes)

    def test_warning_does_not_block_render(self):
        scene = make_scene()
        scene.objects[1].scale = (30, 1, 1)

        report = SceneValidator.validate(scene)

        self.assertTrue(report["passed"])
        self.assertGreater(len(report["warnings"]), 0)

    def test_supports_orbit_camera(self):
        scene = make_scene()
        scene.camera.motion = "orbit"
        scene.camera.position = (10, 5, 10)
        scene.camera.end_position = (10, 5, 10)

        report = SceneValidator.validate(scene)

        self.assertIn("camera", report["checks"])
        self.assertIn("spatial", report["checks"])


if __name__ == "__main__":
    unittest.main()
