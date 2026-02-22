import json
import pytest
from unittest.mock import patch, MagicMock
from adapters.base import Site

FIXTURE_SITE = Site(
    site_id="fixture_001",
    campground_id="232447",
    name="Curry Village Cabin #4",
    park="Yosemite National Park",
    available_dates=["2025-07-03", "2025-07-04"],
    url="https://www.recreation.gov/camping/campsites/fixture_001",
)

# Same site but with availability spanning two date ranges (July and August)
FIXTURE_SITE_BOTH_RANGES = Site(
    site_id="fixture_001",
    campground_id="232447",
    name="Curry Village Cabin #4",
    park="Yosemite National Park",
    available_dates=["2025-07-03", "2025-07-04", "2025-08-02", "2025-08-03"],
    url="https://www.recreation.gov/camping/campsites/fixture_001",
)

CONFIG = {
    "notifications": {
        "timezone": "America/Los_Angeles",
    },
    "targets": [
        {
            "park": "Yosemite National Park",
            "active": True,
            "date_ranges": [{"start": "2025-07-01", "end": "2025-07-07"}],
        }
    ],
}

CREDS = {
    "gmail_address": "sender@gmail.com",
    "app_password": "apppass",
    "ntfy_topic": "my-topic",
}


@pytest.fixture(autouse=True)
def use_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state.json").write_text("{}")
    (tmp_path / "fixtures").mkdir()
    fixture_data = {"Yosemite National Park": [
        {
            "site_id": "fixture_001",
            "campground_id": "232447",
            "name": "Curry Village Cabin #4",
            "park": "Yosemite National Park",
            "available_dates": ["2025-07-03", "2025-07-04"],
            "url": "https://www.recreation.gov/camping/campsites/fixture_001",
        }
    ]}
    (tmp_path / "fixtures" / "sample_availability.json").write_text(json.dumps(fixture_data))


def test_skips_inactive_target(mocker):
    config = {**CONFIG, "targets": [{**CONFIG["targets"][0], "active": False}]}
    mock_alert = mocker.patch("main.send_alert")

    from main import run
    run(config=config, creds=CREDS, state={}, dry_run=False, test_notify=False, adapter=MagicMock())

    mock_alert.assert_not_called()


def test_new_vacancy_triggers_alert(mocker):
    mock_adapter = MagicMock()
    mock_adapter.get_available_sites.return_value = [FIXTURE_SITE]
    mock_alert = mocker.patch("main.send_alert")

    from main import run
    final_state = run(config=CONFIG, creds=CREDS, state={}, dry_run=False, test_notify=False, adapter=mock_adapter)

    mock_alert.assert_called_once()
    key = "fixture_001_2025-07-01_2025-07-07"
    assert key in final_state


def test_existing_vacancy_under_24h_no_alert(mocker):
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    existing_state = {
        "fixture_001_2025-07-01_2025-07-07": {
            "first_alerted": recent,
            "park": "Yosemite National Park",
            "name": "Curry Village Cabin #4",
            "dates": "2025-07-01 to 2025-07-07",
            "url": "https://www.recreation.gov/camping/campsites/fixture_001",
        }
    }
    mock_adapter = MagicMock()
    mock_adapter.get_available_sites.return_value = [FIXTURE_SITE]
    mock_alert = mocker.patch("main.send_alert")

    from main import run
    run(config=CONFIG, creds=CREDS, state=existing_state, dry_run=False, test_notify=False, adapter=mock_adapter)

    mock_alert.assert_not_called()


def test_gone_vacancy_removed_from_state(mocker):
    existing_state = {
        "fixture_001_2025-07-01_2025-07-07": {
            "first_alerted": "2026-01-01T00:00:00+00:00",
            "park": "Yosemite",
        }
    }
    mock_adapter = MagicMock()
    mock_adapter.get_available_sites.return_value = []  # gone
    mocker.patch("main.send_alert")

    from main import run
    final_state = run(config=CONFIG, creds=CREDS, state=existing_state, dry_run=False, test_notify=False, adapter=mock_adapter)

    assert "fixture_001_2025-07-01_2025-07-07" not in final_state


def test_dry_run_uses_fixture_and_does_not_send(mocker, capsys):
    mock_alert = mocker.patch("main.send_alert")

    from main import run
    run(config=CONFIG, creds=CREDS, state={}, dry_run=True, test_notify=False, adapter=None)

    mock_alert.assert_not_called()
    captured = capsys.readouterr()
    assert "[DRY RUN]" in captured.out


def test_adapter_error_skips_target(mocker):
    mock_adapter = MagicMock()
    mock_adapter.get_available_sites.side_effect = Exception("API down")
    mock_alert = mocker.patch("main.send_alert")

    from main import run
    run(config=CONFIG, creds=CREDS, state={}, dry_run=False, test_notify=False, adapter=mock_adapter)

    mock_alert.assert_not_called()


def test_multiple_date_ranges_separate_keys_when_site_available_in_both(mocker):
    """Site available in both ranges → two state keys, one merged alert."""
    config_two_ranges = {
        **CONFIG,
        "targets": [
            {
                "park": "Yosemite National Park",
                "active": True,
                "date_ranges": [
                    {"start": "2025-07-01", "end": "2025-07-07"},
                    {"start": "2025-08-01", "end": "2025-08-07"},
                ],
            }
        ],
    }
    mock_adapter = MagicMock()
    mock_adapter.get_available_sites.return_value = [FIXTURE_SITE_BOTH_RANGES]
    mock_alert = mocker.patch("main.send_alert")

    from main import run
    final_state = run(
        config=config_two_ranges,
        creds=CREDS,
        state={},
        dry_run=False,
        test_notify=False,
        adapter=mock_adapter,
    )

    # One state key per (site, date_range) pair
    assert "fixture_001_2025-07-01_2025-07-07" in final_state
    assert "fixture_001_2025-08-01_2025-08-07" in final_state
    # Alert fired exactly once with all vacancies merged
    mock_alert.assert_called_once()
    vacancies_sent = mock_alert.call_args[0][2]
    assert len(vacancies_sent) == 2


def test_no_false_positive_when_site_available_in_only_one_range(mocker):
    """Site available only in first range → one state key, not two."""
    config_two_ranges = {
        **CONFIG,
        "targets": [
            {
                "park": "Yosemite National Park",
                "active": True,
                "date_ranges": [
                    {"start": "2025-07-01", "end": "2025-07-07"},
                    {"start": "2025-08-01", "end": "2025-08-07"},
                ],
            }
        ],
    }
    mock_adapter = MagicMock()
    # FIXTURE_SITE only has July dates — no August availability
    mock_adapter.get_available_sites.return_value = [FIXTURE_SITE]
    mock_alert = mocker.patch("main.send_alert")

    from main import run
    final_state = run(
        config=config_two_ranges,
        creds=CREDS,
        state={},
        dry_run=False,
        test_notify=False,
        adapter=mock_adapter,
    )

    assert "fixture_001_2025-07-01_2025-07-07" in final_state
    assert "fixture_001_2025-08-01_2025-08-07" not in final_state
    mock_alert.assert_called_once()
    vacancies_sent = mock_alert.call_args[0][2]
    assert len(vacancies_sent) == 1


def test_dry_run_does_not_write_state(mocker, tmp_path):
    import json as _json
    state_file = tmp_path / "state.json"
    state_file.write_text("{}")
    mocker.patch("main.send_alert")

    from main import run
    run(config=CONFIG, creds=CREDS, state={}, dry_run=True, test_notify=False, adapter=None)

    # state.json must remain unchanged (run() returns state but __main__ skips save_state on dry-run)
    assert _json.loads(state_file.read_text()) == {}
