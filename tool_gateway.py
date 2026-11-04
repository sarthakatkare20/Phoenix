"""
Tool Gateway and Security Policy Engine for Paaro.
Enforces ALLOW / CONFIRM / DENY permission boundaries before any tool execution.
"""

from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("paaro.gateway")


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class PolicyEngine:
    """
    Evaluates requested tool actions against safety rules and policies.
    """

    # Safe read-only and harmless operations
    ALLOWED_TOOLS = {
        "get_time",
        "get_system_stats",
        "search",
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
        "play_music",
        "media_control",
        "volume_control",
        "memory_store",
        "memory_search",
        "memory_delete",
        "inspect_project",
        "read_file",
        "list_directory",
        "run_tests",
        "check_logs",
        "check_server_status",
        "verify_endpoint",
        "analyze_test_failures",
        "hermes_task",
        "delegate_hermes",
        "hermes_agent",
        "coding_task",
        "research_task",
        "make_phone_call",
        "call_user",
        "phone_call",
        "send_to_antigravity",
        "antigravity_prompt",
        "ask_antigravity",
        "open_chrome",
        "search_in_chrome",
        "open_in_chrome",
    }

    # Destructive or outward-facing actions requiring user confirmation
    CONFIRM_TOOLS = {
        "close_app",
        "stop_process",
        "delete_file",
        "send_email",
        "system_shutdown",
        "execute_shell",
        "modify_system_setting",
        "modify_code",
        "restart_server",
        "write_file",
        "install_dependency",
    }

    # Explicitly forbidden tools
    DENIED_TOOLS = {
        "format_disk",
        "disable_antivirus",
        "leak_secrets",
        "shutdown_system",
        "delete_system_files",
        "modify_security_policy",
        "credential_access",
        "run_shell",
    }

    def evaluate(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> PolicyDecision:
        name = tool_name.lower().strip()

        if name in self.DENIED_TOOLS:
            logger.warning("PolicyEngine DENIED tool execution: '%s'", tool_name)
            return PolicyDecision.DENY

        if name in self.CONFIRM_TOOLS:
            logger.info("PolicyEngine requires CONFIRMATION for tool: '%s'", tool_name)
            return PolicyDecision.CONFIRM

        if name in self.ALLOWED_TOOLS:
            return PolicyDecision.ALLOW

        # Unknown tools default to CONFIRM for safety
        logger.info("Unknown tool '%s' defaulted to CONFIRM by policy", tool_name)
        return PolicyDecision.CONFIRM


class ToolGateway:
    """
    Central gateway through which all LLM tool requests must pass.
    Guarantees no tool runs without policy evaluation.
    """

    def __init__(self, policy_engine: Optional[PolicyEngine] = None):
        self.policy_engine = policy_engine or PolicyEngine()
        self._custom_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}

    def register_handler(self, tool_name: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self._custom_handlers[tool_name.lower().strip()] = handler

    def evaluate_tool_call(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> PolicyDecision:
        return self.policy_engine.evaluate(tool_name, args)

    def execute_allowed(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute tool if permitted by policy.
        """
        decision = self.evaluate_tool_call(tool_name, args)
        if decision == PolicyDecision.DENY:
            return {
                "status": "error",
                "policy": "deny",
                "error": f"Tool '{tool_name}' is denied by system security policy."
            }

        if decision == PolicyDecision.CONFIRM:
            call_id = f"conf_{int(time.time() * 1000)}"
            self._pending_confirmations[call_id] = {"tool": tool_name, "args": args or {}}
            return {
                "status": "pending_confirmation",
                "call_id": call_id,
                "tool": tool_name,
                "policy": "confirm",
                "message": f"Action '{tool_name}' requires explicit user confirmation."
            }

        # Policy == ALLOW
        name_key = tool_name.lower().strip()
        handler = self._custom_handlers.get(name_key)
        if handler:
            try:
                res = handler(args or {})
                return {"status": "success", "policy": "allow", "result": res}
            except Exception as e:
                logger.error("Error executing handler for '%s': %s", tool_name, e)
                return {"status": "error", "policy": "allow", "error": str(e)}

        # Default mock simulation if no custom handler is registered
        return {
            "status": "success",
            "policy": "allow",
            "result": f"Executed action '{tool_name}' with args {args or {}}."
        }

    def resolve_confirmation(self, call_id: str, approved: bool) -> Dict[str, Any]:
        """Resolve a pending confirmation."""
        pending = self._pending_confirmations.pop(call_id, None)
        if not pending:
            return {"status": "error", "error": f"No pending confirmation with ID '{call_id}'."}

        tool_name = pending["tool"]
        args = pending["args"]

        if not approved:
            return {
                "status": "denied_by_user",
                "tool": tool_name,
                "message": f"User cancelled execution of '{tool_name}'."
            }

        name_key = tool_name.lower().strip()
        handler = self._custom_handlers.get(name_key)
        if handler:
            try:
                res = handler(args)
                return {"status": "success", "confirmed": True, "result": res}
            except Exception as e:
                return {"status": "error", "confirmed": True, "error": str(e)}

        return {
            "status": "success",
            "confirmed": True,
            "result": f"Confirmed and executed '{tool_name}' with args {args}."
        }


    def register_computer_tools(self, controller: Optional[Any] = None) -> None:
        """Register handlers for all Step 9 Computer Control tools."""
        if controller is None:
            try:
                from computer import computer_controller
                controller = computer_controller
            except ImportError:
                logger.warning("paaro.computer module not available for tool registration")
                return

        self.register_handler("open_app", lambda args: controller.open_app(args.get("target") or args.get("app_name") or args.get("app", ""), args=args.get("args")).to_dict())
        self.register_handler("close_app", lambda args: controller.close_app(args.get("target") or args.get("app_name") or args.get("app", ""), force=bool(args.get("force", False))).to_dict())
        self.register_handler("open_folder", lambda args: controller.open_folder(args.get("target") or args.get("folder_path") or args.get("path", ".")).to_dict())
        self.register_handler("open_file", lambda args: controller.open_file(args.get("target") or args.get("file_path") or args.get("path", "")).to_dict())
        self.register_handler("open_url", lambda args: controller.open_url(args.get("target") or args.get("url", "")).to_dict())
        self.register_handler("start_process", lambda args: controller.start_process(args.get("target") or args.get("service_name") or args.get("process", ""), args=args.get("args"), cwd=args.get("cwd")).to_dict())
        self.register_handler("stop_process", lambda args: controller.stop_process(args.get("target") or args.get("process") or args.get("target_name_or_pid", ""), pid=args.get("pid"), force=bool(args.get("force", False))).to_dict())
        self.register_handler("check_process", lambda args: controller.check_process(args.get("target") or args.get("process", "")))
        self.register_handler("get_process_list", lambda args: {"processes": [p.to_dict() for p in controller.get_process_list(max_count=int(args.get("max_count", 50)), filter_name=args.get("filter"))]})
        self.register_handler("list_processes", lambda args: {"processes": [p.to_dict() for p in controller.get_process_list(max_count=int(args.get("max_count", 50)), filter_name=args.get("filter"))]})
        self.register_handler("focus_app", lambda args: controller.focus_app(args.get("target") or args.get("app_name") or args.get("app", "")).to_dict())
        self.register_handler("get_system_state", lambda args: controller.get_system_state())

    def register_telephony_tools(self) -> None:
        """Register outbound voice calling handlers."""
        try:
            from telephony import make_phone_call

            def _call_handler(args: Dict[str, Any]) -> Dict[str, Any]:
                msg = args.get("message") or args.get("text") or args.get("prompt") or "Phoenix priority transmission."
                to_num = args.get("to") or args.get("number") or args.get("phone")
                voice = args.get("voice") or "Polly.Brian"
                return make_phone_call(message=msg, to_number=to_num, voice=voice)

            for t_name in ["make_phone_call", "call_user", "phone_call"]:
                self.register_handler(t_name, _call_handler)
            logger.info("Telephony voice call tools successfully registered in ToolGateway.")
        except Exception as e:
            logger.warning("Could not register Telephony tools: %s", e)
        """Register autonomous Hermes Agent execution handlers."""
        try:
            from hermes_client import execute_hermes
            import os

            def _hermes_handler(args: Dict[str, Any]) -> Dict[str, Any]:
                query = args.get("query") or args.get("task") or args.get("prompt") or args.get("target") or ""
                cwd = args.get("cwd") or os.getcwd()
                return execute_hermes(query, cwd=cwd)

            for t_name in ["hermes_task", "delegate_hermes", "hermes_agent", "coding_task", "research_task"]:
                self.register_handler(t_name, _hermes_handler)
            logger.info("Hermes Agent tools successfully registered in ToolGateway.")
        except Exception as e:
            logger.warning("Could not register Hermes tools: %s", e)


    def register_visual_tools(self) -> None:
        """Register visual screen automation tools (Chrome open, Antigravity prompt injection)."""
        try:
            from visual_control import open_chrome_visual, send_to_antigravity

            def _chrome_handler(args: Dict[str, Any]) -> Dict[str, Any]:
                target = args.get("target") or args.get("url") or args.get("query") or ""
                return open_chrome_visual(target)

            def _antigravity_handler(args: Dict[str, Any]) -> Dict[str, Any]:
                prompt = args.get("prompt") or args.get("query") or args.get("task") or args.get("text") or ""
                return send_to_antigravity(prompt)

            for t_name in ["open_chrome", "search_in_chrome", "open_in_chrome"]:
                self.register_handler(t_name, _chrome_handler)
            for t_name in ["send_to_antigravity", "antigravity_prompt", "ask_antigravity"]:
                self.register_handler(t_name, _antigravity_handler)
            logger.info("Visual automation tools successfully registered in ToolGateway.")
        except Exception as e:
            logger.warning("Could not register visual automation tools: %s", e)

# Global ToolGateway singleton
tool_gateway = ToolGateway()
try:
    tool_gateway.register_computer_tools()
except Exception as e:
    logger.debug("Deferred computer tool registration: %s", e)

try:
    tool_gateway.register_hermes_tools()
except Exception as e:
    logger.debug("Deferred hermes tool registration: %s", e)

try:
    tool_gateway.register_telephony_tools()
except Exception as e:
    logger.debug("Deferred telephony tool registration: %s", e)

try:
    tool_gateway.register_visual_tools()
except Exception as e:
    logger.debug("Deferred computer tool registration: %s", e)

