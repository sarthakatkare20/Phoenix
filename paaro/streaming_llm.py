"""
Streaming LLM Engine for Paaro using Ollama.
Streams progressive response tokens, measures first-token latencies, and routes tool calls through ToolGateway.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
import httpx

from .config import PaaroSettings, settings
from .security import SecurityContext, security_context
from .tool_gateway import PolicyDecision, ToolGateway, tool_gateway
from .memory.service import MemoryService
from .memory.context import ContextBuilder
from .memory.models import TurnStatus

logger = logging.getLogger("paaro.llm")


class StreamingLLM:
    """
    Streaming LLM coordinator communicating with Ollama `/api/chat`.
    Provides low-latency token streaming, context assembly, multi-turn memory integration,
    metrics tracking, and security-governed tool routing.
    """

    def __init__(
        self,
        config: Optional[PaaroSettings] = None,
        security: Optional[SecurityContext] = None,
        gateway: Optional[ToolGateway] = None,
        memory_service: Optional[MemoryService] = None,
        context_builder: Optional[ContextBuilder] = None,
    ):
        self.config = config or settings
        self.security = security or security_context
        self.gateway = gateway or tool_gateway
        self.memory_service = memory_service
        self.context_builder = context_builder or (
            ContextBuilder(
                memory_service=self.memory_service,
                max_turns=self.config.CONVERSATION_MAX_TURNS,
                max_tokens=self.config.CONTEXT_MAX_TOKENS,
                max_memories=self.config.MEMORY_MAX_RESULTS,
            )
            if self.memory_service
            else None
        )

        self._messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.config.LLM_SYSTEM_PROMPT}
        ]
        self._current_cancel_event = asyncio.Event()
        self._current_generation_id: str = ""
        self._is_generating = False
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._listeners_lock = asyncio.Lock()

    @property
    def current_generation_id(self) -> str:
        return self._current_generation_id

    @property
    def messages(self) -> List[Dict[str, str]]:
        return list(self._messages)

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
                logger.error("Error in LLM listener callback: %s", e)

    def cancel(self) -> str:
        """Cancel any active LLM generation. Returns the cancelled generation_id."""
        cancelled_id = self._current_generation_id
        if self._is_generating or cancelled_id:
            logger.info("Cancelling active LLM generation '%s'...", cancelled_id)
            self._current_cancel_event.set()
            self._is_generating = False
            self._current_generation_id = ""
            self._broadcast({
                "type": "llm",
                "status": "cancelled",
                "generation_id": cancelled_id,
                "timestamp": int(time.time() * 1000),
            })
        return cancelled_id

    def clear_history(self) -> None:
        """Reset conversation history back to system prompt."""
        self._messages = [{"role": "system", "content": self.config.LLM_SYSTEM_PROMPT}]

    def _extract_and_strip_action(self, text: str) -> tuple[str, Optional[Dict[str, Any]]]:
        """
        Extract [ACTION: {...}] or [OPEN: ...] tags from response text and strip them from spoken text.
        """
        action_match = re.search(r"\[ACTION:\s*({[^\]]+})\]", text, re.IGNORECASE)
        if action_match:
            try:
                action_data = json.loads(action_match.group(1))
                clean_text = re.sub(r"\[ACTION:\s*{[^\]]+}\]", "", text, flags=re.IGNORECASE).strip()
                return clean_text, action_data
            except json.JSONDecodeError:
                pass

        open_match = re.search(r"\[OPEN:\s*([^\]]+)\]", text, re.IGNORECASE)
        if open_match:
            target = open_match.group(1).strip()
            clean_text = re.sub(r"\[OPEN:\s*[^\]]+\]", "", text, flags=re.IGNORECASE).strip()
            return clean_text, {"type": "open_app", "target": target}

        return text, None

    async def stream_response(
        self,
        user_prompt: str,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream progressive LLM deltas from Ollama and yield structured events.
        Integrates with MemoryService for multi-turn context and persistence.
        """
        if self.security.is_emergency_stopped:
            logger.warning("LLM request rejected: Emergency stop is active.")
            err_event = {
                "type": "llm",
                "status": "error",
                "message": "Cannot generate: Emergency stop is active.",
                "timestamp": int(time.time() * 1000),
            }
            self._broadcast(err_event)
            yield err_event
            return

        self._current_cancel_event.clear()
        generation_id = str(uuid.uuid4())
        self._current_generation_id = generation_id
        self._is_generating = True
        t_request_start = time.time()

        # 1. Check for explicit memory commands ("Remember that...", "What do you remember about me?", "Forget...")
        if self.memory_service:
            try:
                memory_reply = self.memory_service.handle_explicit_memory_command(user_prompt)
                if memory_reply:
                    start_event = {
                        "type": "llm",
                        "status": "start",
                        "model": self.config.LLM_MODEL,
                        "generation_id": generation_id,
                        "timestamp": int(t_request_start * 1000),
                    }
                    self._broadcast(start_event)
                    yield start_event

                    delta_event = {
                        "type": "llm",
                        "status": "delta",
                        "text": memory_reply,
                        "generation_id": generation_id,
                        "timestamp": int(time.time() * 1000),
                    }
                    self._broadcast(delta_event)
                    yield delta_event

                    # Record turns
                    if session_id:
                        try:
                            self.memory_service.record_user_turn(session_id, user_prompt, generation_id=generation_id)
                            self.memory_service.record_assistant_turn(
                                session_id, memory_reply, status=TurnStatus.COMPLETED, generation_id=generation_id
                            )
                        except Exception as e:
                            logger.error("Error recording memory command turn: %s", e)

                    t_end = time.time()
                    self._is_generating = False
                    done_event = {
                        "type": "llm",
                        "status": "done",
                        "text": memory_reply,
                        "generation_id": generation_id,
                        "first_token_latency_ms": 1.0,
                        "generation_duration_ms": 1.0,
                        "total_response_time_ms": round((t_end - t_request_start) * 1000.0, 1),
                        "total_tokens": len(memory_reply.split()),
                        "tokens_per_sec": 100.0,
                        "tool_action": None,
                        "tool_result": None,
                        "timestamp": int(t_end * 1000),
                    }
                    self._broadcast(done_event)
                    yield done_event
                    return
            except Exception as e:
                logger.error("Error evaluating explicit memory command: %s", e)

        # 2. Assemble Context (System + Memories + Recent Turns + User Prompt)
        context_metrics = {}
        if self.context_builder and self.config.MEMORY_ENABLED:
            try:
                chat_messages, context_metrics = self.context_builder.assemble_context(
                    user_prompt=user_prompt,
                    system_prompt=self.config.LLM_SYSTEM_PROMPT,
                    session_id=session_id,
                    user_id=self.memory_service.default_user_id if self.memory_service else self.config.DEFAULT_USER_ID,
                )
            except Exception as e:
                logger.error("Error building context: %s. Fallback to basic history.", e)
                self._messages.append({"role": "user", "content": user_prompt})
                chat_messages = list(self._messages)
        else:
            self._messages.append({"role": "user", "content": user_prompt})
            if len(self._messages) > 21:
                self._messages = [self._messages[0]] + self._messages[-20:]
            chat_messages = list(self._messages)

        start_event = {
            "type": "llm",
            "status": "start",
            "model": self.config.LLM_MODEL,
            "generation_id": generation_id,
            "context_metrics": context_metrics,
            "timestamp": int(t_request_start * 1000),
        }
        self._broadcast(start_event)
        yield start_event

        full_raw_text = ""
        spoken_text_accumulator = ""
        first_token_time: Optional[float] = None
        total_tokens = 0

        buffer = ""
        last_flush_time = time.time()
        buffer_flush_sec = self.config.LLM_STREAM_BUFFER_MS / 1000.0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "model": self.config.LLM_MODEL,
                    "messages": chat_messages,
                    "stream": True,
                    "options": {
                        "temperature": self.config.LLM_TEMPERATURE,
                        "num_predict": self.config.LLM_MAX_TOKENS,
                    },
                }

                async with client.stream(
                    "POST",
                    f"{self.config.OLLAMA_URL}/api/chat",
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        err_msg = f"Ollama error ({response.status_code})"
                        raise RuntimeError(err_msg)

                    async for line in response.aiter_lines():
                        if (
                            self._current_cancel_event.is_set()
                            or self.security.is_emergency_stopped
                            or self._current_generation_id != generation_id
                        ):
                            logger.info("LLM generation '%s' aborted by cancellation event.", generation_id)
                            break

                        if not line.strip():
                            continue

                        try:
                            chunk_json = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        token = chunk_json.get("message", {}).get("content", "")
                        if token:
                            now = time.time()
                            if first_token_time is None:
                                first_token_time = now

                            total_tokens += 1
                            full_raw_text += token
                            buffer += token

                            # Check if delta buffer should be flushed
                            time_since_flush = now - last_flush_time
                            if time_since_flush >= buffer_flush_sec or "\n" in buffer or any(p in buffer for p in ".!?"):
                                # Ensure we don't leak partial [ACTION: tags in spoken stream
                                if "[" in buffer and "]" not in buffer:
                                    # Hold buffer until tag closes or finishes
                                    continue

                                clean_delta, _ = self._extract_and_strip_action(buffer)
                                if clean_delta:
                                    spoken_text_accumulator += clean_delta
                                    delta_event = {
                                        "type": "llm",
                                        "status": "delta",
                                        "text": clean_delta,
                                        "generation_id": generation_id,
                                        "timestamp": int(now * 1000),
                                    }
                                    self._broadcast(delta_event)
                                    yield delta_event

                                buffer = ""
                                last_flush_time = now

                    # Flush any remaining buffer
                    if (
                        buffer
                        and not self._current_cancel_event.is_set()
                        and self._current_generation_id == generation_id
                    ):
                        clean_delta, _ = self._extract_and_strip_action(buffer)
                        if clean_delta:
                            spoken_text_accumulator += clean_delta
                            delta_event = {
                                "type": "llm",
                                "status": "delta",
                                "text": clean_delta,
                                "generation_id": generation_id,
                                "timestamp": int(time.time() * 1000),
                            }
                            self._broadcast(delta_event)
                            yield delta_event

        except Exception as e:
            logger.error("LLM streaming error: %s", e)
            self._is_generating = False
            err_event = {
                "type": "llm",
                "status": "error",
                "message": f"LLM generation failed: {str(e)}",
                "timestamp": int(time.time() * 1000),
            }
            self._broadcast(err_event)
            yield err_event
            return

        t_end = time.time()
        self._is_generating = False

        if self._current_cancel_event.is_set() or self.security.is_emergency_stopped:
            return

        # Check for tool call in completed response
        clean_final_text, tool_action = self._extract_and_strip_action(full_raw_text)
        if not clean_final_text and spoken_text_accumulator:
            clean_final_text = spoken_text_accumulator

        # Calculate latency and throughput metrics
        first_tok_ms = (first_token_time - t_request_start) * 1000.0 if first_token_time else 0.0
        gen_duration_ms = (t_end - first_token_time) * 1000.0 if first_token_time else 0.0
        total_time_ms = (t_end - t_request_start) * 1000.0
        tps = (total_tokens / (gen_duration_ms / 1000.0)) if gen_duration_ms > 0 else 0.0

        # Execute / Route tool call if detected
        tool_result = None
        if tool_action:
            tool_name = tool_action.get("type") or tool_action.get("name") or "unknown_tool"
            tool_args = {k: v for k, v in tool_action.items() if k not in ("type", "name")}

            decision = self.gateway.evaluate_tool_call(tool_name, tool_args)
            tool_event = {
                "type": "llm",
                "status": "tool_request",
                "tool": tool_name,
                "args": tool_args,
                "policy": decision.value,
                "generation_id": generation_id,
                "timestamp": int(time.time() * 1000),
            }
            self._broadcast(tool_event)
            yield tool_event

            if decision == PolicyDecision.ALLOW:
                tool_result = self.gateway.execute_allowed(tool_name, tool_args)
            elif decision == PolicyDecision.CONFIRM:
                tool_result = self.gateway.execute_allowed(tool_name, tool_args)  # Marks as pending confirmation
            elif decision == PolicyDecision.DENY:
                tool_result = {"status": "error", "error": f"Tool '{tool_name}' denied by security policy."}

        # Commit only the final assistant text to history
        self._messages.append({"role": "assistant", "content": clean_final_text})

        # Persist conversation turns to MemoryService
        if self.memory_service and session_id:
            try:
                self.memory_service.record_user_turn(session_id, user_prompt, generation_id=generation_id)
                self.memory_service.record_assistant_turn(
                    session_id=session_id,
                    content=clean_final_text,
                    status=TurnStatus.COMPLETED,
                    tool_action=tool_action,
                    tool_result=tool_result,
                    generation_id=generation_id,
                )
            except Exception as e:
                logger.error("Error saving turns to MemoryService: %s", e)

        done_event = {
            "type": "llm",
            "status": "done",
            "text": clean_final_text,
            "generation_id": generation_id,
            "first_token_latency_ms": round(first_tok_ms, 1),
            "generation_duration_ms": round(gen_duration_ms, 1),
            "total_response_time_ms": round(total_time_ms, 1),
            "total_tokens": total_tokens,
            "tokens_per_sec": round(tps, 1),
            "tool_action": tool_action,
            "tool_result": tool_result,
            "timestamp": int(t_end * 1000),
        }
        self._broadcast(done_event)
        yield done_event
