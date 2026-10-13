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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkflowExecutionError(RuntimeError):
    def __init__(self, message: str, state: WorkflowState) -> None:
        super().__init__(message)
        self.state = state
