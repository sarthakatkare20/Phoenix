"""
Comprehensive Test Suite for Paaro Step 9: Basic Computer Control.
Tests application registry, alias resolution, process check/supervision, safe path containment,
URL scheme whitelisting, Tool Gateway & Policy Engine enforcement, Reasoning Engine integration,
Proactive Engine integration, and Emergency Stop safety boundaries.
"""

import asyncio
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from paaro.config import PaaroSettings
from paaro.security import SecurityContext
from paaro.tool_gateway import PolicyDecision, PolicyEngine, ToolGateway
from paaro.computer.models import (
    ComputerAction,
    ComputerActionResult,
    ComputerActionType,
    ComputerVerificationResult,
)
from paaro.computer.apps import ApplicationRegistry
from paaro.computer.filesystem import SafePathResolver
from paaro.computer.urls import SafeUrlOpener
from paaro.computer.processes import ProcessController
from paaro.computer.controller import ComputerController
from paaro.reasoning.models import ExecutionPlan, PlanStatus, PlanStep, StepStatus, TaskComplexity
from paaro.reasoning.classifier import TaskComplexityClassifier
from paaro.reasoning.planner import PlanGenerator, PlanValidator
from paaro.reasoning.executor import PlanExecutor
from paaro.reasoning.engine import ReasoningEngine
from paaro.proactive.events import EventSeverity, ProactiveEvent


class TestApplicationRegistry(unittest.TestCase):
    """Test desktop application registry, natural language alias resolution, and lifecycle."""

    def setUp(self):
        self.registry = ApplicationRegistry()

    def test_alias_resolution(self):
        # Exact ID
        res = self.registry.resolve_app("chrome")
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "chrome")

        # Aliases
        res_alias1 = self.registry.resolve_app("google chrome")
        self.assertIsNotNone(res_alias1)
        self.assertEqual(res_alias1[0], "chrome")

        res_alias2 = self.registry.resolve_app("browser")
        self.assertIsNotNone(res_alias2)
        self.assertEqual(res_alias2[0], "chrome")

        res_vscode = self.registry.resolve_app("vs code")
        self.assertIsNotNone(res_vscode)
        self.assertEqual(res_vscode[0], "vscode")

        res_spotify = self.registry.resolve_app("music app")
        self.assertIsNotNone(res_spotify)
        self.assertEqual(res_spotify[0], "spotify")

    def test_unknown_app_rejected(self):
        res = self.registry.launch_app("nonexistent_fake_app_xyz_999")
        self.assertFalse(res.success)
        self.assertEqual(res.error, "application_not_found")
        self.assertIsNotNone(res.verification)
        self.assertFalse(res.verification.verified)

    @patch("subprocess.Popen")
    @patch.object(ApplicationRegistry, "is_app_running")
    @patch.object(ApplicationRegistry, "find_executable", return_value="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
    def test_launch_app_success(self, mock_find, mock_is_running, mock_popen):
        mock_proc = MagicMock()
        mock_proc.pid = 4321
        mock_popen.return_value = mock_proc
        # First check not running, then running after launch
        mock_is_running.side_effect = [(False, None), (True, 4321)]

        result = self.registry.launch_app("chrome")
        self.assertTrue(result.success)
        self.assertEqual(result.action, "open_app")
        self.assertEqual(result.pid, 4321)
        self.assertIsNotNone(result.verification)
        self.assertTrue(result.verification.verified)

    @patch("psutil.Process")
    @patch("psutil.process_iter")
    def test_close_app_success(self, mock_iter, mock_process_cls):
        mock_p = MagicMock()
        mock_p.pid = 9876
        mock_p.info = {"name": "spotify.exe", "pid": 9876}
        mock_iter.return_value = [mock_p]

        mock_proc_obj = MagicMock()
        mock_process_cls.return_value = mock_proc_obj

        with patch.object(self.registry, "is_app_running", return_value=(False, None)):
            result = self.registry.close_app("spotify")
            self.assertTrue(result.success)
            self.assertEqual(result.action, "close_app")
            self.assertIn(9876, result.result["terminated_pids"])
            self.assertTrue(result.verification.verified)

    def test_get_all_apps(self):
        apps = self.registry.get_all_apps()
        self.assertIsInstance(apps, list)
        self.assertGreaterEqual(len(apps), 5)
        names = [a.name for a in apps]
        self.assertIn("Google Chrome", names)
        self.assertIn("Visual Studio Code", names)


class TestSafePathResolver(unittest.TestCase):
    """Test filesystem containment, directory resolution, and path traversal rejection."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.allowed_roots = [os.path.realpath(self.temp_dir), os.path.realpath("F:\\jarvis")]
        self.resolver = SafePathResolver(allowed_roots=self.allowed_roots)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_allowed_directory_resolution(self):
        sub_dir = os.path.join(self.temp_dir, "my_project")
        os.makedirs(sub_dir, exist_ok=True)

        is_safe, resolved, err = self.resolver.resolve_safe_path(sub_dir)
        self.assertTrue(is_safe, f"Path should be safe: {err}")
        self.assertEqual(os.path.realpath(sub_dir), resolved)

    def test_path_traversal_blocked(self):
        # Attempt to escape via ../
        dangerous_path = os.path.join(self.temp_dir, "..", "..", "Windows", "System32")
        is_safe, resolved, err = self.resolver.resolve_safe_path(dangerous_path)
        self.assertFalse(is_safe)
        self.assertIn("outside approved directories", err)

    def test_sensitive_file_rejected(self):
        # Attempt to access sensitive filename
        sensitive_path = os.path.join(self.temp_dir, "passwords.txt")
        is_safe, resolved, err = self.resolver.resolve_safe_path(sensitive_path, must_exist=False)
        self.assertFalse(is_safe)
        self.assertIn("restricted sensitive file", err)

        key_path = os.path.join(self.temp_dir, "id_rsa")
        is_safe2, resolved2, err2 = self.resolver.resolve_safe_path(key_path, must_exist=False)
        self.assertFalse(is_safe2)
        self.assertIn("restricted sensitive file", err2)

    @patch("subprocess.Popen")
    def test_open_folder_success(self, mock_popen):
        folder = os.path.join(self.temp_dir, "docs")
        os.makedirs(folder, exist_ok=True)

        res = self.resolver.open_folder(folder)
        self.assertTrue(res.success)
        self.assertEqual(res.action, "open_folder")
        self.assertTrue(res.verification.verified)

    def test_open_folder_traversal_error(self):
        res = self.resolver.open_folder("../../../Windows")
        self.assertFalse(res.success)
        self.assertIn("outside approved directories", res.error)


class TestSafeUrlOpener(unittest.TestCase):
    """Test URL scheme whitelisting and protocol injection defense."""

    def setUp(self):
        self.opener = SafeUrlOpener()

    def test_valid_https_url(self):
        is_valid, norm_url, err = self.opener.validate_url("https://github.com/torvalds/linux")
        self.assertTrue(is_valid)
        self.assertEqual(norm_url, "https://github.com/torvalds/linux")
        self.assertIsNone(err)

    def test_valid_http_url(self):
        is_valid, norm_url, err = self.opener.validate_url("http://localhost:3000/dashboard")
        self.assertTrue(is_valid)
        self.assertEqual(norm_url, "http://localhost:3000/dashboard")

    def test_dangerous_schemes_blocked(self):
        # file:// scheme blocked
        is_valid, _, err = self.opener.validate_url("file:///C:/Windows/System32/calc.exe")
        self.assertFalse(is_valid)
        self.assertIn("forbidden for security", err)

        # javascript: blocked
        is_valid, _, err = self.opener.validate_url("javascript:alert(document.cookie)")
        self.assertFalse(is_valid)
        self.assertIn("forbidden for security", err)

        # data: blocked
        is_valid, _, err = self.opener.validate_url("data:text/html,<script>alert(1)</script>")
        self.assertFalse(is_valid)
        self.assertIn("forbidden for security", err)

    def test_malformed_url_blocked(self):
        is_valid, _, err = self.opener.validate_url("htp:/bad-url")
        self.assertFalse(is_valid)
        self.assertIsNotNone(err)

    @patch("webbrowser.open")
    def test_open_url_success(self, mock_wb_open):
        mock_wb_open.return_value = True
        res = self.opener.open_url("https://google.com")
        self.assertTrue(res.success)
        self.assertEqual(res.action, "open_url")
        self.assertTrue(res.verification.verified)


class TestProcessController(unittest.TestCase):
    """Test process inspection, service supervision, and OS critical process protection."""

    def setUp(self):
        self.controller = ProcessController()

    def test_list_processes(self):
        procs = self.controller.get_process_list(max_count=10)
        self.assertIsInstance(procs, list)
        self.assertGreater(len(procs), 0)
        self.assertIsInstance(procs[0].pid, int)
        self.assertIsInstance(procs[0].name, str)

    def test_check_process(self):
        # Check current python process
        res = self.controller.check_process("python")
        self.assertIsInstance(res, dict)
        self.assertTrue(res["running"])
        self.assertGreater(res["count"], 0)

        # Check nonexistent process
        res_fake = self.controller.check_process("nonexistent_process_abc_123")
        self.assertFalse(res_fake["running"])
        self.assertEqual(res_fake["count"], 0)

    def test_critical_process_protection(self):
        # Attempt to stop critical system process like csrss or svchost
        res = self.controller.stop_process("csrss.exe")
        self.assertFalse(res.success)
        self.assertIn("critical OS process", res.error)

    def test_get_system_state(self):
        state = self.controller.get_system_state()
        self.assertIsInstance(state.cpu_percent, float)
        self.assertIsInstance(state.memory_percent, float)
        self.assertGreater(state.memory_total_gb, 0.0)


class TestComputerController(unittest.TestCase):
    """Test central ComputerController action routing, verification, and event broadcasting."""

    def setUp(self):
        self.controller = ComputerController()
        self.events = []
        self.controller.add_listener(lambda e: self.events.append(e))

    def test_execute_system_state_action(self):
        action = ComputerAction(action_type=ComputerActionType.GET_SYSTEM_STATE)
        res = self.controller.execute_action(action)
        self.assertTrue(res.success)
        self.assertEqual(res.action, "get_system_state")
        self.assertIsNotNone(res.verification)
        self.assertTrue(res.verification.verified)

        # Verify events were dispatched
        types = [e["type"] for e in self.events]
        self.assertIn("computer_action_started", types)
        self.assertIn("computer_action_completed", types)

    def test_execute_check_process_action(self):
        action = ComputerAction(action_type=ComputerActionType.CHECK_PROCESS, target="python")
        res = self.controller.execute_action(action)
        self.assertTrue(res.success)
        self.assertEqual(res.action, "check_process")
        self.assertTrue(res.result["running"])


class TestToolGatewayComputerPolicy(unittest.TestCase):
    """Test security policy enforcement for all Step 9 computer control tools."""

    def setUp(self):
        self.engine = PolicyEngine()
        self.gateway = ToolGateway(policy_engine=self.engine)
        self.mock_controller = MagicMock()
        self.gateway.register_computer_tools(controller=self.mock_controller)

    def test_allowed_computer_tools(self):
        allowed = [
            "open_app",
            "open_folder",
            "open_file",
            "open_url",
            "check_process",
            "get_process_list",
            "list_processes",
            "get_system_state",
            "focus_app",
            "start_process",
        ]
        for tool in allowed:
            decision = self.engine.evaluate(tool)
            self.assertEqual(decision, PolicyDecision.ALLOW, f"Tool '{tool}' should be ALLOWED")

    def test_confirm_computer_tools(self):
        confirm = [
            "close_app",
            "stop_process",
            "restart_server",
        ]
        for tool in confirm:
            decision = self.engine.evaluate(tool)
            self.assertEqual(decision, PolicyDecision.CONFIRM, f"Tool '{tool}' should require CONFIRMATION")

    def test_denied_tools(self):
        denied = [
            "format_disk",
            "disable_antivirus",
            "leak_secrets",
            "shutdown_system",
            "delete_system_files",
            "modify_security_policy",
            "credential_access",
            "run_shell",
        ]
        for tool in denied:
            decision = self.engine.evaluate(tool)
            self.assertEqual(decision, PolicyDecision.DENY, f"Tool '{tool}' should be DENIED")

    def test_execute_denied_tool_returns_error(self):
        res = self.gateway.execute_allowed("format_disk")
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["policy"], "deny")

    def test_execute_confirm_tool_holds_pending(self):
        res = self.gateway.execute_allowed("close_app", {"target": "spotify"})
        self.assertEqual(res["status"], "pending_confirmation")
        self.assertEqual(res["policy"], "confirm")
        call_id = res["call_id"]

        # Confirm and resolve
        self.mock_controller.close_app.return_value = ComputerActionResult(
            success=True, action="close_app", target="spotify"
        )
        resolved = self.gateway.resolve_confirmation(call_id, approved=True)
        self.assertEqual(resolved["status"], "success")
        self.assertTrue(resolved["confirmed"])


class TestReasoningComputerIntegration(unittest.IsolatedAsyncioTestCase):
    """Test Step 8 Reasoning Engine planning and execution of multi-step computer tasks."""

    async def asyncSetUp(self):
        self.planner = PlanGenerator()
        self.security = SecurityContext()
        self.engine = PolicyEngine()
        self.gateway = ToolGateway(policy_engine=self.engine)
        self.executor = PlanExecutor(gateway=self.gateway, security=self.security)

    async def test_multistep_computer_plan_generation(self):
        goal = "Open VS Code, open my Paaro project and check whether the backend is running"
        plan = self.planner.generate_plan(goal)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[0].action, "open_app")
        self.assertEqual(plan.steps[1].action, "open_folder")
        self.assertEqual(plan.steps[2].action, "check_process")

    async def test_multistep_computer_plan_execution(self):
        goal = "Open Chrome and open this URL"
        plan = self.planner.generate_plan(goal)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].action, "open_app")
        self.assertEqual(plan.steps[1].action, "open_url")

        # Execute plan with mock handler
        executed_actions = []
        self.gateway.register_handler("open_app", lambda args: executed_actions.append("open_app") or {"status": "ok"})
        self.gateway.register_handler("open_url", lambda args: executed_actions.append("open_url") or {"status": "ok"})

        completed_plan = await self.executor.execute_plan(plan)
        self.assertEqual(completed_plan.status, PlanStatus.COMPLETED)
        self.assertEqual(executed_actions, ["open_app", "open_url"])


class TestProactiveComputerIntegration(unittest.IsolatedAsyncioTestCase):
    """Test Step 7 Proactive Engine triggering computer control workflows."""

    async def test_service_stopped_proactive_workflow(self):
        # When proactive event detects server down
        event = ProactiveEvent(
            event_type="backend_service_stopped",
            source="process_monitor",
            severity=EventSeverity.HIGH,
            data={"process": "paaro_backend"},
        )
        self.assertEqual(event.event_type, "backend_service_stopped")
        self.assertEqual(event.severity, EventSeverity.HIGH)

        # Plan generated to restart backend
        planner = PlanGenerator()
        plan = planner.generate_plan("Restart server and verify")
        self.assertIsNotNone(plan)
        actions = [s.action for s in plan.steps]
        self.assertIn("check_server_status", actions)
        self.assertIn("restart_server", actions)


class TestEmergencyStopComputerControl(unittest.IsolatedAsyncioTestCase):
    """Test emergency stop halts active computer control plans."""

    async def asyncSetUp(self):
        self.security = SecurityContext()
        self.gateway = ToolGateway()
        self.executor = PlanExecutor(gateway=self.gateway, security=self.security)

    async def test_emergency_stop_cancels_computer_plan(self):
        steps = [
            PlanStep(id="step_1", description="Open App", action="open_app", args={"target": "chrome"}),
            PlanStep(id="step_2", description="Open URL", action="open_url", args={"target": "https://google.com"}, depends_on=["step_1"]),
        ]
        plan = ExecutionPlan(goal="Test emergency stop", steps=steps)

        # Trigger emergency stop before execution
        self.security.trigger_emergency_stop("User emergency halt")
        completed_plan = await self.executor.execute_plan(plan)

        self.assertIn(completed_plan.status, [PlanStatus.CANCELLED, PlanStatus.FAILED])
        self.assertEqual(completed_plan.steps[0].status, StepStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
