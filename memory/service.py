"""
Memory Service implementing business logic, session orchestration, deduplication, and natural memory commands (Step 6).
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import ConversationTurn, Memory, MemoryCategory, Session, TurnStatus
from .retrieval import MemoryRetriever
from .store import SQLiteMemoryStore

logger = logging.getLogger("paaro.memory.service")


class MemoryService:
    """
    Core memory manager handling sessions, turns, long-term memory lifecycle,
    deduplication, and explicit user memory commands.
    """

    def __init__(
        self,
        store: Optional[SQLiteMemoryStore] = None,
        default_user_id: str = "sarthak",
    ):
        self.store = store or SQLiteMemoryStore()
        self.default_user_id = default_user_id
        self._active_session: Optional[Session] = None

    # -------------------------------------------------------------------------
    # Session & Turn Management
    # -------------------------------------------------------------------------

    def get_or_create_active_session(self, user_id: Optional[str] = None) -> Session:
        uid = user_id or self.default_user_id
        if self._active_session is None or self._active_session.user_id != uid:
            sessions = self.store.list_sessions(user_id=uid, limit=1)
            if sessions:
                self._active_session = sessions[0]
            else:
                session = Session(user_id=uid)
                self.store.save_session(session)
                self._active_session = session
        return self._active_session

    def create_new_session(self, user_id: Optional[str] = None) -> Session:
        uid = user_id or self.default_user_id
        session = Session(user_id=uid)
        self.store.save_session(session)
        self._active_session = session
        return session

    def record_user_turn(
        self,
        session_id: str,
        content: str,
        generation_id: Optional[str] = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            session_id=session_id,
            role="user",
            content=content.strip(),
            status=TurnStatus.COMPLETED,
            timestamp=time.time(),
            generation_id=generation_id,
        )
        self.store.save_turn(turn)
        if self._active_session and self._active_session.id == session_id:
            self._active_session.updated_at = turn.timestamp
            self.store.save_session(self._active_session)
        return turn

    def record_assistant_turn(
        self,
        session_id: str,
        content: str,
        status: TurnStatus = TurnStatus.COMPLETED,
        tool_action: Optional[Dict[str, Any]] = None,
        tool_result: Optional[Dict[str, Any]] = None,
        generation_id: Optional[str] = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            session_id=session_id,
            role="assistant",
            content=content.strip(),
            status=status,
            timestamp=time.time(),
            tool_action=tool_action,
            tool_result=tool_result,
            generation_id=generation_id,
        )
        self.store.save_turn(turn)
        if self._active_session and self._active_session.id == session_id:
            self._active_session.updated_at = turn.timestamp
            self.store.save_session(self._active_session)
        return turn

    def mark_turn_interrupted(self, turn_id: str) -> bool:
        return self.store.mark_turn_status(turn_id, TurnStatus.INTERRUPTED)

    def get_recent_turns(
        self,
        session_id: str,
        limit: int = 10,
        include_interrupted: bool = False,
    ) -> List[ConversationTurn]:
        return self.store.get_session_turns(
            session_id=session_id,
            limit=limit,
            include_interrupted=include_interrupted,
        )

    # -------------------------------------------------------------------------
    # Long-Term Memory CRUD & Deduplication
    # -------------------------------------------------------------------------

    def store_memory(
        self,
        content: str,
        category: MemoryCategory = MemoryCategory.PREFERENCE,
        user_id: Optional[str] = None,
        source: str = "user_explicit",
        importance: float = 0.5,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Memory, bool]:
        """
        Store a new memory item or update existing if deduplicated.
        Returns (Memory, is_new: bool).
        """
        uid = user_id or self.default_user_id
        clean_content = content.strip()

        # Check for duplicate
        existing = self.store.find_duplicate_memory(uid, category, clean_content)
        if existing:
            # Touch and update existing memory
            existing.access_count += 1
            existing.last_accessed_at = time.time()
            existing.updated_at = time.time()
            existing.importance = max(existing.importance, importance)
            existing.confidence = max(existing.confidence, confidence)
            if metadata:
                existing.metadata.update(metadata)
            self.store.save_memory(existing)
            logger.info("Deduplicated memory: updated existing memory id=%s", existing.id)
            return existing, False

        # Create new memory
        mem = Memory(
            user_id=uid,
            category=category,
            content=clean_content,
            source=source,
            importance=importance,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.store.save_memory(mem)
        logger.info("Stored new memory id=%s in category=%s", mem.id, category.value)
        return mem, True

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        return self.store.get_memory(memory_id)

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[MemoryCategory] = None,
        importance: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> Optional[Memory]:
        mem = self.store.get_memory(memory_id)
        if not mem:
            return None

        if content is not None:
            mem.content = content.strip()
        if category is not None:
            mem.category = category
        if importance is not None:
            mem.importance = max(0.0, min(1.0, importance))
        if confidence is not None:
            mem.confidence = max(0.0, min(1.0, confidence))

        mem.updated_at = time.time()
        self.store.save_memory(mem)
        return mem

    def delete_memory(self, memory_id: str) -> bool:
        return self.store.delete_memory(memory_id)

    def list_all_memories(
        self,
        user_id: Optional[str] = None,
        category: Optional[MemoryCategory] = None,
    ) -> List[Memory]:
        uid = user_id or self.default_user_id
        return self.store.list_memories(user_id=uid, category=category)

    def search_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.15,
    ) -> List[Tuple[Memory, float]]:
        uid = user_id or self.default_user_id
        all_memories = self.store.list_memories(user_id=uid, limit=100)
        results = MemoryRetriever.retrieve_relevant(
            memories=all_memories,
            query=query,
            top_k=top_k,
            min_score=min_score,
        )
        # Touch retrieved memories
        for mem, _ in results:
            self.store.touch_memory(mem.id)
        return results

    # -------------------------------------------------------------------------
    # Natural Memory Commands & Intent Parsing
    # -------------------------------------------------------------------------

    def handle_explicit_memory_command(
        self,
        text: str,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Inspect user text for explicit memory operations like:
        - "Remember that [fact]"
        - "What do you remember about me?"
        - "Forget [preference]"
        Returns a formatted response string if a memory command was handled, else None.
        """
        uid = user_id or self.default_user_id
        clean = text.strip()
        lower = clean.lower()

        # 1. "What do you remember about me?" / "What are my preferences?"
        if any(
            phrase in lower
            for phrase in [
                "what do you remember about me",
                "what do you remember",
                "what are my preferences",
                "show my memories",
                "list memories",
            ]
        ):
            memories = self.list_all_memories(user_id=uid)
            if not memories:
                return "I don't have any persistent memories saved about you yet."
            
            lines = ["Here is what I remember about you:"]
            for m in memories[:8]:
                lines.append(f"- [{m.category.value.capitalize()}] {m.content}")
            return "\n".join(lines)

        # 2. "Forget [fact / preference / everything]"
        match_forget = re.match(r"(?:please\s+)?forget\s+(?:that\s+)?(.+)", clean, re.IGNORECASE)
        if match_forget:
            target = match_forget.group(1).strip().rstrip(".!?")
            if target in ("all", "everything", "all memories"):
                all_m = self.list_all_memories(user_id=uid)
                for m in all_m:
                    self.delete_memory(m.id)
                return "I have cleared all your persistent memories."

            # Search for best matching memory to delete
            results = self.search_memories(target, user_id=uid, top_k=1, min_score=0.1)
            if results:
                target_mem, _ = results[0]
                self.delete_memory(target_mem.id)
                return f"I have forgotten: '{target_mem.content}'."
            else:
                return f"I couldn't find any memory matching '{target}' to forget."

        # 3. "Remember that [fact/preference]" / "Remember my name is [name]" / "Remember [fact]"
        match_remember = re.match(
            r"(?:please\s+)?remember\s+(?:that\s+)?(.+)", clean, re.IGNORECASE
        )
        if match_remember:
            memory_fact = match_remember.group(1).strip().rstrip(".!?")
            if memory_fact:
                # Classify category
                fact_lower = memory_fact.lower()
                if any(w in fact_lower for w in ["project", "building", "working on", "developing", "codebase"]):
                    category = MemoryCategory.PROJECT
                elif any(w in fact_lower for w in ["my name is", "call me"]) or (any(w in fact_lower for w in ["i am ", "i'm "]) and not any(w in fact_lower for w in ["building", "working", "using", "trying"])):
                    category = MemoryCategory.PROFILE
                elif any(w in fact_lower for w in ["routine", "every day", "daily", "usually at"]):
                    category = MemoryCategory.ROUTINE
                else:
                    category = MemoryCategory.PREFERENCE

                mem, is_new = self.store_memory(
                    content=memory_fact,
                    category=category,
                    user_id=uid,
                    source="user_explicit",
                    importance=0.8,
                    confidence=1.0,
                )
                action = "remembered" if is_new else "updated"
                return f"I have {action}: '{memory_fact}'."

        return None

