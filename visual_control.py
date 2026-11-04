"""
Visual Screen Automation Controller for Project Phoenix.
Enables Phoenix to visibly open Chrome, display live search pages, and inject prompts into Antigravity IDE.
"""

import asyncio
import logging
import os
import subprocess
import time
import urllib.parse
from typing import Any, Dict, Optional

logger = logging.getLogger("paaro.visual")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ANTIGRAVITY_PATH = os.path.expandvars(r"%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe")


def open_chrome_visual(query_or_url: str) -> Dict[str, Any]:
    """
    Open Google Chrome visibly on screen with a target URL or Google search query.
    Ensures the user can watch the browser in real time.
    """
    target = (query_or_url or "").strip()
    if not target:
        target = "https://www.google.com"

    if target.startswith("http://") or target.startswith("https://"):
        url = target
    elif "." in target and " " not in target:
        url = f"https://{target}"
    else:
        encoded = urllib.parse.quote(target)
        url = f"https://www.google.com/search?q={encoded}"

    logger.info("Opening Chrome visibly with URL: %s", url)

    try:
        if os.path.isfile(CHROME_PATH):
            subprocess.Popen([CHROME_PATH, url])
        else:
            import webbrowser
            webbrowser.open(url, new=2)

        return {
            "status": "success",
            "action": "open_chrome",
            "url": url,
            "message": f"Opened Chrome with: {url}",
        }
    except Exception as e:
        logger.error("Error opening Chrome: %s", e)
        return {"status": "error", "message": str(e), "url": url}


def send_to_antigravity(prompt: str) -> Dict[str, Any]:
    """
    Bring Antigravity IDE to the foreground, focus the chat prompt,
    type/paste the prompt, and hit Enter.
    """
    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        return {"status": "error", "message": "No prompt provided for Antigravity."}

    logger.info("Dispatching prompt to Antigravity IDE: %s", clean_prompt[:100])

    try:
        # 1. Bring Antigravity window to front / focus it
        if os.path.isfile(ANTIGRAVITY_PATH):
            subprocess.Popen([ANTIGRAVITY_PATH, r"F:\Phoenix"])

        # 2. Automation script to activate window, press Ctrl+L, paste prompt, and press Enter
        # Uses Windows PowerShell with WScript.Shell for native GUI event dispatch
        ps_script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$wshell = New-Object -ComObject wscript.shell
$wshell.AppActivate('Antigravity')
Start-Sleep -Milliseconds 600
$wshell.SendKeys('^l')
Start-Sleep -Milliseconds 300
Set-Clipboard -Value @'
{clean_prompt}
'@
$wshell.SendKeys('^v')
Start-Sleep -Milliseconds 250
$wshell.SendKeys('{{ENTER}}')
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        return {
            "status": "success",
            "action": "send_to_antigravity",
            "prompt": clean_prompt,
            "message": "Prompt successfully typed and submitted into Antigravity IDE!",
        }

    except Exception as e:
        logger.error("Error dispatching prompt to Antigravity: %s", e)
        return {"status": "error", "message": str(e), "prompt": clean_prompt}


async def open_chrome_visual_async(query_or_url: str) -> Dict[str, Any]:
    return await asyncio.to_thread(open_chrome_visual, query_or_url)


async def send_to_antigravity_async(prompt: str) -> Dict[str, Any]:
    return await asyncio.to_thread(send_to_antigravity, prompt)
