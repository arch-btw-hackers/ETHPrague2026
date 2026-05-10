"""
Email notification service — sends HTML alert emails on delivery violations.

Environment variables:
  SMTP_SENDER_EMAIL   — Gmail address used to send alerts  (default: chatbotomg@gmail.com)
  SMTP_PASSWORD       — Gmail App Password for the sender account
  EXPLORER_BASE_URL   — Block-explorer base URL (default: https://sepolia.etherscan.io)
  ALERT_RECIPIENT_EMAIL — Recipient address for violation alerts

Credentials are read from environment variables so they are never committed
to source control (OWASP A02 / Sensitive Data Exposure mitigation).
Add them to your .env file (never to the repository itself).
"""
import asyncio
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "alert_email.html"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Read from environment — never hard-code credentials in source files.
SENDER_EMAIL: str = os.environ.get("SMTP_SENDER_EMAIL", "chatbotomg@gmail.com")
_EXPLORER_BASE_URL: str = os.environ.get(
    "EXPLORER_BASE_URL", "https://sepolia.etherscan.io"
)


def _build_explorer_link(tx_hash_or_address: str) -> str:
    """Return a full Etherscan-compatible link for a tx hash or contract address."""
    val = tx_hash_or_address.strip()
    # tx hash: 0x + 64 hex chars; address: 0x + 40 hex chars
    if val.startswith("0x") and len(val) == 66:
        return f"{_EXPLORER_BASE_URL}/tx/{val}"
    return f"{_EXPLORER_BASE_URL}/address/{val}"


def _send_sync(
    device_id: str,
    reason: str,
    recipient_email: str,
    tx_hash_or_address: str,
) -> None:
    """Blocking send — runs inside a thread pool so it never blocks the event loop."""
    password = os.environ.get("SMTP_PASSWORD", "")
    if not password:
        logger.warning(
            "SMTP_PASSWORD not set — skipping alert email for device %s", device_id
        )
        return

    explorer_link = _build_explorer_link(tx_hash_or_address)
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        html = _TEMPLATE_PATH.read_text(encoding="utf-8").format(
            device_id=device_id,
            reason=reason,
            timestamp=timestamp,
            explorer_link=explorer_link,
        )
    except (OSError, KeyError) as exc:
        logger.error("Failed to render alert email template: %s", exc)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[GigaService Alert] Delivery violation — {device_id}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = recipient_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SENDER_EMAIL, password)
            smtp.sendmail(SENDER_EMAIL, [recipient_email], msg.as_string())
        logger.info(
            "Alert email sent to %s for device %s", recipient_email, device_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send alert email for device %s: %s", device_id, exc)


async def send_html_alert(
    device_id: str,
    reason: str,
    recipient_email: str,
    tx_hash_or_address: str,
) -> None:
    """
    Send an HTML violation alert email asynchronously.

    Runs the blocking smtplib call in a thread-pool executor so the
    FastAPI event loop is never blocked.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        _send_sync,
        device_id,
        reason,
        recipient_email,
        tx_hash_or_address,
    )
