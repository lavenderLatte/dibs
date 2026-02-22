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
