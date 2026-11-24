import os
import httpx

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Save Flight <onboarding@resend.dev>")
RESEND_API_URL = "https://api.resend.com/emails"


class EmailDeliveryError(Exception):
    pass


def send_email_otp(to_email: str, code: str, minutes_valid: int) -> None:
    """Send a 2FA one-time code by email via Resend's HTTP API.

    Silently no-ops (logs only) when RESEND_API_KEY isn't configured, so local
    dev/tests never require real email credentials - TOTP still works as the
    primary staff 2FA method regardless.
    """
    if not RESEND_API_KEY:
        print(f"[email_service] RESEND_API_KEY not set - skipping email send. OTP for {to_email}: {code}")
        return

    subject = "Your Save Flight verification code"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color:#0b1836;">Save Flight</h2>
      <p>Your verification code is:</p>
      <p style="font-size: 32px; font-weight: 700; letter-spacing: 6px; color:#0b1836;">{code}</p>
      <p style="color:#64748b; font-size: 13px;">This code expires in {minutes_valid} minutes. If you didn't request this, you can ignore this email.</p>
    </div>
    """

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": EMAIL_FROM, "to": [to_email], "subject": subject, "html": html},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # Don't leak provider errors to the client - the login flow already
        # returns "requires_2fa"; a failed send just means the code should be
        # requested again, not a stack trace surfaced to the user. Do log the
        # response body server-side though - "422" alone doesn't say *why*
        # Resend rejected it (e.g. sandbox mode only allows sending to the
        # account owner's own verified address).
        body = getattr(exc, "response", None)
        detail = body.text if body is not None else ""
        print(f"[email_service] Failed to send OTP email to {to_email}: {exc} | {detail}")
        raise EmailDeliveryError(str(exc)) from exc
