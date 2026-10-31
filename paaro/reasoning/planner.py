"""
Plan Generator and Plan Validator for Paaro Reasoning Engine (Step 8).
Generates structured execution plans with dependency validation and safety boundaries.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import ExecutionPlan, PlanStep, StepStatus
from ..streaming_llm import StreamingLLM
from ..tool_gateway import PolicyEngine, ToolGateway, tool_gateway

logger = logging.getLogger("paaro.reasoning.planner")


class PlanValidator:
    """
    Validates structural integrity, dependency acyclicity, and tool authorization of ExecutionPlans.
    """

    def __init__(
        self,
        max_steps: int = 8,
        policy_engine: Optional[PolicyEngine] = None,
    ):
        self.max_steps = max_steps
        self.policy_engine = policy_engine or PolicyEngine()

    def validate(self, plan: ExecutionPlan) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        if not plan.steps:
            errors.append("Plan contains no steps.")
            return False, errors

        if len(plan.steps) > self.max_steps:
            errors.append(f"Plan exceeds maximum allowed steps ({len(plan.steps)} > {self.max_steps}).")

        step_ids: Set[str] = set()
        for step in plan.steps:
            if not step.id or not isinstance(step.id, str):
                errors.append(f"Invalid step ID: '{step.id}'")
            elif step.id in step_ids:
                errors.append(f"Duplicate step ID: '{step.id}'")
            else:
                step_ids.add(step.id)

            if not step.action or not isinstance(step.action, str):
                errors.append(f"Step '{step.id}' has missing or invalid action.")
            elif (
                step.action not in self.policy_engine.ALLOWED_TOOLS
                and step.action not in self.policy_engine.CONFIRM_TOOLS
            ):
                errors.append(f"Unsupported or unauthorized action '{step.action}' in step '{step.id}'.")

            # Validate dependencies reference defined step IDs
            for dep in step.depends_on:
                if dep == step.id:
                    errors.append(f"Step '{step.id}' cannot depend on itself.")
                elif not any(s.id == dep for s in plan.steps):
                    errors.append(f"Step '{step.id}' depends on nonexistent step '{dep}'.")

        # Cycle detection via topological sort
        if not errors:
            cycle_err = self._check_cycles(plan.steps)
            if cycle_err:
                errors.append(cycle_err)

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("[REASONING] Plan validation failed: %s", "; ".join(errors))
        return is_valid, errors

    def _check_cycles(self, steps: List[PlanStep]) -> Optional[str]:
        """Detect dependency cycles using Kahn's algorithm."""
        in_degree: Dict[str, int] = {s.id: 0 for s in steps}
        graph: Dict[str, List[str]] = {s.id: [] for s in steps}

        for s in steps:
            for dep in s.depends_on:
                if dep in graph:
                    graph[dep].append(s.id)
                    in_degree[s.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            node = queue.pop(0)
            visited_count += 1
            for neighbor in graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(steps):
            return "Cycle detected: Plan dependency graph contains a cyclic dependency loop."
        return None


class PlanGenerator:
    """
    Synthesizes structured ExecutionPlans from user goals using deterministic templates or LLM reasoning.
    """

    def __init__(
        self,
        llm: Optional[StreamingLLM] = None,
        validator: Optional[PlanValidator] = None,
        max_steps: int = 8,
    ):
        self.llm = llm
        self.validator = validator or PlanValidator(max_steps=max_steps)
        self.max_steps = max_steps

    def generate_plan(self, goal: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """
        Generate and validate an execution plan for a goal.
        """
        # 1. Check deterministic templates
        plan = self._generate_deterministic_plan(goal, context)
        if plan:
            is_valid, errors = self.validator.validate(plan)
            if is_valid:
                logger.info("[REASONING] Generated deterministic plan '%s' (%d steps)", plan.id, len(plan.steps))
                return plan

        # 2. Default structured fallback plan
        fallback_plan = self._build_default_plan(goal)
        is_valid, _ = self.validator.validate(fallback_plan)
        if is_valid:
            return fallback_plan

        return ExecutionPlan(
            goal=goal,
            steps=[PlanStep(id="step_1", description=f"Execute: {goal}", action="search", args={"query": goal})],
        )

    async def generate(
        self, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> ExecutionPlan:
        """Alias for generate_plan_async."""
        return await self.generate_plan_async(goal, context)

    async def generate_plan_async(
        self, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> ExecutionPlan:
        """
        Async plan generation with LLM support if deterministic template does not match.
        """
        plan = self._generate_deterministic_plan(goal, context)
        if plan:
            is_valid, _ = self.validator.validate(plan)
            if is_valid:
                return plan

        if self.llm:
            try:
                llm_plan = await self._generate_with_llm(goal, context)
                if llm_plan:
                    is_valid, errors = self.validator.validate(llm_plan)
                    if is_valid:
                        logger.info("[REASONING] Generated LLM plan '%s' (%d steps)", llm_plan.id, len(llm_plan.steps))
                        return llm_plan
            except Exception as e:
                logger.error("Error generating LLM plan: %s", e)

        return self.generate_plan(goal, context)

    def _generate_deterministic_plan(
        self, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[ExecutionPlan]:
        text = goal.strip().lower()

        # Pattern 1: Restart server / backend and verify (when not an app launch workflow)
        if (
            ("restart" in text or ("start" in text and "backend" in text and not ("vs code" in text or "vscode" in text)) or "stopped" in text)
            and any(w in text for w in ["server", "backend"])
            and not ("vs code" in text or "vscode" in text or "chrome" in text)
        ):
            steps = [
                PlanStep(id="step_1", description="Check current server and process status", action="check_server_status", args={"port": 8000}),
                PlanStep(id="step_2", description="Check recent server log records", action="check_logs", args={"service": "backend"}, depends_on=["step_1"]),
                PlanStep(id="step_3", description="Identify issue and restart server process", action="restart_server", args={"port": 8000}, depends_on=["step_2"]),
                PlanStep(id="step_4", description="Verify server responsiveness on port 8000", action="verify_endpoint", args={"port": 8000, "endpoint": "/health"}, depends_on=["step_3"]),
            ]
            return ExecutionPlan(goal=goal, steps=steps, context_data=context or {})

        # Pattern 2: Diagnose test failures and fix
        if "test" in text and any(w in text for w in ["fix", "resolve", "make sure pass", "failing", "diagnose"]):
            steps = [
                PlanStep(id="step_1", description="Inspect repository status", action="inspect_project", args={"path": "."}),
                PlanStep(id="step_2", description="Run test suite", action="run_tests", args={"suite": "all"}, depends_on=["step_1"]),
                PlanStep(id="step_3", description="Analyze failure output", action="analyze_test_failures", args={}, depends_on=["step_2"]),
                PlanStep(id="step_4", description="Apply safe code modification", action="modify_code", args={"fix_target": "tests"}, depends_on=["step_3"]),
                PlanStep(id="step_5", description="Re-run test suite", action="run_tests", args={"suite": "all"}, depends_on=["step_4"]),
            ]
            return ExecutionPlan(goal=goal, steps=steps, context_data=context or {})

        # Pattern 3: Check project, run tests and report/analyze
        if any(p in text for p in ["check my paaro", "check project", "check repo", "run"]) and "test" in text:
            steps = [
                PlanStep(id="step_1", description="Inspect repository status", action="inspect_project", args={"path": "."}),
                PlanStep(id="step_2", description="Run test suite", action="run_tests", args={"suite": "all"}, depends_on=["step_1"]),
                PlanStep(id="step_3", description="Analyze test execution results", action="analyze_test_failures", args={}, depends_on=["step_2"]),
            ]
            return ExecutionPlan(goal=goal, steps=steps, context_data=context or {})

        # Pattern 4: Computer Control - Open VS Code, open project, and check/start backend
        if "vs code" in text or "vscode" in text or "code" in text:
            if "paaro" in text or "project" in text:
                if "check" in text or "running" in text or "status" in text:
                    steps = [
                        PlanStep(id="step_1", description="Launch or focus Visual Studio Code", action="open_app", args={"target": "vscode"}),
                        PlanStep(id="step_2", description="Open Paaro project folder", action="open_folder", args={"target": "paaro_project"}, depends_on=["step_1"]),
                        PlanStep(id="step_3", description="Check if Paaro backend service is running", action="check_process", args={"target": "paaro_backend"}, depends_on=["step_2"]),
                    ]
                    return ExecutionPlan(goal=goal, steps=steps, context_data=context or {})
                elif "start" in text or "backend" in text:
                    steps = [
                        PlanStep(id="step_1", description="Launch or focus Visual Studio Code", action="open_app", args={"target": "vscode"}),
                        PlanStep(id="step_2", description="Open Paaro project folder", action="open_folder", args={"target": "paaro_project"}, depends_on=["step_1"]),
                        PlanStep(id="step_3", description="Start Paaro backend service", action="start_process", args={"target": "paaro_backend"}, depends_on=["step_2"]),
                        PlanStep(id="step_4", description="Verify backend process started successfully", action="check_process", args={"target": "paaro_backend"}, depends_on=["step_3"]),
                    ]
                    return ExecutionPlan(goal=goal, steps=steps, context_data=context or {})

        # Pattern 5: Computer Control - Open Chrome and open URL
        if "chrome" in text or "browser" in text:
            if "http" in text or "url" in text or "github" in text or "google" in text:
                url = "https://github.com" if "github" in text else ("https://google.com" if "google" in text else "https://example.com")
                url_match = re.search(r"https?://[^\s]+", goal)
                if url_match:
                    url = url_match.group(0)
                steps = [
                    PlanStep(id="step_1", description="Launch Google Chrome", action="open_app", args={"target": "chrome"}),
                    PlanStep(id="step_2", description=f"Open URL '{url}'", action="open_url", args={"target": url}, depends_on=["step_1"]),
                ]
                return ExecutionPlan(goal=goal, steps=steps, context_data=context or {})

        return None

    def _build_default_plan(self, goal: str) -> ExecutionPlan:
        steps = [
            PlanStep(id="step_1", description="Inspect environment context", action="inspect_project", args={"goal": goal}),
            PlanStep(id="step_2", description=f"Execute task action for: {goal}", action="open_app", args={"target": goal}, depends_on=["step_1"]),
            PlanStep(id="step_3", description="Verify outcome", action="verify_endpoint", args={}, depends_on=["step_2"]),
        ]
        return ExecutionPlan(goal=goal, steps=steps)

    async def _generate_with_llm(
        self, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[ExecutionPlan]:
        if not self.llm:
            return None

        prompt = (
            "Create a strict JSON multi-step execution plan to achieve the following goal.\n"
            f"Goal: \"{goal}\"\n\n"
            "Allowed actions: [inspect_project, read_file, list_directory, run_tests, check_logs, "
            "check_server_status, verify_endpoint, analyze_test_failures, modify_code, restart_server, open_app].\n\n"
            "Format your response as a valid JSON object ONLY:\n"
            "{\n"
            '  "goal": "' + goal + '",\n'
            '  "steps": [\n'
            '    {"id": "step_1", "description": "...", "action": "...", "args": {}, "depends_on": []},\n'
            '    {"id": "step_2", "description": "...", "action": "...", "args": {}, "depends_on": ["step_1"]}\n'
            "  ]\n"
            "}\n"
            "Ensure step IDs are unique, dependencies reference valid prior IDs, and at most 6 steps."
        )

        full_text = ""
        async for delta in self.llm.stream_response(prompt):
            if isinstance(delta, dict) and delta.get("status") == "delta":
                full_text += delta.get("text", "")
            elif isinstance(delta, str):
                full_text += delta

        # Extract JSON from output
        json_match = re.search(r"\{[\s\S]*\}", full_text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                steps_data = data.get("steps", [])
                steps = [PlanStep.from_dict(sd) for sd in steps_data]
                return ExecutionPlan(goal=goal, steps=steps, context_data=context or {})
            except Exception as e:
                logger.error("Failed to parse LLM JSON plan: %s", e)

        return None
