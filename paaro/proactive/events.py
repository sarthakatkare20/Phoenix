"""
Data models and Enums for Paaro Proactive Intelligence & Action Engine (Step 7).
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, Optional
import uuid


class EventSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def level(self) -> int:
        levels = {
            EventSeverity.LOW: 1,
            EventSeverity.MEDIUM: 2,
            EventSeverity.HIGH: 3,
            EventSeverity.CRITICAL: 4,
        }
        return levels.get(self, 1)

    def __ge__(self, other: "EventSeverity") -> bool:
        if isinstance(other, EventSeverity):
            return self.level >= other.level
        return False

    def __gt__(self, other: "EventSeverity") -> bool:
        if isinstance(other, EventSeverity):
            return self.level > other.level
        return False

    def __le__(self, other: "EventSeverity") -> bool:
        if isinstance(other, EventSeverity):
            return self.level <= other.level
        return False

    def __lt__(self, other: "EventSeverity") -> bool:
        if isinstance(other, EventSeverity):
            return self.level < other.level
        return False


class UserActivityState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    BUSY = "busy"


class ProactiveDecisionType(str, Enum):
    IGNORE = "ignore"
    NOTIFY = "notify"
    ASK = "ask"
    ACT = "act"
    DEFER = "defer"


@dataclass
class ProactiveEvent:
    event_type: str
    source: str = "internal"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    severity: EventSeverity = EventSeverity.LOW
    data: Dict[str, Any] = field(default_factory=dict)
    ttl_seconds: float = 300.0  # Default 5 minutes expiry
    requires_llm: bool = False

    def fingerprint(self) -> str:
        """Deterministic fingerprint for deduplication."""
        # Clean sortable data representation
        try:
            data_str = json.dumps(self.data, sort_keys=True)
        except Exception:
            data_str = str(self.data)
        raw = f"{self.event_type}:{self.source}:{data_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        if self.ttl_seconds <= 0:
            return False
        if current_time is not None:
            if self.timestamp < 1_000_000_000.0 and current_time > 1_000_000_000.0:
                return False
            return (current_time - self.timestamp) > self.ttl_seconds
        if self.timestamp < 1_000_000_000.0:
            return False
        return (time.time() - self.timestamp) > self.ttl_seconds



    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp,
            "severity": self.severity.value if isinstance(self.severity, EventSeverity) else self.severity,
            "data": self.data,
            "ttl_seconds": self.ttl_seconds,
            "requires_llm": self.requires_llm,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProactiveEvent":
        sev_val = d.get("severity", "low")
        try:
            sev = EventSeverity(sev_val)
        except ValueError:
            sev = EventSeverity.LOW

        return cls(
            id=d.get("id", str(uuid.uuid4())),
            event_type=d.get("event_type", "generic"),
            source=d.get("source", "external"),
            timestamp=float(d.get("timestamp", time.time())),
            severity=sev,
            data=d.get("data", {}),
            ttl_seconds=float(d.get("ttl_seconds", 300.0)),
            requires_llm=bool(d.get("requires_llm", False)),
        )


@dataclass
class ProactiveDecision:
    decision: ProactiveDecisionType
    event: ProactiveEvent
    message: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    reason: str = ""
    should_speak: bool = False
    requires_llm: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value if isinstance(self.decision, ProactiveDecisionType) else self.decision,
            "event": self.event.to_dict(),
            "message": self.message,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "reason": self.reason,
            "should_speak": self.should_speak,
            "requires_llm": self.requires_llm,
            "created_at": self.created_at,
        }
