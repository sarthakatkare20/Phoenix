"""
Replanner for Paaro Reasoning Engine (Step 8).
Handles runtime execution divergences, step failures, and dynamic plan reconfiguration within strict bounds.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from reasoning.models import ExecutionPlan, PlanStatus, PlanStep, StepStatus
from reasoning.planner import PlanValidator
from streaming_llm import StreamingLLM

logger = logging.getLogger("paaro.reasoning.replanner")


class Replanner:
    """
    Dynamically adjusts execution plans when steps fail or verification fails.
    Enforces maximum replan thresholds to prevent infinite agent reasoning loops.
    """

    def __init__(
        self,
        llm: Optional[StreamingLLM] = None,
        validator: Optional[PlanValidator] = None,
        max_replans: int = 3,
    ):
        self.llm = llm
        self.validator = validator or PlanValidator()
        self.max_replans = max_replans

    async def replan(
        self,
        plan: ExecutionPlan,
        failed_step: Optional[PlanStep] = None,
        failed_step_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> Optional[ExecutionPlan]:
        """
        Async produce a revised ExecutionPlan addressing the failure.
        """
        return self.replan_sync(
            plan=plan,
            failed_step=failed_step,
            failed_step_id=failed_step_id,
            failure_reason=failure_reason,
        )

    def replan_sync(
        self,
        plan: ExecutionPlan,
        failed_step: Optional[PlanStep] = None,
        failed_step_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> Optional[ExecutionPlan]:
        """
        Produce a revised ExecutionPlan addressing the failure.
        Returns None if max replans reached.
        """
        effective_max = min(plan.max_replans, self.max_replans)
        if plan.replan_count >= effective_max:
            logger.warning(
                "[REASONING] Plan '%s' reached max replan limit (%d/%d); aborting",
                plan.id,
                plan.replan_count,
                effective_max,
            )
            return None

        target_step = failed_step
        if not target_step and failed_step_id:
            target_step = plan.get_step(failed_step_id)
        if not target_step and plan.steps:
            target_step = plan.steps[0]

        step_id_str = target_step.id if target_step else "unknown"
        plan.replan_count += 1
        logger.info(
            "[REASONING] Replanning plan '%s' (attempt %d/%d) due to failure on '%s': %s",
            plan.id,
            plan.replan_count,
            step_id_str,
            failure_reason or getattr(target_step, "error", ""),
        )

        # 1. Deterministic Replanning Rules
        if target_step:
            action = target_step.action.lower()
            
            # If tests failed due to dependency/syntax error
            if action in ("run_tests", "modify_code"):
                # Insert recovery diagnostic step
                diag_id = f"replan_{plan.replan_count}_diag"
                fix_id = f"replan_{plan.replan_count}_fix"
                retry_test_id = f"replan_{plan.replan_count}_test"

                new_diag = PlanStep(
                    id=diag_id,
                    description=f"Diagnose failure on {target_step.id}",
                    action="analyze_test_failures",
                    args={"failed_step": target_step.id, "error": failure_reason or target_step.error},
                    depends_on=[dep for dep in target_step.depends_on if dep != target_step.id],
                )
                new_fix = PlanStep(
                    id=fix_id,
                    description="Apply corrective patch",
                    action="modify_code",
                    args={"target": target_step.id},
                    depends_on=[diag_id],
                )
                new_retry = PlanStep(
                    id=retry_test_id,
                    description="Re-test after corrective patch",
                    action="run_tests",
                    args={"suite": "targeted"},
                    depends_on=[fix_id],
                )

                # Keep completed steps, drop failed step and downstream steps
                kept_steps = [s for s in plan.steps if s.status == StepStatus.COMPLETED and s.id != target_step.id]
                plan.steps = kept_steps + [new_diag, new_fix, new_retry]

            elif action == "restart_server":
                # Check logs first, then retry server with clean config
                diag_id = f"replan_{plan.replan_count}_logs"
                retry_server_id = f"replan_{plan.replan_count}_srv"
                verify_id = f"replan_{plan.replan_count}_vfy"

                new_diag = PlanStep(
                    id=diag_id,
                    description="Inspect server crash logs",
                    action="check_logs",
                    args={"service": "backend"},
                    depends_on=[dep for dep in target_step.depends_on if dep != target_step.id],
                )
                new_retry = PlanStep(
                    id=retry_server_id,
                    description="Restart server with fallback configuration",
                    action="restart_server",
                    args={"fallback": True},
                    depends_on=[diag_id],
                )
                new_verify = PlanStep(
                    id=verify_id,
                    description="Verify fallback server status",
                    action="verify_endpoint",
                    args={"endpoint": "/health"},
                    depends_on=[retry_server_id],
                )

                kept_steps = [s for s in plan.steps if s.status == StepStatus.COMPLETED and s.id != target_step.id]
                plan.steps = kept_steps + [new_diag, new_retry, new_verify]

            else:
                # Generic fallback: retry step with modified argument or diagnostic
                target_step.status = StepStatus.PENDING
                target_step.retries = 0
                target_step.error = None
                target_step.args["_replan_attempt"] = plan.replan_count

        # Validate replanned structure
        is_valid, errors = self.validator.validate(plan)
        if not is_valid:
            logger.error("[REASONING] Replanned structure validation failed: %s", errors)
            return None

        plan.status = PlanStatus.RUNNING
        plan.updated_at = time.time()
        return plan
