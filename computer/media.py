"""
Native Python Media and Audio Playback Controller for Phoenix.
Ported from legacy bridge/spotify_controller.mjs with high-performance native Win32 keybd_event API.
Supports Windows virtual media keys, Spotify URI dispatch, and YouTube search.
"""

import ctypes
import logging
import subprocess
import urllib.parse
from typing import Optional

logger = logging.getLogger("paaro.computer.media")

# Windows Virtual Key Codes
VK_MEDIA_NEXT_TRACK = 0xB0  # 176
VK_MEDIA_PREV_TRACK = 0xB1  # 177
VK_MEDIA_STOP = 0xB2        # 178
VK_MEDIA_PLAY_PAUSE = 0xB3  # 179
VK_VOLUME_MUTE = 0xAD       # 173
VK_VOLUME_DOWN = 0xAE       # 174
VK_VOLUME_UP = 0xAF         # 175

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


def send_media_key(vk_code: int, repeat: int = 1) -> bool:
    """Send native Windows Virtual Key event using Win32 API (0ms latency, zero subprocess overhead)."""
    try:
        user32 = ctypes.windll.user32
        for _ in range(repeat):
            user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
            user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        logger.warning("[MEDIA] Win32 keybd_event failed, falling back to WScript.Shell: %s", e)
        try:
            cmd = f'$w = New-Object -ComObject Wscript.Shell; for($i=0;$i<{repeat};$i++){{ $w.SendKeys([char]{vk_code}) }}'
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=2)
            return True
        except Exception as e2:
            logger.error("[MEDIA] PowerShell media key send failed: %s", e2)
            return False


def control_media(action: str) -> dict:
    """
    Control playback state: play_pause, pause, play, next, previous, volume_up, volume_down, mute.
    """
    act = action.lower().strip()
    logger.info("[MEDIA] Executing media action: %s", act)

    if act in ("play_pause", "toggle", "pause", "play", "resume"):
        send_media_key(VK_MEDIA_PLAY_PAUSE)
        return {"ok": True, "action": "play_pause"}
    elif act in ("next", "skip", "next_song"):
        send_media_key(VK_MEDIA_NEXT_TRACK)
        return {"ok": True, "action": "next"}
    elif act in ("previous", "prev", "prev_song"):
        send_media_key(VK_MEDIA_PREV_TRACK)
        return {"ok": True, "action": "previous"}
    elif act in ("stop",):
        send_media_key(VK_MEDIA_STOP)
        return {"ok": True, "action": "stop"}
    elif act in ("volume_up", "louder", "tez"):
        # Repeat 3 times for a noticeable step
        send_media_key(VK_VOLUME_UP, repeat=3)
        return {"ok": True, "action": "volume_up"}
    elif act in ("volume_down", "quieter", "dheemi"):
        send_media_key(VK_VOLUME_DOWN, repeat=3)
        return {"ok": True, "action": "volume_down"}
    elif act in ("mute", "unmute", "silent"):
        send_media_key(VK_VOLUME_MUTE)
        return {"ok": True, "action": "mute"}
    else:
        logger.warning("[MEDIA] Unknown media action requested: %s", action)
        return {"ok": False, "error": f"Unknown media action: {action}"}


def play_music(query: str, platform: str = "spotify") -> dict:
    """
    Search and launch music tracks on Spotify or YouTube.
    """
    clean = query.strip() if query else ""
    platform = platform.lower().strip()

    if platform == "youtube" or (clean and platform != "spotify"):
        encoded = urllib.parse.quote(clean)
        url = f"https://www.youtube.com/results?search_query={encoded}" if clean else "https://youtube.com"
        logger.info("[MEDIA] Launching YouTube query: '%s' -> %s", clean, url)
        try:
            subprocess.Popen(f'start "" "{url}"', shell=True)
            return {"ok": True, "platform": "youtube", "query": clean, "url": url}
        except Exception as e:
            logger.error("[MEDIA] Failed to launch YouTube: %s", e)
            return {"ok": False, "error": str(e)}

    # Spotify play / search
    if clean:
        encoded = urllib.parse.quote(clean)
        spotify_uri = f"spotify:search:{encoded}"
        web_fallback_url = f"https://open.spotify.com/search/{encoded}"
    else:
        spotify_uri = "spotify:"
        web_fallback_url = "https://open.spotify.com"

    logger.info("[MEDIA] Launching Spotify search: '%s'", clean)
    try:
        # Launch Spotify URI
        p = subprocess.Popen(f'start "" "{spotify_uri}"', shell=True)
        return {"ok": True, "platform": "spotify", "query": clean, "uri": spotify_uri}
    except Exception as e:
        logger.warning("[MEDIA] Spotify desktop launch failed, falling back to web player: %s", e)
        try:
            subprocess.Popen(f'start "" "{web_fallback_url}"', shell=True)
            return {"ok": True, "platform": "spotify_web", "query": clean, "url": web_fallback_url}
        except Exception as e2:
            logger.error("[MEDIA] Spotify web launch also failed: %s", e2)
            return {"ok": False, "error": str(e2)}
