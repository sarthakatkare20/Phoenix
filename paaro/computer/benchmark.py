"""
Performance Benchmark for Paaro Step 9: Computer Control Subsystem.
Measures:
- Policy evaluation latency
- Path validation latency
- Process lookup latency
- Controller orchestration overhead
- Verification latency
"""

import time
import os
from paaro.tool_gateway import PolicyEngine, ToolGateway
from paaro.computer.filesystem import SafePathResolver
from paaro.computer.urls import SafeUrlOpener
from paaro.computer.processes import ProcessController
from paaro.computer.controller import ComputerController
from paaro.computer.models import ComputerAction, ComputerActionType

def run_benchmarks():
    print("==================== COMPUTER CONTROL BENCHMARKS ====================")
    
    # 1. Policy Evaluation Latency
    engine = PolicyEngine()
    t0 = time.perf_counter()
    iterations = 1000
    for _ in range(iterations):
        engine.evaluate("open_app")
        engine.evaluate("close_app")
        engine.evaluate("open_folder")
        engine.evaluate("format_disk")
    t1 = time.perf_counter()
    policy_lat_us = ((t1 - t0) / (iterations * 4)) * 1_000_000
    print(f"  Policy Evaluation Latency:       {policy_lat_us:.3f} µs ({policy_lat_us/1000:.4f} ms)")

    # 2. Path Validation Latency
    resolver = SafePathResolver()
    t0 = time.perf_counter()
    for _ in range(iterations):
        resolver.resolve_safe_path("F:\\jarvis")
        resolver.resolve_safe_path("downloads")
        resolver.resolve_safe_path("../../Windows/System32", must_exist=False)
    t1 = time.perf_counter()
    path_lat_us = ((t1 - t0) / (iterations * 3)) * 1_000_000
    print(f"  Path Validation Latency:         {path_lat_us:.3f} µs ({path_lat_us/1000:.4f} ms)")

    # 3. URL Validation Latency
    opener = SafeUrlOpener()
    t0 = time.perf_counter()
    for _ in range(iterations):
        opener.validate_url("https://github.com/paaro")
        opener.validate_url("javascript:alert(1)")
    t1 = time.perf_counter()
    url_lat_us = ((t1 - t0) / (iterations * 2)) * 1_000_000
    print(f"  URL Validation Latency:          {url_lat_us:.3f} µs ({url_lat_us/1000:.4f} ms)")

    # 4. Process Lookup Latency
    procs = ProcessController()
    t0 = time.perf_counter()
    proc_iters = 20
    for _ in range(proc_iters):
        procs.check_process("python")
    t1 = time.perf_counter()
    proc_lat_ms = ((t1 - t0) / proc_iters) * 1000
    print(f"  Process Lookup Latency:          {proc_lat_ms:.2f} ms")

    # 5. Controller Orchestration Overhead
    controller = ComputerController()
    t0 = time.perf_counter()
    for _ in range(100):
        action = ComputerAction(action_type=ComputerActionType.CHECK_PROCESS, target="python")
        controller.execute_action(action)
    t1 = time.perf_counter()
    ctrl_overhead_ms = ((t1 - t0) / 100) * 1000
    print(f"  Controller Action Overhead:      {ctrl_overhead_ms:.2f} ms")

    # 6. System State Query Latency
    t0 = time.perf_counter()
    for _ in range(20):
        procs.get_system_state()
    t1 = time.perf_counter()
    sys_lat_ms = ((t1 - t0) / 20) * 1000
    print(f"  System State Metrics Latency:    {sys_lat_ms:.2f} ms")
    print("=====================================================================")

if __name__ == "__main__":
    run_benchmarks()
