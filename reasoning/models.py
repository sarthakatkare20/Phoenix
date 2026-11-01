"""
Data models and Enums for Paaro Reasoning & Planning Engine (Step 8).
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid


class TaskComplexity(str, Enum):
    DIRECT = "direct"          # Direct question or single immediate tool (bypasses planner)
    SIMPLE = "simple"          # 1-2 predictable actions
    MULTI_STEP = "multi_step"  # Several dependent actions
    COMPLEX = "complex"        # Conditional execution, diagnosis, replanning, verification

    @property
    def is_fast_path(self) -> bool:
        return self in (TaskComplexity.DIRECT, TaskComplexity.SIMPLE)


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PlanStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PlanStep:
    id: str
    description: str
    action: str
    args: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 2

    def __init__(
        self,
        id: str,
        description: str,
        action: str,
        args: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
        status: StepStatus = StepStatus.PENDING,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        retries: int = 0,
        max_retries: int = 2,
    ):
        self.id = id
        self.description = description
        self.action = action
        self.args = args if args is not None else (parameters or {})
        self.depends_on = list(depends_on) if depends_on else []
        self.status = status
        self.result = result
        self.error = error
        self.retries = retries
        self.max_retries = max_retries

    @property
    def parameters(self) -> Dict[str, Any]:
        return self.args

    @parameters.setter
    def parameters(self, val: Dict[str, Any]) -> None:
        self.args = val

    @property
    def retry_count(self) -> int:
        return self.retries

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "action": self.action,
            "args": self.args,
            "parameters": self.args,
            "depends_on": list(self.depends_on),
            "status": self.status.value if isinstance(self.status, StepStatus) else self.status,
            "result": self.result,
            "error": self.error,
            "retries": self.retries,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlanStep":
        st_val = d.get("status", StepStatus.PENDING.value)
        try:
            st = StepStatus(st_val)
        except ValueError:
            st = StepStatus.PENDING

        args_val = d.get("args") if d.get("args") is not None else d.get("parameters", {})
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            description=d.get("description", ""),
            action=d.get("action", "unknown"),
            args=args_val,
            depends_on=d.get("depends_on", []),
            status=st,
            result=d.get("result"),
            error=d.get("error"),
            retries=int(d.get("retries", 0)),
            max_retries=int(d.get("max_retries", 2)),
        )


@dataclass
class ExecutionPlan:
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: PlanStatus = PlanStatus.CREATED
    replan_count: int = 0
    max_replans: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    context_data: Dict[str, Any] = field(default_factory=dict)

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def all_completed(self) -> bool:
        if not self.steps:
            return False
        return all(s.status == StepStatus.COMPLETED or s.status == StepStatus.SKIPPED for s in self.steps)

    def has_failed(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)

    def ready_steps(self) -> List[PlanStep]:
        """Returns pending steps whose dependencies are all completed."""
        completed_ids = {s.id for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)}
        ready = []
        for s in self.steps:
            if s.status == StepStatus.PENDING:
                if all(dep in completed_ids for dep in s.depends_on):
                    ready.append(s)
        return ready

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value if isinstance(self.status, PlanStatus) else self.status,
            "steps": [s.to_dict() for s in self.steps],
            "replan_count": self.replan_count,
            "max_replans": self.max_replans,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context_data": self.context_data,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExecutionPlan":
        st_val = d.get("status", PlanStatus.CREATED.value)
        try:
            st = PlanStatus(st_val)
        except ValueError:
            st = PlanStatus.CREATED

        steps = [PlanStep.from_dict(sd) for sd in d.get("steps", [])]
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            goal=d.get("goal", ""),
            status=st,
            steps=steps,
            replan_count=int(d.get("replan_count", 0)),
            max_replans=int(d.get("max_replans", 3)),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
            context_data=d.get("context_data", {}),
        )


@dataclass
class StepResult:
    step_id: str
    status: StepStatus = StepStatus.COMPLETED
    output: Optional[Any] = None
    error: Optional[str] = None
    needs_replan: bool = False
    replan_reason: Optional[str] = None
    success: bool = True

    def __init__(
        self,
        step_id: str,
        status: StepStatus = StepStatus.COMPLETED,
        output: Optional[Any] = None,
        error: Optional[str] = None,
        needs_replan: bool = False,
        replan_reason: Optional[str] = None,
        success: Optional[bool] = None,
    ):
        self.step_id = step_id
        self.status = status
        self.output = output
        self.error = error
        self.needs_replan = needs_replan
        self.replan_reason = replan_reason
        if success is not None:
            self.success = success
        else:
            self.success = (status == StepStatus.COMPLETED and not error)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value if isinstance(self.status, StepStatus) else self.status,
            "output": self.output,
            "error": self.error,
            "needs_replan": self.needs_replan,
            "replan_reason": self.replan_reason,
            "success": self.success,
        }


@dataclass
class VerificationResult:
    is_verified: bool
    reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.is_verified

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_verified": self.is_verified,
            "reason": self.reason,
            "metrics": self.metrics,
        }
