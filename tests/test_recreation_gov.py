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


from datetime import date


@resp_mock.activate
def test_get_available_sites_returns_sites_in_date_range(adapter, tmp_path):
    # Seed cache to skip RIDB call
    cache = {"Yosemite National Park": {"ids": ["cg_001"], "fetched_at": "2099-01-01T00:00:00"}}
    (tmp_path / "cache" / "park_lookup.json").write_text(json.dumps(cache))

    resp_mock.add(
        resp_mock.GET,
        f"{AVAIL_BASE}/cg_001/month",
        json={
            "campsites": {
                "site_123": {
                    "site": "Cabin #4",
                    "availabilities": {
                        "2025-07-03T00:00:00Z": "Available",
                        "2025-07-04T00:00:00Z": "Reserved",
                    },
                }
            }
        },
        status=200,
    )

    sites = adapter.get_available_sites(
        "Yosemite National Park",
        [{"start": "2025-07-01", "end": "2025-07-07"}],
    )
    assert len(sites) == 1
    assert sites[0].site_id == "site_123"
    assert sites[0].name == "Cabin #4"
    assert "2025-07-03" in sites[0].available_dates
    assert "2025-07-04" not in sites[0].available_dates


@resp_mock.activate
def test_get_available_sites_excludes_dates_outside_range(adapter, tmp_path):
    cache = {"Yosemite National Park": {"ids": ["cg_001"], "fetched_at": "2099-01-01T00:00:00"}}
    (tmp_path / "cache" / "park_lookup.json").write_text(json.dumps(cache))

    resp_mock.add(
        resp_mock.GET,
        f"{AVAIL_BASE}/cg_001/month",
        json={
            "campsites": {
                "site_456": {
                    "site": "Tent Cabin",
                    "availabilities": {
                        "2025-08-01T00:00:00Z": "Available",  # outside range
                    },
                }
            }
        },
        status=200,
    )

    sites = adapter.get_available_sites(
        "Yosemite National Park",
        [{"start": "2025-07-01", "end": "2025-07-07"}],
    )
    assert len(sites) == 0


@resp_mock.activate
def test_get_available_sites_skips_failed_campground(adapter, tmp_path):
    cache = {"Yosemite National Park": {"ids": ["cg_bad", "cg_good"], "fetched_at": "2099-01-01T00:00:00"}}
    (tmp_path / "cache" / "park_lookup.json").write_text(json.dumps(cache))

    resp_mock.add(resp_mock.GET, f"{AVAIL_BASE}/cg_bad/month", status=500)
    resp_mock.add(
        resp_mock.GET,
        f"{AVAIL_BASE}/cg_good/month",
        json={
            "campsites": {
                "site_789": {
                    "site": "Good Cabin",
                    "availabilities": {"2025-07-03T00:00:00Z": "Available"},
                }
            }
        },
        status=200,
    )

    sites = adapter.get_available_sites(
        "Yosemite National Park",
        [{"start": "2025-07-01", "end": "2025-07-07"}],
    )
    assert len(sites) == 1
    assert sites[0].site_id == "site_789"
