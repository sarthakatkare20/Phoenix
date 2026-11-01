"""
Plan Executor for Paaro Reasoning Engine (Step 8).
Dependency-aware step scheduler and execution loop routed strictly through Tool Gateway.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from reasoning.models import ExecutionPlan, PlanStatus, PlanStep, StepResult, StepStatus
from security import SecurityContext, security_context
from tool_gateway import PolicyDecision, ToolGateway, tool_gateway

logger = logging.getLogger("paaro.reasoning.executor")


class PlanExecutor:
    """
    Executes ExecutionPlan steps respecting dependency ordering and Tool Gateway security.
    """

    def __init__(
        self,
        gateway: Optional[ToolGateway] = None,
        tool_gateway_instance: Optional[ToolGateway] = None,
        tool_gateway: Optional[ToolGateway] = None,
        security: Optional[SecurityContext] = None,
        max_retries_per_step: int = 2,
        max_retries: Optional[int] = None,
    ):
        from tool_gateway import tool_gateway as default_gw
        self.gateway = gateway or tool_gateway_instance or tool_gateway or default_gw
        self.security = security or security_context
        self.max_retries_per_step = max_retries if max_retries is not None else max_retries_per_step
        self.max_retries = self.max_retries_per_step
        self._active_plan: Optional[ExecutionPlan] = None
        self._cancel_event = asyncio.Event()
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
                logger.error("Error in executor listener: %s", e)

    @property
    def active_plan(self) -> Optional[ExecutionPlan]:
        return self._active_plan

    def cancel(self) -> Optional[str]:
        """Cancel active plan execution."""
        if self._active_plan:
            plan_id = self._active_plan.id
            self._cancel_event.set()
            self._active_plan.status = PlanStatus.CANCELLED
            for s in self._active_plan.steps:
                if s.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.READY):
                    s.status = StepStatus.CANCELLED
            self._broadcast({
                "type": "plan_cancelled",
                "plan_id": plan_id,
                "timestamp": int(time.time() * 1000),
            })
            return plan_id
        return None

    async def execute_step(
        self,
        step: PlanStep,
        plan_context: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        """
        Execute a single PlanStep through ToolGateway.
        """
        if self.security.is_emergency_stopped:
            step.status = StepStatus.CANCELLED
            step.error = "Emergency stop is active."
            return StepResult(step_id=step.id, status=StepStatus.CANCELLED, error=step.error, success=False)

        step.status = StepStatus.RUNNING
        t0 = time.time()
        logger.info("[REASONING] Starting step '%s': %s (action=%s)", step.id, step.description, step.action)

        # Merge plan context data into args if appropriate
        merged_args = dict(step.args)
        if plan_context:
            merged_args["_plan_context"] = plan_context

        # Route through Tool Gateway
        tool_res = self.gateway.execute_allowed(step.action, merged_args)
        res_status = tool_res.get("status")

        if res_status == "pending_confirmation":
            logger.info("[REASONING] Step '%s' action '%s' requires user confirmation", step.id, step.action)
            step.status = StepStatus.BLOCKED
            step.result = StepResult(step_id=step.id, status=StepStatus.BLOCKED, output=tool_res, error=tool_res.get("message"), success=False)
            return step.result

        if res_status == "error" or tool_res.get("policy") == "deny":
            err_msg = tool_res.get("error") or "Tool execution failed"
            logger.warning("[REASONING] Step '%s' failed: %s", step.id, err_msg)
            
            if step.retries < step.max_retries:
                step.retries += 1
                step.status = StepStatus.PENDING  # Retry
                logger.info("[REASONING] Step '%s' will retry (%d/%d)", step.id, step.retries, step.max_retries)
                step.result = StepResult(step_id=step.id, status=StepStatus.PENDING, error=err_msg, success=False)
                return step.result
            else:
                step.status = StepStatus.FAILED
                step.error = err_msg
                step.result = StepResult(
                    step_id=step.id,
                    status=StepStatus.FAILED,
                    error=err_msg,
                    needs_replan=True,
                    replan_reason=f"Step '{step.id}' failed after {step.retries} retries: {err_msg}",
                    success=False,
                )
                return step.result

        # Success
        output = tool_res.get("result")
        step.status = StepStatus.COMPLETED
        step.error = None
        dur_ms = (time.time() - t0) * 1000.0
        logger.info("[REASONING] Step '%s' completed successfully in %.1fms", step.id, dur_ms)

        step.result = StepResult(step_id=step.id, status=StepStatus.COMPLETED, output=output, success=True)
        return step.result

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        cancel_event: Optional[asyncio.Event] = None,
        on_step_start: Optional[Callable[[PlanStep], Any]] = None,
        on_step_complete: Optional[Callable[[PlanStep, StepResult], Any]] = None,
    ) -> ExecutionPlan:
        """
        Execute all steps of an ExecutionPlan according to dependencies.
        """
        self._active_plan = plan
        self._cancel_event.clear()
        combined_cancel = cancel_event or self._cancel_event

        if self.security.is_emergency_stopped:
            logger.warning("[REASONING] Plan '%s' halted by emergency stop before start", plan.id)
            plan.status = PlanStatus.FAILED
            for s in plan.steps:
                s.status = StepStatus.CANCELLED
            return plan

        plan.status = PlanStatus.RUNNING
        logger.info("[REASONING] Executing plan '%s' with %d steps", plan.id, len(plan.steps))
        self._broadcast({
            "type": "plan_started",
            "plan_id": plan.id,
            "goal": plan.goal,
            "steps": [s.to_dict() for s in plan.steps],
            "timestamp": int(time.time() * 1000),
        })

        while not plan.all_completed() and not plan.has_failed():
            if combined_cancel and combined_cancel.is_set():
                logger.info("[REASONING] Plan '%s' cancelled by cancel event", plan.id)
                plan.status = PlanStatus.CANCELLED
                for s in plan.steps:
                    if s.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.READY):
                        s.status = StepStatus.CANCELLED
                self._broadcast({
                    "type": "plan_cancelled",
                    "plan_id": plan.id,
                    "timestamp": int(time.time() * 1000),
                })
                return plan

            if self.security.is_emergency_stopped:
                logger.warning("[REASONING] Plan '%s' halted by emergency stop", plan.id)
                plan.status = PlanStatus.FAILED
                for s in plan.steps:
                    if s.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.READY):
                        s.status = StepStatus.CANCELLED
                return plan

            ready = plan.ready_steps()
            if not ready:
                # Check if any step is currently blocked on confirmation
                if any(s.status == StepStatus.BLOCKED for s in plan.steps):
                    plan.status = PlanStatus.PAUSED
                    logger.info("[REASONING] Plan '%s' paused on confirmation requirement", plan.id)
                    return plan

                # No ready steps and not completed -> deadlock or failure
                logger.error("[REASONING] Plan '%s' stalled with no ready steps", plan.id)
                plan.status = PlanStatus.FAILED
                return plan

            # Execute the next ready step
            step = ready[0]
            self._broadcast({
                "type": "plan_step_started",
                "plan_id": plan.id,
                "step": step.to_dict(),
                "timestamp": int(time.time() * 1000),
            })
            if on_step_start:
                try:
                    if asyncio.iscoroutinefunction(on_step_start):
                        await on_step_start(step)
                    else:
                        on_step_start(step)
                except Exception as e:
                    logger.error("Error in on_step_start callback: %s", e)

            res = await self.execute_step(step, plan_context=plan.context_data)

            ev_type = "plan_step_completed" if res.status == StepStatus.COMPLETED else "plan_step_failed"
            self._broadcast({
                "type": ev_type,
                "plan_id": plan.id,
                "step": step.to_dict(),
                "result": res.to_dict(),
                "timestamp": int(time.time() * 1000),
            })

            if on_step_complete:
                try:
                    if asyncio.iscoroutinefunction(on_step_complete):
                        await on_step_complete(step, res)
                    else:
                        on_step_complete(step, res)
                except Exception as e:
                    logger.error("Error in on_step_complete callback: %s", e)

            if res.status == StepStatus.BLOCKED:
                plan.status = PlanStatus.PAUSED
                return plan

            if res.status == StepStatus.FAILED:
                plan.status = PlanStatus.FAILED
                # Mark dependent steps as BLOCKED
                for s in plan.steps:
                    if step.id in s.depends_on and s.status == StepStatus.PENDING:
                        s.status = StepStatus.BLOCKED
                self._broadcast({
                    "type": "plan_failed",
                    "plan_id": plan.id,
                    "failed_step": step.id,
                    "error": res.error,
                    "timestamp": int(time.time() * 1000),
                })
                return plan

            # Yield control to event loop
            await asyncio.sleep(0.01)

        plan.status = PlanStatus.COMPLETED if plan.all_completed() else PlanStatus.FAILED
        plan.updated_at = time.time()
        final_ev = "plan_completed" if plan.status == PlanStatus.COMPLETED else "plan_failed"
        self._broadcast({
            "type": final_ev,
            "plan_id": plan.id,
            "status": plan.status.value,
            "timestamp": int(time.time() * 1000),
        })
        return plan
