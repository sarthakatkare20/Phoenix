"""
Bounded Proactive Event Queue with Priority and TTL Expiry (Step 7).
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .events import EventSeverity, ProactiveEvent

logger = logging.getLogger("paaro.proactive.queue")


class ProactiveEventQueue:
    """
    Thread-safe bounded priority queue for deferred proactive events.
    Prioritizes higher severity and drops expired or duplicate items.
    """

    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self._items: List[ProactiveEvent] = []
        self._lock = threading.Lock()

    def _cleanup_expired_locked(self, now: float) -> int:
        initial_count = len(self._items)
        self._items = [ev for ev in self._items if not ev.is_expired(now)]
        removed = initial_count - len(self._items)
        if removed > 0:
            logger.debug("Purged %d expired proactive events from queue", removed)
        return removed

    def push(self, event: ProactiveEvent) -> bool:
        """
        Push an event into the queue.
        Returns True if enqueued, False if dropped or duplicate.
        """
        with self._lock:
            now = time.time()
            self._cleanup_expired_locked(now)

            if event.is_expired(now):
                logger.debug("Event %s is already expired; dropping from queue", event.id)
                return False

            # Check duplicate fingerprint in queue
            fp = event.fingerprint()
            for existing in self._items:
                if existing.fingerprint() == fp:
                    logger.debug("Duplicate event fingerprint '%s' in queue; ignoring push", fp[:8])
                    return False

            # Insert maintaining priority order (Higher severity first, then older timestamp first)
            # Rank score: severity level (higher = better), negative timestamp (smaller/older = better)
            self._items.append(event)
            self._items.sort(
                key=lambda ev: (
                    ev.severity.level if isinstance(ev.severity, EventSeverity) else 1,
                    -ev.timestamp,
                ),
                reverse=True,
            )

            # Enforce max bound: drop lowest priority items from the end
            while len(self._items) > self.max_size:
                dropped = self._items.pop()
                logger.warning(
                    "Proactive queue full (%d); dropped lowest priority event '%s' (%s)",
                    self.max_size,
                    dropped.event_type,
                    dropped.severity.value,
                )

            return True

    def pop(self) -> Optional[ProactiveEvent]:
        """Pop and return the highest priority non-expired event."""
        with self._lock:
            now = time.time()
            self._cleanup_expired_locked(now)

            if not self._items:
                return None
            return self._items.pop(0)

    def peek(self) -> Optional[ProactiveEvent]:
        """Peek the highest priority non-expired event without removing."""
        with self._lock:
            now = time.time()
            self._cleanup_expired_locked(now)

            if not self._items:
                return None
            return self._items[0]

    def purge_expired(self) -> int:
        """Explicitly purge expired items."""
        with self._lock:
            return self._cleanup_expired_locked(time.time())

    def clear(self) -> None:
        """Clear all queued events."""
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            self._cleanup_expired_locked(time.time())
            return len(self._items)

    def to_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._cleanup_expired_locked(time.time())
            return [ev.to_dict() for ev in self._items]
