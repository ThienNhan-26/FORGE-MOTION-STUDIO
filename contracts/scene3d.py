from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Vector3 = tuple[float, float, float]


class CameraSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    position: Vector3 = (9.0, 7.0, 11.0)
    end_position: Vector3 = (7.0, 5.0, 9.0)
    target: Vector3 = (0.0, 1.0, 0.0)
    end_target: Vector3 = (0.0, 1.0, 0.0)
    fov: float = Field(default=42.0, ge=20.0, le=100.0)
    motion: Literal["none", "push_in", "orbit"] = "push_in"

    @model_validator(mode="after")
    def camera_must_not_look_at_its_own_position(self):
        if sum((a - b) ** 2 for a, b in zip(self.position, self.target)) < 1e-8:
            raise ValueError("camera.position phải khác camera.target")
        if self.motion != "none" and sum((a - b) ** 2 for a, b in zip(self.end_position, self.end_target)) < 1e-8:
            raise ValueError("camera.end_position phải khác camera.end_target")
        return self


class EnvironmentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    background: str = "#b9dce7"
    fog_color: str = "#b9dce7"
    fog_near: float = Field(default=18.0, ge=0.0, le=500.0)
    fog_far: float = Field(default=65.0, ge=1.0, le=1000.0)
    ambient_intensity: float = Field(default=1.25, ge=0.0, le=5.0)
    sun_intensity: float = Field(default=2.2, ge=0.0, le=10.0)

    @field_validator("background", "fog_color")
    @classmethod
    def safe_environment_color(cls, value: str) -> str:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError("environment colors phải có định dạng #RRGGBB")
        return value

    @model_validator(mode="after")
    def fog_range_must_be_ordered(self):
        if self.fog_far <= self.fog_near:
            raise ValueError("environment.fog_far phải lớn hơn fog_near")
        return self


class ObjectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["island", "tree", "pine", "house", "cloud", "rock", "crystal", "cube", "sphere"]
    position: Vector3 = (0.0, 0.0, 0.0)
    rotation: Vector3 = (0.0, 0.0, 0.0)
    scale: Vector3 = (1.0, 1.0, 1.0)
    color: str = "#7da45b"
    visible: bool = True
    animation: Literal["none", "float", "rotate", "pulse"] = "none"

    @field_validator("id")
    @classmethod
    def safe_object_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            raise ValueError("object id chỉ được chứa chữ, số, gạch ngang và gạch dưới")
        return value

    @field_validator("color")
    @classmethod
    def safe_color(cls, value: str) -> str:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError("color phải có định dạng hex #RRGGBB")
        return value

    @model_validator(mode="after")
    def positive_scale(self):
        if any(component <= 0 or component > 100 for component in self.scale):
            raise ValueError("scale phải lớn hơn 0 và không vượt quá 100")
        return self


class Scene3DSpec(BaseModel):
    """Portable, deterministic scene contract shared by Preview and Remotion."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1] = 1
    project_id: str = "floating-island"
    title: str = "Floating Island"
    style: Literal["low_poly"] = "low_poly"
    width: int = Field(default=1920, ge=640, le=3840)
    height: int = Field(default=1080, ge=360, le=2160)
    fps: int = Field(default=30, ge=24, le=60)
    duration_seconds: int = Field(default=18, ge=3, le=120)
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    camera: CameraSpec = Field(default_factory=CameraSpec)
    objects: list[ObjectSpec] = Field(min_length=1, max_length=250)

    @field_validator("project_id")
    @classmethod
    def safe_project_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            raise ValueError("project_id chỉ được chứa chữ ASCII, số, gạch ngang và gạch dưới")
        return value

    @model_validator(mode="after")
    def unique_object_ids(self):
        ids = [obj.id for obj in self.objects]
        if len(ids) != len(set(ids)):
            raise ValueError("object id phải duy nhất trong scene")
        return self
