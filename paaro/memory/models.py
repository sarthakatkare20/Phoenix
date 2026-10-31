"""
Memory and Session data structures for Paaro (Step 6).
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional
import uuid


class MemoryCategory(str, Enum):
    PROFILE = "profile"
    PREFERENCE = "preference"
    PROJECT = "project"
    FACT = "fact"
    ROUTINE = "routine"
    TASK = "task"
    CONTEXT = "context"


class TurnStatus(str, Enum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    ERROR = "error"


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "sarthak"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", "sarthak"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConversationTurn:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: str = "user"  # "user" | "assistant" | "system"
    content: str = ""
    status: TurnStatus = TurnStatus.COMPLETED
    timestamp: float = field(default_factory=time.time)
    tool_action: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    generation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "status": self.status.value if isinstance(self.status, TurnStatus) else self.status,
            "timestamp": self.timestamp,
            "tool_action": self.tool_action,
            "tool_result": self.tool_result,
            "generation_id": self.generation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationTurn":
        status_val = data.get("status", TurnStatus.COMPLETED.value)
        try:
            status = TurnStatus(status_val)
        except ValueError:
            status = TurnStatus.COMPLETED

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            session_id=data.get("session_id", ""),
            role=data.get("role", "user"),
            content=data.get("content", ""),
            status=status,
            timestamp=data.get("timestamp", time.time()),
            tool_action=data.get("tool_action"),
            tool_result=data.get("tool_result"),
            generation_id=data.get("generation_id"),
        )


@dataclass
class Memory:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "sarthak"
    category: MemoryCategory = MemoryCategory.PREFERENCE
    content: str = ""
    source: str = "user_explicit"  # "user_explicit" | "inferred" | "system"
    importance: float = 0.5  # 0.0 to 1.0
    confidence: float = 1.0  # 0.0 to 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category.value if isinstance(self.category, MemoryCategory) else self.category,
            "content": self.content,
            "source": self.source,
            "importance": self.importance,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        cat_val = data.get("category", MemoryCategory.PREFERENCE.value)
        try:
            cat = MemoryCategory(cat_val)
        except ValueError:
            cat = MemoryCategory.PREFERENCE

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", "sarthak"),
            category=cat,
            content=data.get("content", ""),
            source=data.get("source", "user_explicit"),
            importance=float(data.get("importance", 0.5)),
            confidence=float(data.get("confidence", 1.0)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            last_accessed_at=float(data.get("last_accessed_at", time.time())),
            access_count=int(data.get("access_count", 0)),
            metadata=data.get("metadata", {}),
        )
