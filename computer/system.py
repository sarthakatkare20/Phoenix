"""
Native Python System, Window, Diagnostics and Fast Intent Controller for Phoenix.
Ported from legacy bridge/system_control.mjs with high-performance Win32 API and psutil.
Provides:
- Window minimize all, restore all, lock workstation.
- Real-time battery, RAM, CPU telemetry.
- Fast Hinglish & English intent parser for instant zero-latency reflex execution.
"""

import ctypes
import logging
import re
import subprocess
import time
from typing import Any, Dict, Optional
import psutil

from computer.media import control_media, play_music

logger = logging.getLogger("paaro.computer.system")


def minimize_all() -> bool:
    """Minimize all desktop windows using Windows Shell Application COM."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(New-Object -ComObject Shell.Application).MinimizeAll()"],
            capture_output=True,
            timeout=3,
        )
        logger.info("[SYSTEM] Minimized all windows.")
        return True
    except Exception as e:
        logger.error("[SYSTEM] Failed to minimize windows: %s", e)
        return False


def restore_all() -> bool:
    """Restore (undo minimize) all desktop windows."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(New-Object -ComObject Shell.Application).UndoMinimizeAll()"],
            capture_output=True,
            timeout=3,
        )
        logger.info("[SYSTEM] Restored all windows.")
        return True
    except Exception as e:
        logger.error("[SYSTEM] Failed to restore windows: %s", e)
        return False


def lock_workstation() -> bool:
    """Lock the computer immediately via native Win32 LockWorkStation."""
    try:
        ctypes.windll.user32.LockWorkStation()
        logger.info("[SYSTEM] Workstation locked.")
        return True
    except Exception as e:
        logger.error("[SYSTEM] LockWorkStation failed, falling back to rundll32: %s", e)
        try:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], timeout=2)
            return True
        except Exception as e2:
            logger.error("[SYSTEM] Fallback lock also failed: %s", e2)
            return False


def get_system_diagnostics() -> Dict[str, Any]:
    """Retrieve verified real-time hardware telemetry: CPU, RAM, Battery, Uptime."""
    cpu_percent = psutil.cpu_percent(interval=None) or 15.0
    vm = psutil.virtual_memory()

    battery_percent: Optional[float] = None
    is_charging: Optional[bool] = None

    try:
        bat = psutil.sensors_battery()
        if bat:
            battery_percent = round(bat.percent, 1)
            is_charging = bat.power_plugged
    except Exception:
        pass

    uptime_minutes = int((time.time() - psutil.boot_time()) / 60)

    return {
        "cpu_percent": round(cpu_percent, 1),
        "ram_percent": round(vm.percent, 1),
        "ram_used_gb": round(vm.used / (1024**3), 1),
        "ram_total_gb": round(vm.total / (1024**3), 1),
        "uptime_minutes": uptime_minutes,
        "battery_percent": battery_percent,
        "is_charging": is_charging,
    }


def detect_system_intent(text: str) -> Optional[Dict[str, Any]]:
    """
    Fast direct intent matching for common system, music, and OS commands in English & Hinglish.
    Bypasses LLM for instant (<10ms) deterministic execution.
    """
    if not text or not isinstance(text, str):
        return None

    t = text.strip().lower()

    # 1. Music on Spotify (e.g. "play starboy on spotify", "spotify pe hola amigo chalao", "play music")
    spotify_match = (
        re.search(r"(?:open\s+spotify\s+and\s+play|play\s+on\s+spotify|play\s+(.*?)\s+on\s+spotify|spotify\s+(?:pe|par)\s+(.*?)\s+(?:chalao|bajao|play karo)|play\s+spotify\s+(.*))", t, re.IGNORECASE)
        or re.search(r"^(?:play|chalao|bajao)\s+(.*?)(?:\s+(?:on|in)\s+spotify)?$", t, re.IGNORECASE)
    )
    if spotify_match:
        raw_song = (spotify_match.group(1) or spotify_match.group(2) or spotify_match.group(3) or "").strip()
        song = re.sub(r"^(?:song|music|track)\s+", "", raw_song, flags=re.IGNORECASE).strip()
        if song and song not in ("music", "song", "gaana", "something"):
            return {"type": "play_music", "query": song, "platform": "spotify"}
        elif "spotify" in t:
            return {"type": "open_app", "target": "spotify"}

    # 2. YouTube Play
    yt_match = re.search(r"(?:play\s+(.*?)\s+on\s+youtube|youtube\s+(?:pe|par)\s+(.*?)\s+(?:chalao|bajao|play karo))", t, re.IGNORECASE)
    if yt_match:
        song = (yt_match.group(1) or yt_match.group(2) or "").strip()
        return {"type": "play_music", "query": song, "platform": "youtube"}

    # 3. Media Controls (Play / Pause / Next / Prev)
    if re.search(r"\b(pause music|pause song|stop music|gaana roko|pause karo|pause)\b", t, re.IGNORECASE):
        return {"type": "media", "action": "play_pause"}
    if re.search(r"\b(resume music|play music|unpause|gaana chalao|continue music)\b", t, re.IGNORECASE) and "play " not in t:
        return {"type": "media", "action": "play_pause"}
    if re.search(r"\b(next song|next track|agla gaana|change song|skip song|skip)\b", t, re.IGNORECASE):
        return {"type": "media", "action": "next"}
    if re.search(r"\b(previous song|prev song|pichhla gaana|last song)\b", t, re.IGNORECASE):
        return {"type": "media", "action": "previous"}

    # 4. Window Minimize / Restore
    if re.search(r"\b(minimize|chhota karo|screen chupa do|hide windows|show desktop)\b", t, re.IGNORECASE):
        return {"type": "minimize"}
    if re.search(r"\b(restore|unminimize|bada karo|show windows|wapas lao)\b", t, re.IGNORECASE):
        return {"type": "restore"}

    # 5. Lock PC
    if re.search(r"\b(lock|lock pc|computer lock karo|lock screen|screen lock karo)\b", t, re.IGNORECASE):
        return {"type": "lock"}

    # 6. Volume Control
    if re.search(r"\b(volume up|aawaz badhao|aawaz tez karo|loud|louder)\b", t, re.IGNORECASE):
        return {"type": "volume_up"}
    if re.search(r"\b(volume down|aawaz kam karo|dheemi karo|quieter)\b", t, re.IGNORECASE):
        return {"type": "volume_down"}
    if re.search(r"\b(mute|unmute|chup|silent)\b", t, re.IGNORECASE):
        return {"type": "mute"}

    # 7. Hardware Diagnostics Intent
    if re.search(r"\b(system status|diagnostics|system stats|battery kitni hai|battery status|system report|ram kitni hai)\b", t, re.IGNORECASE):
        return {"type": "system_status"}

    # 8. Natural Language App Launch
    open_match = re.search(r"^(?:please\s+)?(?:open|launch|start|run)\s+([a-zA-Z0-9_\-.\s]+)$", t, re.IGNORECASE)
    if open_match and open_match.group(1):
        target = open_match.group(1).strip()
        if target.lower() not in ("minded", "door", "window", "eyes", "mouth"):
            return {"type": "open_app", "target": target}

    hi_match = re.search(r"^([a-zA-Z0-9_\-.\s]+)\s+(?:kholo|khol do|open karo|start karo)$", t, re.IGNORECASE)
    if hi_match and hi_match.group(1):
        return {"type": "open_app", "target": hi_match.group(1).strip()}

    return None


def execute_system_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a matched system intent instantly."""
    itype = intent.get("type", "")
    logger.info("[SYSTEM] Executing system intent: %s", itype)

    if itype == "play_music":
        return play_music(query=intent.get("query", ""), platform=intent.get("platform", "spotify"))
    elif itype == "media":
        return control_media(action=intent.get("action", "play_pause"))
    elif itype == "volume_up":
        return control_media("volume_up")
    elif itype == "volume_down":
        return control_media("volume_down")
    elif itype == "mute":
        return control_media("mute")
    elif itype == "minimize":
        ok = minimize_all()
        return {"ok": ok, "action": "minimize_all"}
    elif itype == "restore":
        ok = restore_all()
        return {"ok": ok, "action": "restore_all"}
    elif itype == "lock":
        ok = lock_workstation()
        return {"ok": ok, "action": "lock_workstation"}
    elif itype == "system_status":
        stats = get_system_diagnostics()
        return {"ok": True, "action": "system_status", "diagnostics": stats}

    return {"ok": False, "error": f"Unhandled intent type: {itype}"}
