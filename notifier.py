import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
import requests

QUIET_START = 23  # 11 PM
QUIET_END = 6     # 6 AM


def is_quiet_hours(
    timezone_str: str,
    now: datetime = None,
    quiet_start: int = QUIET_START,
    quiet_end: int = QUIET_END,
) -> bool:
    """Returns True if current time is within quiet hours in the given timezone."""
    tz = pytz.timezone(timezone_str)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = tz.localize(now)
    hour = now.hour
    # Range wraps midnight: quiet if hour >= quiet_start OR hour < quiet_end
    return hour >= quiet_start or hour < quiet_end


def format_vacancies(vacancies: list) -> tuple:
    """
    Returns (email_body, push_body) for a list of vacancy dicts.
    Each vacancy dict: {park, name, dates, url}
    """
    count = len(vacancies)

    # Email: full list
    lines = [f"{count} accommodation{'s' if count > 1 else ''} just opened for your watched dates:\n"]
    for v in vacancies:
        lines.append(f"• {v['name']} — {v['dates']}")
        lines.append(f"  Book now: {v['url']}\n")
    email_body = "\n".join(lines)

    # Push: first result + summary
    first = vacancies[0]
    if count == 1:
        push_body = f"{first['name']} ({first['dates']})\n{first['url']}"
    else:
        push_body = f"{first['name']} ({first['dates']}) + {count - 1} more\n{first['url']}"

    return email_body, push_body


def send_email(gmail_address: str, app_password: str, to: str, subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, to, msg.as_string())


def send_push(ntfy_topic: str, title: str, body: str, url: str = None):
    headers = {"Title": title}
    if url:
        headers["Click"] = url
    resp = requests.post(
        f"https://ntfy.sh/{ntfy_topic}",
        data=body.encode("utf-8"),
        headers=headers,
    )
    resp.raise_for_status()


def send_alert(config: dict, creds: dict, vacancies: list, force: bool = False):
    """
    Send a merged alert for all vacancies.

    Args:
        config: full config dict (needs config["notifications"])
        creds: {"gmail_address", "app_password", "ntfy_topic"}
        vacancies: list of vacancy dicts {park, name, dates, url}
        force: if True, bypass quiet hours (used by --test-notify)
    """
    if not vacancies:
        return

    notif = config["notifications"]
    park_name = vacancies[0]["park"]
    count = len(vacancies)
    subject = f"\U0001f3d5 Vacancy Alert \u2014 {park_name}"
    push_title = f"\U0001f3d5 {park_name} \u2014 {count} vacanc{'ies' if count > 1 else 'y'} found"
    email_body, push_body = format_vacancies(vacancies)
    first_url = vacancies[0]["url"]

    send_email(creds["gmail_address"], creds["app_password"], notif["email"], subject, email_body)

    qh = notif.get("quiet_hours") or {}
    qs = int(qh["start"].split(":")[0]) if qh.get("start") else QUIET_START
    qe = int(qh["end"].split(":")[0]) if qh.get("end") else QUIET_END
    quiet = is_quiet_hours(notif["timezone"], quiet_start=qs, quiet_end=qe) if not force else False
    if not quiet:
        send_push(creds["ntfy_topic"], push_title, push_body, first_url)
