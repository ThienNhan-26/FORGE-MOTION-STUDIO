
from __future__ import annotations

import math
from typing import Any

from contracts.scene3d import Scene3DSpec


# Approximate local-space bounding radii derived from SceneWorld.tsx.
# These are conservative estimates, not exact mesh intersection tests.
GEOMETRY_RADII: dict[str, float] = {
    "island": 2.65,
    "tree": 1.55,
    "pine": 1.65,
    "house": 1.25,
    "cloud": 1.35,
    "rock": 1.00,
    "crystal": 1.20,
    "sphere": 0.80,
    "cube": math.sqrt(3) / 2,
}

CAMERA_NEAR = 0.1
CAMERA_FAR = 300.0
ORBIT_ANGLE = 1.35


def _distance(a: tuple[float, float, float],
              b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _lerp3(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    t: float,
) -> tuple[float, float, float]:
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _camera_pose(
    scene: Scene3DSpec,
    progress: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Mirror the endpoint behavior of SceneWorld.cameraPose()."""
    raw = min(1.0, max(0.0, progress))

    if scene.camera.motion == "none":
        return scene.camera.position, scene.camera.target

    # SceneWorld uses smoothstep easing. At endpoints this is exactly 0 or 1.
    t = raw * raw * (3.0 - 2.0 * raw)

    position = _lerp3(
        scene.camera.position,
        scene.camera.end_position,
        t,
    )
    target = _lerp3(
        scene.camera.target,
        scene.camera.end_target,
        t,
    )

    if scene.camera.motion == "orbit":
        angle = raw * ORBIT_ANGLE
        dx = position[0] - target[0]
        dy = position[1] - target[1]
        dz = position[2] - target[2]

        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        # Three.js Vector3.applyAxisAngle around positive Y.
        rotated_x = dx * cos_a + dz * sin_a
        rotated_z = -dx * sin_a + dz * cos_a

        position = (
            target[0] + rotated_x,
            target[1] + dy,
            target[2] + rotated_z,
        )

    return position, target


def _object_radius(obj: Any) -> float:
    base_radius = GEOMETRY_RADII.get(obj.kind, 1.0)
    max_scale = max(abs(float(value)) for value in obj.scale)

    # Float animation can move an object by up to 0.14 units.
    # Pulse animation can enlarge scale by up to 5.5%.
    animation_margin = 0.14 if obj.animation == "float" else 0.0
    pulse_factor = 1.055 if obj.animation == "pulse" else 1.0

    return base_radius * max_scale * pulse_factor + animation_margin


class SceneValidator:
    """Pre-render structural and approximate spatial validation."""

    @staticmethod
    def validate(scene: Scene3DSpec | dict[str, Any]) -> dict[str, Any]:
        if not isinstance(scene, Scene3DSpec):
            scene = Scene3DSpec.model_validate(scene)

        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        def add_error(code: str, message: str) -> None:
            errors.append({"code": code, "message": message})

        def add_warning(
            code: str,
            message: str,
            object_id: str | None = None,
        ) -> None:
            item = {"code": code, "message": message}
            if object_id is not None:
                item["object_id"] = object_id
            warnings.append(item)

        visible_objects = [obj for obj in scene.objects if obj.visible]

        if not visible_objects:
            add_error(
                "NO_VISIBLE_OBJECTS",
                "Scene không có object nào đang visible.",
            )

        # Check unusually disproportionate object scales.
        for obj in visible_objects:
            values = [float(value) for value in obj.scale]
            smallest = min(values)
            largest = max(values)

            if smallest > 0 and largest / smallest > 20:
                add_warning(
                    "EXTREME_SCALE_RATIO",
                    "Object có tỷ lệ scale giữa các trục rất lớn; "
                    "hãy kiểm tra hình dạng và framing.",
                    obj.id,
                )

            radius = _object_radius(obj)
            if radius > 100:
                add_warning(
                    "VERY_LARGE_OBJECT",
                    "Bounding radius ước lượng của object vượt 100 units.",
                    obj.id,
                )

        # Camera is sampled at both ends of the shot.
        # Intermediate motion is continuous; these endpoint checks are
        # an inexpensive first gate, not a full per-frame simulation.
        camera_samples = (
            ("start", 0.0),
            ("end", 1.0),
        )

        camera_checks_passed = True
        spatial_checks_passed = True

        for label, progress in camera_samples:
            camera_position, camera_target = _camera_pose(scene, progress)

            target_distance = _distance(camera_position, camera_target)
            if target_distance < CAMERA_NEAR:
                camera_checks_passed = False
                add_error(
                    "CAMERA_TARGET_TOO_CLOSE",
                    f"Camera {label} cách target nhỏ hơn near plane "
                    f"({CAMERA_NEAR}).",
                )
                continue

            for obj in visible_objects:
                center = tuple(float(v) for v in obj.position)
                radius = _object_radius(obj)
                distance = _distance(camera_position, center)

                if distance <= radius:
                    add_warning(
                        "CAMERA_INSIDE_OBJECT_BOUNDS",
                        f"Camera {label} nằm trong bounding sphere ước lượng "
                        f"của object (distance={distance:.2f}, "
                        f"radius={radius:.2f}). Đây chưa phải phép "
                        f"kiểm tra giao cắt mesh chính xác.",
                        obj.id,
                    )
                    camera_checks_passed = False

                elif distance - radius < CAMERA_NEAR:
                    add_warning(
                        "OBJECT_NEAR_CAMERA_CLIP",
                        f"Object có thể giao với vùng near clipping "
                        f"của camera {label}.",
                        obj.id,
                    )
                    camera_checks_passed = False

                if distance - radius > CAMERA_FAR:
                    add_warning(
                        "OBJECT_BEYOND_CAMERA_FAR",
                        f"Object nằm ngoài far plane ước lượng "
                        f"({CAMERA_FAR} units) tại camera {label}.",
                        obj.id,
                    )
                    spatial_checks_passed = False

        # Fog should not end before it begins.
        # Pydantic already enforces this; keep an explicit diagnostic
        # in the validation report for downstream consumers.
        fog_valid = scene.environment.fog_far > scene.environment.fog_near
        if not fog_valid:
            add_error(
                "INVALID_FOG_RANGE",
                "fog_far phải lớn hơn fog_near.",
            )

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "checks": {
                "contract": True,
                "visible_objects": len(visible_objects) > 0,
                "camera": camera_checks_passed,
                "spatial": spatial_checks_passed,
                "fog": fog_valid,
            },
            "metadata": {
                "project_id": scene.project_id,
                "object_count": len(scene.objects),
                "visible_object_count": len(visible_objects),
                "camera_motion": scene.camera.motion,
                "camera_far": CAMERA_FAR,
                "sampling": ["start", "end"],
                "geometry_bounds": "approximate",
            },
        }
