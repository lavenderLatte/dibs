import json
from datetime import datetime, timezone, timedelta

import pytest

from state import (
    load_state,
    save_state,
    make_key,
    is_new_vacancy,
    should_realert,
    add_to_state,
    reset_timer,
    remove_gone_vacancies,
)


@pytest.fixture(autouse=True)
def use_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_load_state_missing_file():
    assert load_state() == {}


def test_load_state_existing_file(tmp_path):
    data = {"key1": {"first_alerted": "2026-01-01T00:00:00+00:00", "park": "Yosemite"}}
    (tmp_path / "state.json").write_text(json.dumps(data))
    assert load_state() == data


def test_save_and_load_roundtrip():
    state = {"site_1_2025-07-01_2025-07-07": {"first_alerted": "2026-01-01T00:00:00+00:00"}}
    save_state(state)
    assert load_state() == state


def test_make_key():
    assert make_key("site_123", "2025-07-01", "2025-07-07") == "site_123_2025-07-01_2025-07-07"


def test_is_new_vacancy_true():
    assert is_new_vacancy({}, "site_123_2025-07-01_2025-07-07") is True


def test_is_new_vacancy_false():
    state = {"site_123_2025-07-01_2025-07-07": {"first_alerted": "2026-01-01T00:00:00+00:00"}}
    assert is_new_vacancy(state, "site_123_2025-07-01_2025-07-07") is False


def test_should_realert_after_24h():
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    assert should_realert({"key1": {"first_alerted": past}}, "key1") is True


def test_should_not_realert_before_24h():
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert should_realert({"key1": {"first_alerted": recent}}, "key1") is False


def test_should_not_realert_unknown_key():
    assert should_realert({}, "unknown") is False


def test_add_to_state_sets_fields():
    state = {}
    add_to_state(state, "key1", {"park": "Yosemite", "name": "Cabin", "dates": "Jul 1-5", "url": "https://rec.gov"})
    assert state["key1"]["park"] == "Yosemite"
    assert "first_alerted" in state["key1"]


def test_reset_timer_updates_timestamp():
    old_time = "2020-01-01T00:00:00+00:00"
    state = {"key1": {"first_alerted": old_time, "park": "Yosemite"}}
    reset_timer(state, "key1")
    assert state["key1"]["first_alerted"] != old_time


def test_remove_gone_vacancies():
    state = {
        "key1": {"first_alerted": "2026-01-01", "park": "Yosemite"},
        "key2": {"first_alerted": "2026-01-01", "park": "Zion"},
    }
    result = remove_gone_vacancies(state, {"key1"})
    assert "key1" in result
    assert "key2" not in result
