import json
import pytest
import responses as resp_mock
from adapters.recreation_gov import RecreationGovAdapter

RIDB_BASE = "https://ridb.recreation.gov/api/v1"
AVAIL_BASE = "https://www.recreation.gov/api/camps/availability/campground"


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cache").mkdir()
    return RecreationGovAdapter(api_key="test-key")


@resp_mock.activate
def test_get_campground_ids_calls_ridb(adapter):
    resp_mock.add(
        resp_mock.GET,
        f"{RIDB_BASE}/facilities",
        json={
            "RECDATA": [
                {"FacilityID": "111"},
                {"FacilityID": "222"},
            ]
        },
        status=200,
    )
    ids = adapter.get_campground_ids("Yosemite National Park")
    assert ids == ["111", "222"]
    assert resp_mock.calls[0].request.headers["apikey"] == "test-key"
    assert "Yosemite" in resp_mock.calls[0].request.url


@resp_mock.activate
def test_get_campground_ids_uses_cache(adapter, tmp_path):
    cache_data = {
        "Yosemite National Park": {
            "ids": ["333"],
            "fetched_at": "2099-01-01T00:00:00",
        }
    }
    (tmp_path / "cache" / "park_lookup.json").write_text(json.dumps(cache_data))

    ids = adapter.get_campground_ids("Yosemite National Park")
    assert ids == ["333"]
    assert len(resp_mock.calls) == 0  # no HTTP call made


@resp_mock.activate
def test_get_campground_ids_refreshes_expired_cache(adapter, tmp_path):
    from datetime import datetime, timezone, timedelta
    expired_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    cache_data = {
        "Yosemite National Park": {
            "ids": ["old"],
            "fetched_at": expired_time,
        }
    }
    (tmp_path / "cache" / "park_lookup.json").write_text(json.dumps(cache_data))

    resp_mock.add(
        resp_mock.GET,
        f"{RIDB_BASE}/facilities",
        json={"RECDATA": [{"FacilityID": "fresh"}]},
        status=200,
    )
    ids = adapter.get_campground_ids("Yosemite National Park")
    assert ids == ["fresh"]
    assert len(resp_mock.calls) == 1
