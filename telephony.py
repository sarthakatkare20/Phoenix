"""
Telephony and Voice Calling Module for Project Phoenix.
Enables Phoenix to initiate GSM voice calls to the user's mobile phone via Twilio Voice API.
"""

import asyncio
import html
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("paaro.telephony")


def get_telephony_credentials() -> Dict[str, str]:
    """Retrieve Twilio credentials and user phone number from environment or config."""
    try:
        from config import settings
        acc = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        tok = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        f_num = getattr(settings, "TWILIO_PHONE_NUMBER", None)
        u_num = getattr(settings, "USER_PHONE_NUMBER", None)
    except Exception:
        acc, tok, f_num, u_num = None, None, None, None

    account_sid = (acc or os.environ.get("TWILIO_ACCOUNT_SID", "")).strip()
    auth_token = (tok or os.environ.get("TWILIO_AUTH_TOKEN", "")).strip()
    from_number = (f_num or os.environ.get("TWILIO_PHONE_NUMBER", "")).strip()
    to_number = (u_num or os.environ.get("USER_PHONE_NUMBER", "")).strip()

    return {
        "account_sid": account_sid,
        "auth_token": auth_token,
        "from_number": from_number,
        "to_number": to_number,
    }


def make_phone_call(
    message: str,
    to_number: Optional[str] = None,
    voice: str = "Polly.Brian",
) -> Dict[str, Any]:
    """
    Trigger an outbound GSM phone call to the user's mobile phone.
    When answered, Phoenix speaks the synthesized message.
    """
    creds = get_telephony_credentials()
    account_sid = creds["account_sid"]
    auth_token = creds["auth_token"]
    from_number = creds["from_number"]
    target_number = (to_number or creds["to_number"]).strip()

    if not account_sid or not auth_token or not from_number:
        err = (
            "Twilio credentials missing. Please set TWILIO_ACCOUNT_SID, "
            "TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in .env.local"
        )
        logger.warning(err)
        return {"status": "error", "message": err}

    if not target_number:
        err = "No target phone number specified. Please set USER_PHONE_NUMBER in .env.local or pass 'to'."
        logger.warning(err)
        return {"status": "error", "message": err}

    # Ensure E.164 phone format (+CountryCodeNumber)
    clean_target = re.sub(r"[^\d\+]", "", target_number)
    if not clean_target.startswith("+"):
        if len(clean_target) == 10:
            clean_target = f"+91{clean_target}"
        else:
            clean_target = f"+{clean_target}"

    clean_msg = html.escape(message.strip() or "Hello Sarthak, Phoenix transmission incoming.")
    twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>'
        f'<Pause length="1"/>'
        f'<Say voice="{voice}">{clean_msg}</Say>'
        f'<Pause length="1"/>'
        f'<Say voice="{voice}">Transmission complete. Standing by.</Say>'
        f'</Response>'
    )

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        call = client.calls.create(
            twiml=twiml,
            to=clean_target,
            from_=from_number,
        )

        logger.info("Outbound call successfully queued (SID: %s) to %s", call.sid, clean_target)
        return {
            "status": "success",
            "call_sid": call.sid,
            "to": clean_target,
            "message": message,
            "call_status": getattr(call, "status", "queued"),
        }
    except Exception as e:
        logger.error("Failed to initiate outbound call: %s", e)
        return {"status": "error", "message": str(e), "to": clean_target}


async def make_phone_call_async(
    message: str,
    to_number: Optional[str] = None,
    voice: str = "Polly.Brian",
) -> Dict[str, Any]:
    """Asynchronously make a phone call without blocking the asyncio loop."""
    return await asyncio.to_thread(make_phone_call, message, to_number, voice)
