import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from dotenv import load_dotenv

# Ищем .env рядом со скриптом
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SMTP_SENDER_EMAIL", "chatbotomg@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EXPLORER_BASE_URL = os.environ.get("EXPLORER_BASE_URL", "https://sepolia.etherscan.io")

RECIPIENT_EMAIL = "andrii.fedorov@infis.cz"

def send_demo_email():
    if not SMTP_PASSWORD:
        print("Пароль SMTP_PASSWORD не найден в .env")
        return

    # Данные для письма
    device_id = "cargo_tracker_9000"
    g_force = "12.4G"
    reason = f"Critical impact detected ({g_force}). Fragile goods compromised. Delivery contract terminated immediately."
    
    contract_address = os.environ.get("CONTRACT_ADDRESS", "0x965CdD2a560bab50ce52A826d1431A488C9E9959")
    explorer_link = f"{EXPLORER_BASE_URL}/address/{contract_address}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Весь HTML-шаблон (Amazon) вшит прямо в код
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Amazon Logistics Alert</title>
      <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif; background: #f3f3f3; color: #0f1111; padding: 10px; line-height: 1.3; }}
        .wrapper {{ background: #fff; max-width: 400px; margin: 0 auto; border-radius: 8px; border: 1px solid #ddd; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: #232f3e; padding: 12px; text-align: center; }}
        .header img {{ height: 22px; filter: brightness(0) invert(1); }}
        .content {{ padding: 16px; }}
        h1 {{ color: #c40000; font-size: 18px; margin-bottom: 12px; text-align: center; }}
        .box {{ background: #f9f9f9; border-left: 4px solid #ff9900; padding: 10px; margin-bottom: 12px; border-radius: 0 4px 4px 0; }}
        .label {{ font-size: 11px; color: #565959; text-transform: uppercase; font-weight: bold; margin-bottom: 2px; }}
        .val {{ font-size: 14px; font-weight: bold; margin-bottom: 8px; word-break: break-word; }}
        .val.alert {{ color: #c40000; }}
        .btn {{ display: block; text-align: center; background: #ffd814; border: 1px solid #fcd200; color: #0f1111; text-decoration: none; padding: 12px; border-radius: 8px; font-weight: bold; font-size: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }}
        .footer {{ text-align: center; font-size: 10px; color: #565959; padding: 8px; background: #eaeded; }}
      </style>
    </head>
    <body>
      <div class="wrapper">
        <div class="header">
          <img src="https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg" alt="Amazon">
        </div>
        <div class="content">
          <h1>Contract Terminated</h1>
          <div class="box">
            <div class="label">Tracker ID</div>
            <div class="val">{device_id}</div>
            <div class="label">Violation Reason</div>
            <div class="val alert">{reason}</div>
            <div class="label">Time (UTC)</div>
            <div class="val" style="margin-bottom:0; font-weight: normal; font-size: 12px;">{timestamp}</div>
          </div>
          <a href="{explorer_link}" class="btn">View on Etherscan</a>
        </div>
        <div class="footer">Amazon Logistics IoT automatically generated message.</div>
      </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Action Required: Amazon Delivery Violation — {device_id}"
    msg["From"] = f"Amazon Logistics <{SENDER_EMAIL}>"
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    print("Отправляю письмо...")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SENDER_EMAIL, SMTP_PASSWORD)
            smtp.sendmail(SENDER_EMAIL, [RECIPIENT_EMAIL], msg.as_string())
        print("Письмо успешно отправлено.")
    except Exception as exc:
        print(f"Ошибка отправки: {exc}")

if __name__ == "__main__":
    send_demo_email()