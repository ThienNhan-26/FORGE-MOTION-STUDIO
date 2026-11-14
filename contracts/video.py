from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class LayerSpec(BaseModel):
    type: Literal["text", "particles"] = "text"
    content: str = ""
    color: str = "#ffffff"

    @field_validator("content", mode="before")
    @classmethod
    def normalize_empty_content(cls, value):
        # Particle layers do not need text. Some LLMs serialize the unused
        # field as null; normalize that to the contract's empty-string default.
        return "" if value is None else value

    @field_validator("color", mode="before")
    @classmethod
    def normalize_color(cls, value):
        # Use the documented default when a model explicitly emits null.
        return "#ffffff" if value is None else value


class SceneSpec(BaseModel):
    duration_seconds: int = Field(default=5, ge=1, le=60)
    bg_color1: str = "#0f172a"
    bg_color2: str = "#4c1d95"
    camera_motion: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"] = Field(
        default="zoom_in",
        description="Camera motion: none, zoom_in, zoom_out, pan_left, or pan_right.",
    )
    layers: list[LayerSpec] = Field(default_factory=list)


class VideoSpec(BaseModel):
    project_id: str = "proj_default"
    title: str = "Untitled"
    scenes: list[SceneSpec] = Field(..., min_length=1, max_length=40)

    @field_validator("project_id")
    @classmethod
    def safe_project_id(cls, value: str) -> str:
        cleaned = "".join(ch for ch in value if ch.isalnum() or ch in "-_")[:64]
        if not cleaned:
            raise ValueError("project_id không hợp lệ")
        return cleaned
