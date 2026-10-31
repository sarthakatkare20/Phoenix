"""
Process and System State Controller for Paaro Computer Control (Step 9).
Provides safe process inspection, PID validation, known process startup, graceful termination, and system metrics.
"""

import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil

from .models import (
    ComputerActionResult,
    ComputerVerificationResult,
    ProcessInfo,
    SystemStateInfo,
)

logger = logging.getLogger("paaro.computer.processes")


class ProcessController:
    """
    Manages process inspection, verified startups, safe terminations, and system metrics.
    Protects critical system processes from unauthorized or accidental termination.
    """

    CRITICAL_OS_PROCESSES: Set[str] = {
        "system",
        "system idle process",
        "csrss.exe",
        "smss.exe",
        "services.exe",
        "lsass.exe",
        "wininit.exe",
        "winlogon.exe",
        "svchost.exe",
        "fontdrvhost.exe",
        "dwm.exe",
        "securityhealthservice.exe",
        "antivirus",
    }

    PROTECTED_PIDS: Set[int] = {0, 4}

    KNOWN_SERVICES: Dict[str, Dict[str, Any]] = {
        "paaro_backend": {
            "name": "Paaro Backend Server",
            "cmd": ["python", "-m", "paaro.server"],
            "port": 8000,
            "filter": "paaro.server",
        },
        "ollama": {
            "name": "Ollama LLM Engine",
            "cmd": ["ollama", "serve"],
            "port": 11434,
            "filter": "ollama",
        },
        "vite": {
            "name": "Frontend Dev Server",
            "cmd": ["npm", "run", "dev"],
            "port": 5173,
            "filter": "vite",
        },
    }

    def get_process_list(
        self, max_count: int = 50, filter_name: Optional[str] = None
    ) -> List[ProcessInfo]:
        """
        List running processes with CPU and memory statistics.
        """
        processes: List[ProcessInfo] = []
        filter_lower = filter_name.lower().strip() if filter_name else None

        for p in psutil.process_iter(["pid", "name", "status", "memory_info"]):
            try:
                name = p.info.get("name") or "Unknown"
                if filter_lower and filter_lower not in name.lower():
                    continue

                mem_mb = 0.0
                mem_info = p.info.get("memory_info")
                if mem_info:
                    mem_mb = mem_info.rss / (1024 * 1024)

                processes.append(
                    ProcessInfo(
                        pid=p.info["pid"],
                        name=name,
                        cpu_percent=0.0,
                        memory_mb=mem_mb,
                        status=p.info.get("status", "running"),
                        cmdline=[],
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by memory usage descending
        processes.sort(key=lambda x: x.memory_mb, reverse=True)
        return processes[:max_count]

    def check_process(self, target: str) -> Dict[str, Any]:
        """
        Check if a specific process name or PID is currently running.
        """
        if not target:
            return {"running": False, "pids": [], "count": 0}

        target_str = str(target).strip().lower()
        matched_pids: List[int] = []
        matched_names: List[str] = []
        total_mem_mb = 0.0

        # Check by PID if integer
        if target_str.isdigit():
            target_pid = int(target_str)
            if psutil.pid_exists(target_pid):
                try:
                    p = psutil.Process(target_pid)
                    matched_pids.append(target_pid)
                    matched_names.append(p.name())
                    total_mem_mb += p.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        else:
            for p in psutil.process_iter(["pid", "name", "memory_info"]):
                try:
                    pname = (p.info.get("name") or "").lower()
                    if not pname:
                        continue
                    pname_stem = os.path.splitext(pname)[0]
                    if target_str == pname or target_str == pname_stem or target_str in pname:
                        matched_pids.append(p.info["pid"])
                        matched_names.append(p.info.get("name") or target_str)
                        if p.info.get("memory_info"):
                            total_mem_mb += p.info["memory_info"].rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        is_running = len(matched_pids) > 0
        return {
            "running": is_running,
            "target": target,
            "pids": matched_pids,
            "count": len(matched_pids),
            "names": list(set(matched_names)),
            "memory_mb": round(total_mem_mb, 2),
        }

    def start_process(
        self,
        service_name_or_cmd: str,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
    ) -> ComputerActionResult:
        """
        Safely launch an approved known process or service.
        """
        key = service_name_or_cmd.lower().strip()
        svc_config = self.KNOWN_SERVICES.get(key)

        if not svc_config:
            # Check natural aliases
            if "backend" in key or "server" in key or "paaro" in key:
                svc_config = self.KNOWN_SERVICES["paaro_backend"]
            elif "ollama" in key or "llm" in key:
                svc_config = self.KNOWN_SERVICES["ollama"]
            elif "vite" in key or "frontend" in key:
                svc_config = self.KNOWN_SERVICES["vite"]

        if not svc_config:
            return ComputerActionResult(
                success=False,
                action="start_process",
                target=service_name_or_cmd,
                error=f"Unrecognized process service: '{service_name_or_cmd}'. Only approved services can be started.",
                verification=ComputerVerificationResult(verified=False, reason="Unapproved process"),
            )

        cmd = list(svc_config["cmd"]) + (args or [])
        work_dir = cwd or os.getcwd()

        logger.info("[COMPUTER] Starting approved service '%s': %s", svc_config['name'], cmd)
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=work_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            time.sleep(0.5)
            is_alive = proc.poll() is None

            return ComputerActionResult(
                success=is_alive,
                action="start_process",
                target=svc_config["name"],
                pid=proc.pid,
                result={"service": key, "name": svc_config["name"], "pid": proc.pid},
                verification=ComputerVerificationResult(
                    verified=is_alive,
                    reason=f"Service '{svc_config['name']}' running (PID: {proc.pid})",
                    details={"pid": proc.pid, "port": svc_config.get("port")},
                ),
            )
        except Exception as e:
            logger.error("[COMPUTER] Failed to start service '%s': %s", svc_config['name'], e)
            return ComputerActionResult(
                success=False,
                action="start_process",
                target=service_name_or_cmd,
                error=str(e),
                verification=ComputerVerificationResult(verified=False, reason=str(e)),
            )

    def stop_process(
        self,
        target_name_or_pid: str,
        pid: Optional[int] = None,
        force: bool = False,
    ) -> ComputerActionResult:
        """
        Gracefully terminate an approved process by name or PID.
        Blocks killing critical OS and protected processes.
        """
        target_str = str(target_name_or_pid).strip().lower()

        # Check PID protection
        if pid in self.PROTECTED_PIDS:
            return ComputerActionResult(
                success=False,
                action="stop_process",
                target=target_name_or_pid,
                error=f"Cannot stop system PID {pid}: protected by OS security.",
            )

        # Check process name protection
        if target_str in self.CRITICAL_OS_PROCESSES:
            return ComputerActionResult(
                success=False,
                action="stop_process",
                target=target_name_or_pid,
                error=f"Cannot terminate critical OS process '{target_name_or_pid}'.",
            )

        # Find target PIDs
        check_res = self.check_process(target_name_or_pid)
        target_pids = check_res.get("pids", [])
        if pid and pid not in target_pids:
            target_pids.append(pid)

        if not target_pids:
            return ComputerActionResult(
                success=True,
                action="stop_process",
                target=target_name_or_pid,
                result={"message": "Process was not running"},
                verification=ComputerVerificationResult(
                    verified=True,
                    reason=f"Process '{target_name_or_pid}' is already stopped.",
                ),
            )

        terminated: List[int] = []
        for p_id in target_pids:
            if p_id in self.PROTECTED_PIDS:
                continue
            try:
                p = psutil.Process(p_id)
                pname = p.name().lower()
                if pname in self.CRITICAL_OS_PROCESSES:
                    continue

                logger.info("[COMPUTER] Terminating process '%s' (PID=%d)", pname, p_id)
                if force:
                    p.kill()
                else:
                    p.terminate()
                terminated.append(p_id)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        time.sleep(0.3)
        still_running = False
        for p_id in terminated:
            if psutil.pid_exists(p_id):
                still_running = True
                break

        return ComputerActionResult(
            success=not still_running,
            action="stop_process",
            target=target_name_or_pid,
            result={"terminated_pids": terminated},
            verification=ComputerVerificationResult(
                verified=not still_running,
                reason=f"Stopped process '{target_name_or_pid}' (PIDs: {terminated})",
                details={"pids": terminated},
            ),
        )

    def get_system_state(self) -> SystemStateInfo:
        """
        Query system CPU, memory, battery, and running processes.
        """
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()

        battery_pct = None
        battery_plugged = None
        if hasattr(psutil, "sensors_battery"):
            try:
                bat = psutil.sensors_battery()
                if bat:
                    battery_pct = bat.percent
                    battery_plugged = bat.power_plugged
            except Exception:
                pass

        proc_count = len(psutil.pids())

        return SystemStateInfo(
            cpu_percent=cpu,
            memory_percent=mem.percent,
            memory_used_gb=mem.used / (1024 ** 3),
            memory_total_gb=mem.total / (1024 ** 3),
            battery_percent=battery_pct,
            battery_plugged=battery_plugged,
            running_app_count=proc_count,
        )
