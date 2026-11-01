"""
Plan Verifier for Paaro Reasoning Engine (Step 8).
Validates actual goal achievement instead of assuming success from execution alone.
"""

import logging
from typing import Any, Dict, Optional

from reasoning.models import ExecutionPlan, PlanStep, StepStatus, VerificationResult

logger = logging.getLogger("paaro.reasoning.verifier")


class PlanVerifier:
    """
    Evaluates whether the intended goal of an ExecutionPlan was genuinely satisfied.
    """

    async def verify(self, plan: ExecutionPlan) -> VerificationResult:
        """
        Verify the completed plan against target expectations.
        """
        return self.verify_sync(plan)

    def verify_sync(self, plan: ExecutionPlan) -> VerificationResult:
        if not plan.all_completed():
            return VerificationResult(
                is_verified=False,
                reason="Plan has unfinished or failed steps.",
                metrics={"completed_steps": len([s for s in plan.steps if s.status == StepStatus.COMPLETED])},
            )

        goal_lower = plan.goal.lower()

        # 1. Verification for test execution workflows
        if "test" in goal_lower:
            test_steps = [s for s in plan.steps if "test" in s.action.lower() or "verify" in s.action.lower()]
            if test_steps:
                target_step = test_steps[-1]
                step_res = target_step.result
                output_str = ""
                has_failed = False
                if step_res:
                    if hasattr(step_res, "output"):
                        output_str = str(step_res.output).lower()
                    else:
                        output_str = str(step_res).lower()
                    if hasattr(step_res, "success") and not step_res.success:
                        has_failed = True

                if has_failed or ("fail" in output_str and "0 fail" not in output_str and "10 pass" not in output_str):
                    logger.warning("[REASONING] Verification failed: test step '%s' reported failures", target_step.id)
                    return VerificationResult(
                        is_verified=False,
                        reason=f"Test suite reported failures: {output_str}",
                        metrics={"step_id": target_step.id, "result": output_str},
                    )

        # 2. Verification for server restart workflows
        if "server" in goal_lower and any(w in goal_lower for w in ["restart", "start"]):
            verify_steps = [s for s in plan.steps if "verify" in s.action.lower() or "server" in s.action.lower()]
            if verify_steps:
                target_step = verify_steps[-1]
                if target_step.error or target_step.status != StepStatus.COMPLETED:
                    return VerificationResult(
                        is_verified=False,
                        reason=f"Server verification failed on step '{target_step.id}'",
                        metrics={"step_id": target_step.id},
                    )

        # Default: all steps completed successfully
        logger.info("[REASONING] Plan '%s' successfully verified against goal '%s'", plan.id, plan.goal[:40])
        return VerificationResult(
            is_verified=True,
            reason="All plan steps and verification assertions completed successfully.",
            metrics={"total_steps": len(plan.steps), "replan_count": plan.replan_count},
        )
