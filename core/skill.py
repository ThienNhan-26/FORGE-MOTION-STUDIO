from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from core.task import ExecutionResult


@dataclass
class SkillManifest:
    name: str
    version: str = "1.0.0"
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)


class BaseSkill:
    """Contract for plugins. Scheduler knows only this interface."""
    def __init__(self) -> None:
        self.manifest = self.get_manifest()

    def get_manifest(self) -> SkillManifest:
        raise NotImplementedError

    def execute(self, params: dict[str, Any]) -> ExecutionResult:
        raise NotImplementedError
