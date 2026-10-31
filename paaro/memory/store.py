"""
SQLite Persistent Store for Paaro Memory and Conversation Sessions (Step 6).
Thread-safe, local, and resilient.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from .models import ConversationTurn, Memory, MemoryCategory, Session, TurnStatus

logger = logging.getLogger("paaro.memory.store")


class SQLiteMemoryStore:
    """
    Thread-safe SQLite storage engine for conversation sessions and persistent memories.
    """

    def __init__(self, db_path: str = "data/paaro_memory.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        
        # Ensure parent directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception as e:
                logger.warning("Could not create database directory '%s': %s", db_dir, e)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Sessions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        metadata TEXT
                    )
                """)

                # 2. Conversation Turns table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        status TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        tool_action TEXT,
                        tool_result TEXT,
                        generation_id TEXT,
                        FOREIGN KEY (session_id) REFERENCES sessions(id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_turns_session_time 
                    ON conversation_turns (session_id, timestamp)
                """)

                # 3. Long-term Memories table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source TEXT NOT NULL,
                        importance REAL NOT NULL,
                        confidence REAL NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        last_accessed_at REAL NOT NULL,
                        access_count INTEGER NOT NULL,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_user_cat 
                    ON memories (user_id, category)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memories_user_content 
                    ON memories (user_id, content)
                """)
                conn.commit()

    # -------------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------------

    def save_session(self, session: Session) -> Session:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (id, user_id, created_at, updated_at, metadata)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        metadata = excluded.metadata
                    """,
                    (
                        session.id,
                        session.user_id,
                        session.created_at,
                        session.updated_at,
                        json.dumps(session.metadata),
                    ),
                )
                conn.commit()
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
                row = cursor.fetchone()
                if row:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    return Session(
                        id=row["id"],
                        user_id=row["user_id"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        metadata=meta,
                    )
        return None

    def list_sessions(self, user_id: str, limit: int = 10) -> List[Session]:
        sessions = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                    (user_id, limit),
                )
                for row in cursor.fetchall():
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    sessions.append(
                        Session(
                            id=row["id"],
                            user_id=row["user_id"],
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                            metadata=meta,
                        )
                    )
        return sessions

    # -------------------------------------------------------------------------
    # Conversation Turns
    # -------------------------------------------------------------------------

    def save_turn(self, turn: ConversationTurn) -> ConversationTurn:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO conversation_turns (
                        id, session_id, role, content, status, timestamp, 
                        tool_action, tool_result, generation_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        content = excluded.content,
                        status = excluded.status,
                        tool_action = excluded.tool_action,
                        tool_result = excluded.tool_result,
                        generation_id = excluded.generation_id
                    """,
                    (
                        turn.id,
                        turn.session_id,
                        turn.role,
                        turn.content,
                        turn.status.value if isinstance(turn.status, TurnStatus) else turn.status,
                        turn.timestamp,
                        json.dumps(turn.tool_action) if turn.tool_action else None,
                        json.dumps(turn.tool_result) if turn.tool_result else None,
                        turn.generation_id,
                    ),
                )
                conn.commit()
        return turn

    def get_session_turns(
        self,
        session_id: str,
        limit: int = 20,
        include_interrupted: bool = True,
    ) -> List[ConversationTurn]:
        turns = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if include_interrupted:
                    cursor.execute(
                        "SELECT * FROM conversation_turns WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                        (session_id, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM conversation_turns 
                        WHERE session_id = ? AND status = 'completed' 
                        ORDER BY timestamp ASC LIMIT ?
                        """,
                        (session_id, limit),
                    )

                for row in cursor.fetchall():
                    tool_act = json.loads(row["tool_action"]) if row["tool_action"] else None
                    tool_res = json.loads(row["tool_result"]) if row["tool_result"] else None
                    turns.append(
                        ConversationTurn(
                            id=row["id"],
                            session_id=row["session_id"],
                            role=row["role"],
                            content=row["content"],
                            status=TurnStatus(row["status"]),
                            timestamp=row["timestamp"],
                            tool_action=tool_act,
                            tool_result=tool_res,
                            generation_id=row["generation_id"],
                        )
                    )
        return turns

    def mark_turn_status(self, turn_id: str, status: TurnStatus) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE conversation_turns SET status = ? WHERE id = ?",
                    (status.value if isinstance(status, TurnStatus) else status, turn_id),
                )
                conn.commit()
                return cursor.rowcount > 0

    # -------------------------------------------------------------------------
    # Memories
    # -------------------------------------------------------------------------

    def save_memory(self, memory: Memory) -> Memory:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, category, content, source, importance, 
                        confidence, created_at, updated_at, last_accessed_at, 
                        access_count, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        category = excluded.category,
                        content = excluded.content,
                        source = excluded.source,
                        importance = excluded.importance,
                        confidence = excluded.confidence,
                        updated_at = excluded.updated_at,
                        last_accessed_at = excluded.last_accessed_at,
                        access_count = excluded.access_count,
                        metadata = excluded.metadata
                    """,
                    (
                        memory.id,
                        memory.user_id,
                        memory.category.value if isinstance(memory.category, MemoryCategory) else memory.category,
                        memory.content,
                        memory.source,
                        memory.importance,
                        memory.confidence,
                        memory.created_at,
                        memory.updated_at,
                        memory.last_accessed_at,
                        memory.access_count,
                        json.dumps(memory.metadata),
                    ),
                )
                conn.commit()
        return memory

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
                row = cursor.fetchone()
                if row:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    return Memory(
                        id=row["id"],
                        user_id=row["user_id"],
                        category=MemoryCategory(row["category"]),
                        content=row["content"],
                        source=row["source"],
                        importance=row["importance"],
                        confidence=row["confidence"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        last_accessed_at=row["last_accessed_at"],
                        access_count=row["access_count"],
                        metadata=meta,
                    )
        return None

    def find_duplicate_memory(
        self,
        user_id: str,
        category: MemoryCategory,
        content: str,
    ) -> Optional[Memory]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cat_val = category.value if isinstance(category, MemoryCategory) else category
                cursor.execute(
                    """
                    SELECT * FROM memories 
                    WHERE user_id = ? AND category = ? AND LOWER(TRIM(content)) = LOWER(TRIM(?))
                    LIMIT 1
                    """,
                    (user_id, cat_val, content),
                )
                row = cursor.fetchone()
                if row:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    return Memory(
                        id=row["id"],
                        user_id=row["user_id"],
                        category=MemoryCategory(row["category"]),
                        content=row["content"],
                        source=row["source"],
                        importance=row["importance"],
                        confidence=row["confidence"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        last_accessed_at=row["last_accessed_at"],
                        access_count=row["access_count"],
                        metadata=meta,
                    )
        return None

    def list_memories(
        self,
        user_id: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 50,
    ) -> List[Memory]:
        memories = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if category:
                    cat_val = category.value if isinstance(category, MemoryCategory) else category
                    cursor.execute(
                        """
                        SELECT * FROM memories 
                        WHERE user_id = ? AND category = ? 
                        ORDER BY importance DESC, updated_at DESC LIMIT ?
                        """,
                        (user_id, cat_val, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM memories 
                        WHERE user_id = ? 
                        ORDER BY importance DESC, updated_at DESC LIMIT ?
                        """,
                        (user_id, limit),
                    )

                for row in cursor.fetchall():
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    memories.append(
                        Memory(
                            id=row["id"],
                            user_id=row["user_id"],
                            category=MemoryCategory(row["category"]),
                            content=row["content"],
                            source=row["source"],
                            importance=row["importance"],
                            confidence=row["confidence"],
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                            last_accessed_at=row["last_accessed_at"],
                            access_count=row["access_count"],
                            metadata=meta,
                        )
                    )
        return memories

    def delete_memory(self, memory_id: str) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                conn.commit()
                return cursor.rowcount > 0

    def touch_memory(self, memory_id: str) -> None:
        with self._lock:
            with self._get_connection() as conn:
                now = time.time()
                conn.execute(
                    """
                    UPDATE memories 
                    SET last_accessed_at = ?, access_count = access_count + 1 
                    WHERE id = ?
                    """,
                    (now, memory_id),
                )
                conn.commit()

    def close(self) -> None:
        """Close any lingering resources (connections are per-call and thread-safe)."""
        pass

