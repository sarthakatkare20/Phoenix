"""
Lightweight in-memory Event Bus for Paaro Proactive Architecture (Step 7).
Thread-safe, async-friendly, local publish-subscribe bus.
"""

import asyncio
import inspect
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set

from proactive.events import ProactiveEvent

logger = logging.getLogger("paaro.proactive.event_bus")


class EventBus:
    """
    Lightweight, thread-safe publish-subscribe event bus.
    Supports sync and async handler dispatch with event_type filtering.
    """

    def __init__(self, async_loop: Optional[asyncio.AbstractEventLoop] = None):
        self._async_loop = async_loop
        self._lock = threading.Lock()
        # Mapping: event_type -> List of (handler, filter_set)
        self._subscribers: List[tuple[Callable[[ProactiveEvent], Any], Optional[Set[str]]]] = []

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._async_loop = loop

    def subscribe(
        self,
        handler: Callable[[ProactiveEvent], Any],
        event_types: Optional[List[str]] = None,
    ) -> None:
        """
        Subscribe a callback handler to events.
        If event_types is specified, only events matching one of those types are delivered.
        """
        with self._lock:
            filter_set = set(event_types) if event_types else None
            # Prevent duplicate registration
            for h, _ in self._subscribers:
                if h == handler:
                    return
            self._subscribers.append((handler, filter_set))
            logger.debug("Subscribed handler %s with filters: %s", handler, filter_set)

    def unsubscribe(self, handler: Callable[[ProactiveEvent], Any]) -> None:
        """Unsubscribe an existing handler."""
        with self._lock:
            self._subscribers = [
                (h, f) for (h, f) in self._subscribers if h != handler
            ]
            logger.debug("Unsubscribed handler %s", handler)

    def publish(self, event: ProactiveEvent) -> None:
        """
        Publish an event to all matching subscribers.
        Dispatches synchronously to sync callables and schedules async coroutines.
        """
        subscribers_snapshot = []
        with self._lock:
            subscribers_snapshot = list(self._subscribers)

        for handler, filter_set in subscribers_snapshot:
            if filter_set is not None and event.event_type not in filter_set:
                continue

            try:
                if inspect.iscoroutinefunction(handler):
                    if self._async_loop and self._async_loop.is_running():
                        asyncio.run_coroutine_threadsafe(handler(event), self._async_loop)
                    else:
                        # Fallback for sync execution context if no running loop
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(handler(event))
                            else:
                                loop.run_until_complete(handler(event))
                        except Exception:
                            asyncio.run(handler(event))
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    "Error executing subscriber %s for event '%s': %s",
                    handler,
                    event.event_type,
                    e,
                    exc_info=True,
                )

    async def publish_async(self, event: ProactiveEvent) -> None:
        """Async variant of publish for use within active coroutines."""
        subscribers_snapshot = []
        with self._lock:
            subscribers_snapshot = list(self._subscribers)

        for handler, filter_set in subscribers_snapshot:
            if filter_set is not None and event.event_type not in filter_set:
                continue

            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    "Error executing async subscriber %s for event '%s': %s",
                    handler,
                    event.event_type,
                    e,
                    exc_info=True,
                )
