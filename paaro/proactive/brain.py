"""
Proactive Brain for Paaro (Step 7).
Handles contextual proactive reasoning, Tool Gateway policy enforcement, and TTS vocalization.
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from .events import (
    ProactiveDecision,
    ProactiveDecisionType,
    ProactiveEvent,
    UserActivityState,
)
from .evaluator import EventEvaluator
from ..security import SecurityContext, security_context
from ..tool_gateway import PolicyDecision, ToolGateway, tool_gateway
from ..streaming_llm import StreamingLLM
from ..kokoro_tts import StreamingTTS
from ..memory.service import MemoryService

logger = logging.getLogger("paaro.proactive.brain")


class ProactiveBrain:
    """
    Coordinates evaluation, contextual reasoning, Policy Engine enforcement,
    and streaming speech synthesis for proactive actions.
    """

    def __init__(
        self,
        evaluator: Optional[EventEvaluator] = None,
        llm: Optional[StreamingLLM] = None,
        tts: Optional[StreamingTTS] = None,
        gateway: Optional[ToolGateway] = None,
        security: Optional[SecurityContext] = None,
        memory_service: Optional[MemoryService] = None,
        auto_speech: bool = True,
    ):
        self.evaluator = evaluator or EventEvaluator()
        self.llm = llm
        self.tts = tts
        self.gateway = gateway or tool_gateway
        self.security = security or security_context
        self.memory_service = memory_service
        self.auto_speech = auto_speech

        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._active_proactive_gen_id: Optional[str] = None

    def add_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _broadcast(self, event: Dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception as e:
                logger.error("Error in Proactive listener callback: %s", e)

    async def process_event(
        self,
        event: ProactiveEvent,
        user_state: UserActivityState = UserActivityState.IDLE,
        session_id: Optional[str] = None,
    ) -> ProactiveDecision:
        """
        Main entry point to evaluate and process an incoming proactive event.
        """
        t0 = time.time()
        
        # Emit raw event received
        self._broadcast({
            "type": "proactive_event",
            "event": event.to_dict(),
            "user_state": user_state.value,
            "timestamp": int(t0 * 1000),
        })

        # 1. Deterministic Evaluation
        decision = self.evaluator.evaluate(event, user_state=user_state)

        # 2. Handle IGNORE / DEFER outcomes
        if decision.decision == ProactiveDecisionType.IGNORE:
            self._broadcast({
                "type": "proactive_ignored",
                "event_id": event.id,
                "event_type": event.event_type,
                "reason": decision.reason,
                "timestamp": int(time.time() * 1000),
            })
            return decision

        if decision.decision == ProactiveDecisionType.DEFER:
            self._broadcast({
                "type": "proactive_deferred",
                "event_id": event.id,
                "event_type": event.event_type,
                "reason": decision.reason,
                "timestamp": int(time.time() * 1000),
            })
            return decision

        # 3. LLM Reasoning (if required for complex non-templated events)
        if decision.requires_llm and self.llm and not self.security.is_emergency_stopped:
            decision = await self._reason_with_llm(event, decision, session_id=session_id)

        # 4. Tool Execution Check (Strict Tool Gateway / Policy Engine boundary)
        tool_result = None
        if decision.decision == ProactiveDecisionType.ACT and decision.tool_name:
            tool_res = self.gateway.execute_allowed(decision.tool_name, decision.tool_args or {})
            tool_result = tool_res
            logger.info(
                "[PROACTIVE] Executed tool '%s' via Tool Gateway: %s",
                decision.tool_name,
                tool_res.get("status"),
            )

        # Broadcast final decision
        self._broadcast({
            "type": "proactive_decision",
            "decision": decision.to_dict(),
            "tool_result": tool_result,
            "eval_latency_ms": round((time.time() - t0) * 1000.0, 2),
            "timestamp": int(time.time() * 1000),
        })

        # 5. Vocalize through Streaming TTS if enabled and text available
        if (
            self.auto_speech
            and decision.should_speak
            and decision.message
            and self.tts
            and not self.security.is_emergency_stopped
        ):
            await self._vocalize_message(decision.message)

        return decision

    async def _reason_with_llm(
        self,
        event: ProactiveEvent,
        base_decision: ProactiveDecision,
        session_id: Optional[str] = None,
    ) -> ProactiveDecision:
        """
        Use StreamingLLM to synthesize a concise proactive response message.
        """
        prompt = (
            f"SYSTEM EVENT OCCURRED:\n"
            f"Type: {event.event_type}\n"
            f"Source: {event.source}\n"
            f"Severity: {event.severity.value}\n"
            f"Details: {json.dumps(event.data)}\n\n"
            "As Paaro, formulate a natural 1-sentence proactive message for Sarthak. "
            "If an action should be proposed, clearly ask. Keep it under 25 words."
        )

        try:
            full_text = ""
            async for chunk_ev in self.llm.stream_response(prompt, session_id=session_id):
                if isinstance(chunk_ev, dict) and chunk_ev.get("status") == "delta":
                    full_text += chunk_ev.get("text", "")
                elif isinstance(chunk_ev, str):
                    full_text += chunk_ev

            clean_msg = full_text.strip()
            if clean_msg:
                base_decision.message = clean_msg
                base_decision.should_speak = True
        except Exception as e:
            logger.error("Error during proactive LLM reasoning: %s", e)
            # Fallback to base deterministic summary
            if not base_decision.message:
                base_decision.message = f"Notice: {event.event_type} event occurred."

        return base_decision

    async def _vocalize_message(self, message: str) -> None:
        """
        Send proactive message to Streaming TTS pipeline with interruptible generation ID.
        """
        if not self.tts or self.security.is_emergency_stopped:
            return

        gen_id = f"proactive-{uuid.uuid4()}"
        self._active_proactive_gen_id = gen_id

        self._broadcast({
            "type": "proactive_message",
            "message": message,
            "generation_id": gen_id,
            "timestamp": int(time.time() * 1000),
        })

        self.tts.on_llm_start(generation_id=gen_id)
        self.tts.feed_text_delta(message, generation_id=gen_id)
        self.tts.flush_text(generation_id=gen_id)
