from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class WorkflowState:
    run_id: str
    task: str
    mode: str
    status: str = "running"
    current_step: str = "requirements"
    created_at: str = field(default_factory=timestamp)
    specification: dict[str, Any] = field(default_factory=dict)
    design: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    iterations: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    repair_count: int = 0
    error: str = ""
    next_step: str = "requirements"
    example_id: str | None = None
    max_repairs: int = 2
    review_required: bool = False
    confirmed_specification: dict[str, Any] = field(default_factory=dict)
    requirement_history: list[dict[str, Any]] = field(default_factory=list)
    pending_artifact: dict[str, Any] = field(default_factory=dict)
    confirmed_at: str = ""
    owner_pid: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "WorkflowState":
        from dataclasses import fields
        return cls(**{f.name: value[f.name] for f in fields(cls) if f.name in value})


class WorkflowCancelled(RuntimeError):
    pass


class WorkflowExecutionError(RuntimeError):
    def __init__(self, message: str, state: WorkflowState) -> None:
        super().__init__(message)
        self.state = state
