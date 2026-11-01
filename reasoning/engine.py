"""
Reasoning & Planning Engine for Paaro (Step 8).
Coordinates task classification, plan synthesis, validation, dependency execution,
dynamic replanning, verification, and conversational status vocalization.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from .models import ExecutionPlan, PlanStatus, PlanStep, StepResult, StepStatus, TaskComplexity, VerificationResult
from .classifier import TaskComplexityClassifier
from .planner import PlanGenerator, PlanValidator
from .executor import PlanExecutor
from .verifier import PlanVerifier
from .replanner import Replanner
from ..config import PaaroSettings, settings
from ..security import SecurityContext, security_context
from ..tool_gateway import PolicyDecision, ToolGateway, tool_gateway
from ..streaming_llm import StreamingLLM
from ..kokoro_tts import StreamingTTS
from ..memory.service import MemoryService
from ..memory.models import TurnStatus

logger = logging.getLogger("paaro.reasoning.engine")


class ReasoningEngine:
    """
    Central Reasoning and Planning Engine.
    Executes complex multi-step goals while bypassing simple/direct queries through the fast path.
    """

    def __init__(
        self,
        config: Optional[PaaroSettings] = None,
        llm: Optional[StreamingLLM] = None,
        tts: Optional[StreamingTTS] = None,
        gateway: Optional[ToolGateway] = None,
        security: Optional[SecurityContext] = None,
        memory_service: Optional[MemoryService] = None,
        classifier: Optional[TaskComplexityClassifier] = None,
        planner: Optional[PlanGenerator] = None,
        validator: Optional[PlanValidator] = None,
        executor: Optional[PlanExecutor] = None,
        verifier: Optional[PlanVerifier] = None,
        replanner: Optional[Replanner] = None,
    ):
        self.config = config or settings
        self.llm = llm
        self.tts = tts
        self.gateway = gateway or tool_gateway
        self.security = security or security_context
        self.memory_service = memory_service

        self.classifier = classifier or TaskComplexityClassifier(llm=self.llm)
        self.validator = validator or PlanValidator(max_steps=self.config.MAX_PLAN_STEPS, policy_engine=self.gateway.policy_engine)
        self.planner = planner or PlanGenerator(llm=self.llm, validator=self.validator, max_steps=self.config.MAX_PLAN_STEPS)
        self.executor = executor or PlanExecutor(gateway=self.gateway, security=self.security, max_retries_per_step=self.config.MAX_RETRIES_PER_STEP)
        self.verifier = verifier or PlanVerifier()
        self.replanner = replanner or Replanner(llm=self.llm, validator=self.validator, max_replans=self.config.MAX_REPLANS)

        self._active_plan: Optional[ExecutionPlan] = None
        self._current_cancel_event = asyncio.Event()
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

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
                logger.error("Error in reasoning listener: %s", e)

    @property
    def is_executing_plan(self) -> bool:
        return bool(
            (self._active_plan and self._active_plan.status == PlanStatus.RUNNING)
            or (self.executor.active_plan and self.executor.active_plan.status == PlanStatus.RUNNING)
        )

    def cancel_active_plan(self) -> Optional[str]:
        """Cancel any currently running plan."""
        cancelled_id = None
        self._current_cancel_event.set()
        if self._active_plan:
            cancelled_id = self._active_plan.id
            self._active_plan.status = PlanStatus.CANCELLED

        exec_id = self.executor.cancel()
        cancelled_id = cancelled_id or exec_id

        if cancelled_id:
            logger.info("[REASONING] Cancelling active plan '%s'", cancelled_id)
            self._broadcast({
                "type": "plan_cancelled",
                "plan_id": cancelled_id,
                "timestamp": int(time.time() * 1000),
            })
            return cancelled_id
        return None

    def get_active_plan(self) -> Optional[Dict[str, Any]]:
        return self._active_plan.to_dict() if self._active_plan else None

    async def generate_plan(
        self, goal: str, session_id: Optional[str] = None
    ) -> Optional[ExecutionPlan]:
        """Generate and validate an execution plan."""
        return await self.planner.generate(goal)

    async def execute_task(
        self, goal: str, session_id: Optional[str] = None
    ) -> Optional[ExecutionPlan]:
        """Generate and execute a task plan."""
        plan = await self.generate_plan(goal, session_id=session_id)
        if not plan:
            return None
        return await self.executor.execute_plan(plan, cancel_event=self._current_cancel_event)

    async def handle_request(
        self,
        user_prompt: str,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Main entry point for handling user requests.
        Returns None if request is DIRECT/SIMPLE (letting StreamingLLM fast-path handle it),
        or returns a structured dict result if handled by the Reasoning & Planning Engine.
        """
        if not self.config.REASONING_ENABLED:
            return None

        # 1. Classify task complexity
        t0 = time.time()
        complexity = await self.classifier.classify(user_prompt)
        t_classify = (time.time() - t0) * 1000.0
        logger.info("[REASONING] Complexity for '%s': %s (%.2fms)", user_prompt[:40], complexity.value, t_classify)

        # 2. Fast Path check
        if complexity in (TaskComplexity.DIRECT, TaskComplexity.SIMPLE):
            return None  # Pass through to standard fast streaming LLM

        # 3. Multi-Step or Complex Task -> Execute Planning Workflow
        self._current_cancel_event.clear()
        generation_id = str(uuid.uuid4())

        # Vocalize initial natural status without exposing hidden chain of thought
        ack_message = self._generate_ack_status(user_prompt)
        if ack_message and self.tts and not self.security.is_emergency_stopped:
            self.tts.on_llm_start(generation_id=generation_id)
            self.tts.feed_text_delta(ack_message, generation_id=generation_id)
            self.tts.flush_text(generation_id=generation_id)

        # 4. Generate & Validate Plan
        t_plan_start = time.time()
        plan = await self.planner.generate_plan_async(user_prompt)
        self._active_plan = plan
        t_plan_dur = (time.time() - t_plan_start) * 1000.0

        self._broadcast({
            "type": "plan_created",
            "plan": plan.to_dict(),
            "complexity": complexity.value,
            "plan_duration_ms": round(t_plan_dur, 2),
            "timestamp": int(time.time() * 1000),
        })

        # Callbacks for progress updates
        async def on_step_start(step: PlanStep):
            self._broadcast({
                "type": "plan_step_started",
                "plan_id": plan.id,
                "step": step.to_dict(),
                "timestamp": int(time.time() * 1000),
            })

        async def on_step_complete(step: PlanStep, result: StepResult):
            status_ev = "plan_step_completed" if result.status == StepStatus.COMPLETED else "plan_step_failed"
            self._broadcast({
                "type": status_ev,
                "plan_id": plan.id,
                "step_id": step.id,
                "status": result.status.value,
                "output": result.output,
                "error": result.error,
                "timestamp": int(time.time() * 1000),
            })

        # 5. Execution & Replanning Loop
        self._broadcast({
            "type": "plan_started",
            "plan_id": plan.id,
            "timestamp": int(time.time() * 1000),
        })

        completed_plan = await self.executor.execute_plan(
            plan=plan,
            cancel_event=self._current_cancel_event,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
        )
        exec_status = completed_plan.status

        # Handle Replanning on Step Failure
        while exec_status == PlanStatus.FAILED and plan.replan_count < plan.max_replans:
            failed_step = next((s for s in plan.steps if s.status == StepStatus.FAILED), None)
            if not failed_step:
                break

            logger.info("[REASONING] Attempting replanning for failed step '%s'", failed_step.id)
            replanned = self.replanner.replan(
                plan=plan,
                failed_step_id=failed_step.id,
                failure_reason=failed_step.error or "Step failed",
            )
            if not replanned:
                break

            self._broadcast({
                "type": "plan_replanned",
                "plan": plan.to_dict(),
                "replan_count": plan.replan_count,
                "timestamp": int(time.time() * 1000),
            })

            # Resume execution with revised plan
            completed_plan = await self.executor.execute_plan(
                plan=plan,
                cancel_event=self._current_cancel_event,
                on_step_start=on_step_start,
                on_step_complete=on_step_complete,
            )
            exec_status = completed_plan.status

        # 6. Verification
        verification = await self.verifier.verify(plan)
        if not verification.is_verified and exec_status == PlanStatus.COMPLETED and plan.replan_count < plan.max_replans:
            # Verification caught failure -> trigger replanning
            replanned = self.replanner.replan(
                plan=plan,
                failed_step_id=plan.steps[-1].id,
                failure_reason=verification.reason,
            )
            if replanned:
                self._broadcast({
                    "type": "plan_replanned",
                    "plan": plan.to_dict(),
                    "reason": verification.reason,
                    "timestamp": int(time.time() * 1000),
                })
                completed_plan = await self.executor.execute_plan(
                    plan=plan,
                    cancel_event=self._current_cancel_event,
                    on_step_start=on_step_start,
                    on_step_complete=on_step_complete,
                )
                exec_status = completed_plan.status
                verification = await self.verifier.verify(plan)

        final_status = "completed" if (exec_status == PlanStatus.COMPLETED and verification.is_verified) else (exec_status.value if hasattr(exec_status, "value") else str(exec_status))
        self._broadcast({
            "type": f"plan_{final_status}",
            "plan_id": plan.id,
            "status": final_status,
            "verification": verification.to_dict(),
            "timestamp": int(time.time() * 1000),
        })

        # 7. Synthesize final response
        summary = self._synthesize_final_summary(plan, verification)
        if summary and self.tts and not self.security.is_emergency_stopped:
            final_gen_id = str(uuid.uuid4())
            self.tts.on_llm_start(generation_id=final_gen_id)
            self.tts.feed_text_delta(summary, generation_id=final_gen_id)
            self.tts.flush_text(generation_id=final_gen_id)

        # Persist conversation turn to MemoryService if session_id provided
        if self.memory_service and session_id:
            try:
                self.memory_service.record_user_turn(session_id, user_prompt, generation_id=generation_id)
                self.memory_service.record_assistant_turn(
                    session_id=session_id,
                    content=summary,
                    status=TurnStatus.COMPLETED if final_status == "completed" else TurnStatus.ERROR,
                    tool_action={"plan_id": plan.id, "steps": len(plan.steps)},
                    tool_result={"status": final_status, "verified": verification.is_verified},
                    generation_id=generation_id,
                )
            except Exception as e:
                logger.error("Error persisting plan turn: %s", e)

        return {
            "status": final_status,
            "plan": plan.to_dict(),
            "verification": verification.to_dict(),
            "summary": summary,
            "complexity": complexity.value,
        }

    def _generate_ack_status(self, prompt: str) -> str:
        text = prompt.lower()
        if "test" in text and ("repo" in text or "project" in text or "paaro" in text):
            return "I will check the repository and run the test suite for you."
        if "server" in text and ("restart" in text or "stopped" in text):
            return "I am inspecting the server status and logs to restart it safely."
        return "I am working on your multi-step request."

    def _synthesize_final_summary(self, plan: ExecutionPlan, verification: VerificationResult) -> str:
        if verification.is_verified:
            completed_steps = [s for s in plan.steps if s.status == StepStatus.COMPLETED]
            return f"Completed {len(completed_steps)} steps successfully. {verification.reason}"
        else:
            failed_steps = [s for s in plan.steps if s.status == StepStatus.FAILED]
            if failed_steps:
                return f"Task encountered an issue at step '{failed_steps[0].id}': {failed_steps[0].error or 'Execution failed'}."
            return f"Task completed but verification indicated an issue: {verification.reason}."
