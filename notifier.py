import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
import requests

QUIET_START = 23  # 11 PM
QUIET_END = 6     # 6 AM


def is_quiet_hours(timezone_str: str, now: datetime = None) -> bool:
    """Returns True if current time is within quiet hours (11pm–6am) in the given timezone."""
    tz = pytz.timezone(timezone_str)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = tz.localize(now)
    hour = now.hour
    # Range wraps midnight: quiet if hour >= 23 OR hour < 6
    return hour >= QUIET_START or hour < QUIET_END


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
