from __future__ import annotations
import json
from pathlib import Path
from contracts.video import VideoSpec


class SpecValidator:
    @staticmethod
    def validate(data: dict | str | Path) -> VideoSpec:
        if isinstance(data, dict):
            payload = data
        else:
            payload = json.loads(Path(data).read_text(encoding="utf-8"))
        return VideoSpec.model_validate(payload)
