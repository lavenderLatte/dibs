from datetime import datetime

import pytest

from notifier import is_quiet_hours, format_vacancies


# ── Quiet hours ────────────────────────────────────────────────────────────────
# Quiet = 11pm (23:00) through 6am (06:00). Wraps midnight.

def test_is_quiet_at_midnight():
    assert is_quiet_hours("America/Los_Angeles", now=datetime(2026, 1, 1, 0, 0)) is True


def test_is_quiet_at_5am():
    assert is_quiet_hours("America/Los_Angeles", now=datetime(2026, 1, 1, 5, 59)) is True


def test_is_not_quiet_at_6am():
    assert is_quiet_hours("America/Los_Angeles", now=datetime(2026, 1, 1, 6, 0)) is False


def test_is_quiet_at_11pm():
    assert is_quiet_hours("America/Los_Angeles", now=datetime(2026, 1, 1, 23, 0)) is True


def test_is_not_quiet_at_noon():
    assert is_quiet_hours("America/Los_Angeles", now=datetime(2026, 1, 1, 12, 0)) is False


# ── Alert formatting ───────────────────────────────────────────────────────────

VACANCY_1 = {"park": "Yosemite", "name": "Cabin #1", "dates": "Jul 3-5", "url": "https://rec.gov/1"}
VACANCY_2 = {"park": "Yosemite", "name": "Cabin #2", "dates": "Jul 6-8", "url": "https://rec.gov/2"}


def test_format_single_vacancy_email_contains_name_dates_url():
    email_body, _ = format_vacancies([VACANCY_1])
    assert "Cabin #1" in email_body
    assert "Jul 3-5" in email_body
    assert "https://rec.gov/1" in email_body


def test_format_single_vacancy_push_body():
    _, push_body = format_vacancies([VACANCY_1])
    assert "Cabin #1" in push_body
    assert "https://rec.gov/1" in push_body


def test_format_multiple_vacancies_email_lists_all():
    email_body, _ = format_vacancies([VACANCY_1, VACANCY_2])
    assert "Cabin #1" in email_body
    assert "Cabin #2" in email_body


def test_format_multiple_vacancies_push_summarizes():
    _, push_body = format_vacancies([VACANCY_1, VACANCY_2])
    assert "Cabin #1" in push_body
    assert "+ 1 more" in push_body


# ── Email delivery ─────────────────────────────────────────────────────────────

def test_send_email_calls_smtp_with_correct_args(mocker):
    mock_smtp_cls = mocker.patch("notifier.smtplib.SMTP_SSL")
    mock_server = mocker.MagicMock()
    mock_smtp_cls.return_value.__enter__ = mocker.MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = mocker.MagicMock(return_value=False)

    from notifier import send_email
    send_email("sender@gmail.com", "apppass", "to@example.com", "Subject", "Body")

    mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 465)
    mock_server.login.assert_called_once_with("sender@gmail.com", "apppass")
    mock_server.sendmail.assert_called_once()
    _, call_args, _ = mock_server.sendmail.mock_calls[0]
    assert call_args[0] == "sender@gmail.com"
    assert call_args[1] == "to@example.com"


# ── Push delivery ──────────────────────────────────────────────────────────────

def test_send_push_posts_to_ntfy(mocker):
    mock_post = mocker.patch("notifier.requests.post")
    from notifier import send_push
    send_push("my-topic", "Alert Title", "Alert body", "https://rec.gov/1")

    mock_post.assert_called_once()
    url = mock_post.call_args[0][0]
    assert "ntfy.sh/my-topic" in url
    assert mock_post.call_args[1]["headers"]["Title"] == "Alert Title"
    assert mock_post.call_args[1]["headers"]["Click"] == "https://rec.gov/1"


# ── send_alert integration ─────────────────────────────────────────────────────

CONFIG = {
    "notifications": {
        "email": "to@example.com",
        "ntfy_topic": "my-topic",
        "timezone": "America/Los_Angeles",
    }
}
CREDS = {
    "gmail_address": "sender@gmail.com",
    "app_password": "apppass",
    "ntfy_topic": "my-topic",
}


def test_send_alert_sends_email_and_push_outside_quiet(mocker):
    mocker.patch("notifier.is_quiet_hours", return_value=False)
    mock_email = mocker.patch("notifier.send_email")
    mock_push = mocker.patch("notifier.send_push")

    from notifier import send_alert
    send_alert(CONFIG, CREDS, [VACANCY_1])

    mock_email.assert_called_once()
    mock_push.assert_called_once()


def test_send_alert_suppresses_push_during_quiet_hours(mocker):
    mocker.patch("notifier.is_quiet_hours", return_value=True)
    mock_email = mocker.patch("notifier.send_email")
    mock_push = mocker.patch("notifier.send_push")

    from notifier import send_alert
    send_alert(CONFIG, CREDS, [VACANCY_1])

    mock_email.assert_called_once()
    mock_push.assert_not_called()


def test_send_alert_force_bypasses_quiet_hours(mocker):
    mocker.patch("notifier.is_quiet_hours", return_value=True)
    mock_email = mocker.patch("notifier.send_email")
    mock_push = mocker.patch("notifier.send_push")

    from notifier import send_alert
    send_alert(CONFIG, CREDS, [VACANCY_1], force=True)

    mock_email.assert_called_once()
    mock_push.assert_called_once()


def test_send_alert_does_nothing_for_empty_vacancies(mocker):
    mock_email = mocker.patch("notifier.send_email")
    mock_push = mocker.patch("notifier.send_push")

    from notifier import send_alert
    send_alert(CONFIG, CREDS, [])

    mock_email.assert_not_called()
    mock_push.assert_not_called()
