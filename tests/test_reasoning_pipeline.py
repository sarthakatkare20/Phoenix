"""
Comprehensive Test Suite for Paaro Step 8: Reasoning & Planning Engine.
Tests task complexity classification, structured plan generation, plan validation,
dependency-based execution, step retry, bounded replanning, plan verification,
Tool Gateway policy enforcement, barge-in cancellation, and Step 7 proactive integration.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from paaro.config import PaaroSettings
from paaro.security import SecurityContext
from paaro.tool_gateway import PolicyDecision, PolicyEngine, ToolGateway
from paaro.memory.service import MemoryService
from paaro.proactive.events import EventSeverity, ProactiveEvent
from paaro.reasoning.models import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    StepResult,
    StepStatus,
    TaskComplexity,
    VerificationResult,
)
from paaro.reasoning.classifier import TaskComplexityClassifier
from paaro.reasoning.planner import PlanGenerator, PlanValidator
from paaro.reasoning.executor import PlanExecutor
from paaro.reasoning.verifier import PlanVerifier
from paaro.reasoning.replanner import Replanner
from paaro.reasoning.engine import ReasoningEngine


class TestTaskComplexityClassifier(unittest.IsolatedAsyncioTestCase):
    """Test deterministic fast-path and LLM classification."""

    async def asyncSetUp(self):
        self.classifier = TaskComplexityClassifier(llm=None)

    async def test_direct_requests_fast_path(self):
        direct_queries = [
            "What time is it?",
            "What is the date today?",
            "What's my CPU usage?",
            "Open Chrome",
            "Open VS Code",
            "Who are you?",
            "Hello there",
        ]
        for query in direct_queries:
            complexity = await self.classifier.classify(query)
            self.assertEqual(complexity, TaskComplexity.DIRECT, f"Query '{query}' should be DIRECT")
            self.assertTrue(complexity.is_fast_path)

    async def test_simple_requests_fast_path(self):
        simple_queries = [
            "Open VS Code and open my project",
            "Check the memory and open Chrome",
            "Launch terminal and check CPU",
        ]
        for query in simple_queries:
            complexity = await self.classifier.classify(query)
            self.assertEqual(complexity, TaskComplexity.SIMPLE, f"Query '{query}' should be SIMPLE")
            self.assertTrue(complexity.is_fast_path)

    async def test_multi_step_requests(self):
        multi_step_queries = [
            "Run my tests and tell me what failed",
            "Inspect project files and list directory",
            "Check git status and run tests",
        ]
        for query in multi_step_queries:
            complexity = await self.classifier.classify(query)
            self.assertEqual(complexity, TaskComplexity.MULTI_STEP, f"Query '{query}' should be MULTI_STEP")
            self.assertFalse(complexity.is_fast_path)

    async def test_complex_requests(self):
        complex_queries = [
            "Find why tests are failing, fix the issue, rerun them and make sure everything passes",
            "Diagnose backend crash, restart server and verify healthy",
            "Check my repo, debug failure and fix it",
        ]
        for query in complex_queries:
            complexity = await self.classifier.classify(query)
            self.assertEqual(complexity, TaskComplexity.COMPLEX, f"Query '{query}' should be COMPLEX")
            self.assertFalse(complexity.is_fast_path)

    async def test_llm_assisted_classification_fallback(self):
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="MULTI_STEP")
        classifier = TaskComplexityClassifier(llm=mock_llm)

        complexity = await classifier.classify("Execute the automated deployment procedure across staging")
        self.assertEqual(complexity, TaskComplexity.MULTI_STEP)


class TestPlanValidator(unittest.TestCase):
    """Test structural, dependency, tool authorization, and bounds validation."""

    def setUp(self):
        self.validator = PlanValidator(max_steps=8)

    def test_valid_plan_passes(self):
        step1 = PlanStep(id="step_1", description="Inspect repo", action="inspect_project")
        step2 = PlanStep(id="step_2", description="Run tests", action="run_tests", depends_on=["step_1"])
        plan = ExecutionPlan(goal="Check repo tests", steps=[step1, step2])

        is_valid, errors = self.validator.validate(plan)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_duplicate_step_ids_rejected(self):
        step1 = PlanStep(id="step_1", description="Inspect repo", action="inspect_project")
        step2 = PlanStep(id="step_1", description="Run tests", action="run_tests")
        plan = ExecutionPlan(goal="Duplicate step test", steps=[step1, step2])

        is_valid, errors = self.validator.validate(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("Duplicate step ID" in err for err in errors))

    def test_missing_dependency_rejected(self):
        step1 = PlanStep(id="step_1", description="Run tests", action="run_tests", depends_on=["non_existent_step"])
        plan = ExecutionPlan(goal="Missing dep test", steps=[step1])

        is_valid, errors = self.validator.validate(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("depends on nonexistent step" in err for err in errors))

    def test_cyclic_dependency_rejected(self):
        step1 = PlanStep(id="step_1", description="Action 1", action="run_tests", depends_on=["step_2"])
        step2 = PlanStep(id="step_2", description="Action 2", action="inspect_project", depends_on=["step_1"])
        plan = ExecutionPlan(goal="Cycle test", steps=[step1, step2])

        is_valid, errors = self.validator.validate(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("Cycle detected" in err for err in errors))

    def test_excessive_steps_rejected(self):
        steps = [
            PlanStep(id=f"step_{i}", description=f"Step {i}", action="read_file", parameters={"file_path": "a.txt"})
            for i in range(12)
        ]
        plan = ExecutionPlan(goal="Too many steps", steps=steps)

        is_valid, errors = self.validator.validate(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("exceeds maximum allowed" in err for err in errors))

    def test_unauthorized_tool_rejected(self):
        step = PlanStep(id="step_1", description="Execute arbitrary shell", action="execute_arbitrary_shell_command")
        plan = ExecutionPlan(goal="Unauthorized tool", steps=[step])

        is_valid, errors = self.validator.validate(plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("Unsupported or unauthorized action" in err for err in errors))


class TestPlanGenerator(unittest.IsolatedAsyncioTestCase):
    """Test deterministic template generation and LLM fallback."""

    async def asyncSetUp(self):
        self.validator = PlanValidator(max_steps=8)
        self.generator = PlanGenerator(validator=self.validator, llm=None)

    async def test_deterministic_template_test_diagnose_fix(self):
        goal = "Find why tests are failing, fix the issue and rerun them"
        plan = await self.generator.generate(goal)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 5)
        self.assertEqual(plan.steps[0].action, "inspect_project")
        self.assertEqual(plan.steps[1].action, "run_tests")
        self.assertEqual(plan.steps[2].action, "analyze_test_failures")
        self.assertEqual(plan.steps[3].action, "modify_code")
        self.assertEqual(plan.steps[4].action, "run_tests")

    async def test_deterministic_template_server_restart(self):
        goal = "Backend stopped, check logs, restart server and verify"
        plan = await self.generator.generate(goal)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 4)
        self.assertEqual(plan.steps[0].action, "check_server_status")
        self.assertEqual(plan.steps[1].action, "check_logs")
        self.assertEqual(plan.steps[2].action, "restart_server")
        self.assertEqual(plan.steps[3].action, "verify_endpoint")


class TestPlanExecutor(unittest.IsolatedAsyncioTestCase):
    """Test dependency execution, ToolGateway authority, retries, and failure handling."""

    async def asyncSetUp(self):
        self.security = SecurityContext()
        self.tool_gateway = ToolGateway()
        self.executor = PlanExecutor(tool_gateway=self.tool_gateway, security=self.security, max_retries=1)

    async def test_successful_plan_execution_with_dependencies(self):
        executed_events = []
        self.executor.add_listener(lambda e: executed_events.append(e))

        step1 = PlanStep(id="step_1", description="Inspect repo", action="inspect_project", parameters={"project_dir": "."})
        step2 = PlanStep(id="step_2", description="List directory", action="list_directory", depends_on=["step_1"], parameters={"path": "."})
        plan = ExecutionPlan(goal="Inspect directory structure", steps=[step1, step2])

        result_plan = await self.executor.execute_plan(plan)
        self.assertEqual(result_plan.status, PlanStatus.COMPLETED)
        self.assertEqual(step1.status, StepStatus.COMPLETED)
        self.assertEqual(step2.status, StepStatus.COMPLETED)
        self.assertIsNotNone(step1.result)
        self.assertIsNotNone(step2.result)
        self.assertTrue(step1.result.success)
        self.assertTrue(step2.result.success)

        event_types = [e.get("type") for e in executed_events]
        self.assertIn("plan_started", event_types)
        self.assertIn("plan_step_started", event_types)
        self.assertIn("plan_step_completed", event_types)
        self.assertIn("plan_completed", event_types)

    async def test_failed_step_retries_and_fails(self):
        # Action that fails
        self.tool_gateway.register_handler("read_file", lambda args: (_ for _ in ()).throw(FileNotFoundError("File not found")))
        step1 = PlanStep(id="step_1", description="Read nonexistent file", action="read_file", parameters={"file_path": "non_existent_123456.txt"}, max_retries=2)
        plan = ExecutionPlan(goal="Read bad file", steps=[step1])

        result_plan = await self.executor.execute_plan(plan)
        self.assertEqual(result_plan.status, PlanStatus.FAILED)
        self.assertEqual(step1.status, StepStatus.FAILED)
        self.assertEqual(step1.retry_count, 2)

    async def test_dependent_step_blocked_when_parent_fails(self):
        self.tool_gateway.register_handler("read_file", lambda args: (_ for _ in ()).throw(FileNotFoundError("File not found")))
        step1 = PlanStep(id="step_1", description="Read nonexistent file", action="read_file", parameters={"file_path": "non_existent_123456.txt"})
        step2 = PlanStep(id="step_2", description="Inspect", action="inspect_project", depends_on=["step_1"])
        plan = ExecutionPlan(goal="Dependency failure test", steps=[step1, step2])

        result_plan = await self.executor.execute_plan(plan)
        self.assertEqual(result_plan.status, PlanStatus.FAILED)
        self.assertEqual(step1.status, StepStatus.FAILED)
        self.assertEqual(step2.status, StepStatus.BLOCKED)

    async def test_tool_gateway_security_enforcement(self):
        """Planner cannot bypass ToolGateway or execute unauthorized actions."""
        # Directly executing disallowed tool should be denied by policy
        step1 = PlanStep(id="step_1", description="Dangerous format disk", action="format_disk")
        plan = ExecutionPlan(goal="Malicious execution", steps=[step1])

        result_plan = await self.executor.execute_plan(plan)
        self.assertEqual(result_plan.status, PlanStatus.FAILED)
        self.assertEqual(step1.status, StepStatus.FAILED)
        self.assertIn("denied by system security policy", step1.result.error)


class TestPlanVerifier(unittest.IsolatedAsyncioTestCase):
    """Test post-execution verification checks."""

    async def asyncSetUp(self):
        self.verifier = PlanVerifier()

    async def test_test_verification_success(self):
        step1 = PlanStep(id="step_1", description="Run tests", action="run_tests")
        step1.status = StepStatus.COMPLETED
        step1.result = StepResult(step_id="step_1", success=True, output="Ran 10 tests. 10 passed. 0 failed. OK")
        plan = ExecutionPlan(goal="Run tests and fix", steps=[step1], status=PlanStatus.COMPLETED)

        verification = await self.verifier.verify(plan)
        self.assertTrue(verification.verified)

    async def test_test_verification_failure_detects_failures(self):
        step1 = PlanStep(id="step_1", description="Run tests", action="run_tests")
        step1.status = StepStatus.COMPLETED
        step1.result = StepResult(step_id="step_1", success=False, output="FAILED (failures=2, errors=1)")
        plan = ExecutionPlan(goal="Run tests and fix", steps=[step1], status=PlanStatus.COMPLETED)

        verification = await self.verifier.verify(plan)
        self.assertFalse(verification.verified)
        self.assertIn("Test suite reported failures", verification.reason)


class TestReplanner(unittest.IsolatedAsyncioTestCase):
    """Test dynamic step insertion, bounded replans, and failure recovery."""

    async def asyncSetUp(self):
        self.validator = PlanValidator(max_steps=8)
        self.replanner = Replanner(validator=self.validator, max_replans=2)

    async def test_replan_on_test_failure_injects_diagnosis_and_fix(self):
        step1 = PlanStep(id="step_1", description="Run tests", action="run_tests")
        step1.status = StepStatus.FAILED
        step1.result = StepResult(step_id="step_1", success=False, output="AssertionError in test_calc.py line 42")
        plan = ExecutionPlan(goal="Run tests", steps=[step1], status=PlanStatus.FAILED)

        updated_plan = await self.replanner.replan(plan, failed_step=step1)
        self.assertIsNotNone(updated_plan)
        self.assertEqual(updated_plan.replan_count, 1)
        self.assertEqual(updated_plan.status, PlanStatus.RUNNING)
        # Verify diagnosis and fix steps were inserted
        actions = [s.action for s in updated_plan.steps]
        self.assertIn("analyze_test_failures", actions)
        self.assertIn("modify_code", actions)
        self.assertIn("run_tests", actions)

    async def test_bounded_replan_limit_enforced(self):
        step1 = PlanStep(id="step_1", description="Run tests", action="run_tests")
        step1.status = StepStatus.FAILED
        step1.result = StepResult(step_id="step_1", success=False, output="Error")
        plan = ExecutionPlan(goal="Run tests", steps=[step1], status=PlanStatus.FAILED, replan_count=2)

        updated_plan = await self.replanner.replan(plan, failed_step=step1)
        self.assertIsNone(updated_plan)


class TestReasoningEngineCancellationAndEmergencyStop(unittest.IsolatedAsyncioTestCase):
    """Test barge-in cancellation and emergency stop integration with Reasoning Engine."""

    async def asyncSetUp(self):
        self.config = PaaroSettings(REASONING_ENABLED=True)
        self.security = SecurityContext()
        self.engine = ReasoningEngine(config=self.config, security=self.security)

    async def test_cancellation_aborts_active_plan(self):
        step1 = PlanStep(id="step_1", description="Inspect repo", action="inspect_project")
        step2 = PlanStep(id="step_2", description="List directory", action="list_directory", depends_on=["step_1"])
        plan = ExecutionPlan(goal="Inspect repo", steps=[step1, step2])

        async def on_step_start(step):
            self.engine.cancel_active_plan()

        result_plan = await self.engine.executor.execute_plan(plan, on_step_start=on_step_start)
        self.assertEqual(result_plan.status, PlanStatus.CANCELLED)

    async def test_emergency_stop_halts_plan_instantly(self):
        self.security.trigger_emergency_stop(reason="User emergency stop button pressed")
        step1 = PlanStep(id="step_1", description="Inspect repo", action="inspect_project")
        plan = ExecutionPlan(goal="Inspect repo", steps=[step1])

        result_plan = await self.engine.executor.execute_plan(plan)
        self.assertEqual(result_plan.status, PlanStatus.FAILED)
        self.assertEqual(step1.status, StepStatus.CANCELLED)


class TestReasoningAndProactiveIntegration(unittest.IsolatedAsyncioTestCase):
    """Test Step 7 Proactive Event handoff to Step 8 Reasoning Engine."""

    async def asyncSetUp(self):
        self.config = PaaroSettings(REASONING_ENABLED=True)
        self.security = SecurityContext()
        self.engine = ReasoningEngine(config=self.config, security=self.security)

    async def test_proactive_event_triggers_reasoning_flow(self):
        """Simulate proactive brain asking user and user saying yes -> reasoning executes diagnostic plan."""
        # 1. Proactive event occurs
        proactive_ev = ProactiveEvent(
            event_type="server_stopped",
            source="system_monitor",
            severity=EventSeverity.HIGH,
            data={"service": "paaro-backend", "port": 8000},
        )
        self.assertEqual(proactive_ev.event_type, "server_stopped")

        # 2. User confirms action: "Paaro, check backend stopped, restart it and verify"
        user_response = "Check backend stopped, restart it and verify"
        complexity = await self.engine.classifier.classify(user_response)
        self.assertIn(complexity, (TaskComplexity.MULTI_STEP, TaskComplexity.COMPLEX))

        # 3. Plan generated and executed
        plan = await self.engine.generate_plan(user_response)
        self.assertIsNotNone(plan)
        self.assertTrue(len(plan.steps) >= 3)
        self.assertEqual(plan.steps[0].action, "check_server_status")

        # 4. Execute plan (pauses on Step 3 restart_server because policy requires user confirmation)
        result_plan = await self.engine.executor.execute_plan(plan)
        self.assertEqual(result_plan.status, PlanStatus.PAUSED)
        self.assertEqual(plan.steps[2].status, StepStatus.BLOCKED)

        # 5. User confirms the action -> step unblocked and plan completes
        plan.steps[2].status = StepStatus.PENDING
        # Allow restart_server for the confirmed execution
        self.engine.gateway.policy_engine.CONFIRM_TOOLS.discard("restart_server")
        self.engine.gateway.policy_engine.ALLOWED_TOOLS.add("restart_server")
        resumed_plan = await self.engine.executor.execute_plan(plan)
        self.assertEqual(resumed_plan.status, PlanStatus.COMPLETED)
        self.assertTrue(all(s.status == StepStatus.COMPLETED for s in resumed_plan.steps))


if __name__ == "__main__":
    unittest.main()
