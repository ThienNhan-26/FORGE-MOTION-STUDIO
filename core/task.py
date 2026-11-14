from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DENIED = "DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


@dataclass
class ExecutionResult:
    status: ExecutionStatus
    output: str
    exit_code: int | None = None
    evidence: str | None = None
    review_status: str | None = None
    review_summary: str = ""
    review_rounds: int = 0


@dataclass
class Task:
    task_id: str
    title: str
    description: str = ""
    task_type: str = "GENERAL"
    skill_name: str = ""
    dependencies: list[str] = field(default_factory=list)
    input_data: dict[str, Any] = field(default_factory=dict)
    mission_id: str = ""
    status: TaskStatus = TaskStatus.CREATED
    artifact_path: str | None = None
    result: str = ""
    error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_record(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "task_type": self.task_type,
            "skill_name": self.skill_name,
            "dependencies": self.dependencies,
            "input_data": self.input_data,
            "mission_id": self.mission_id,
            "artifact_path": self.artifact_path,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }
