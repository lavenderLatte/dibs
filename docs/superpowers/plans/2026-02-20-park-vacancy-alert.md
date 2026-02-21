# National Park Vacancy Alert System Implementation Plan

> **For Claude:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a free, automated system that monitors Recreation.gov for accommodation vacancies in national parks and sends merged alerts via Gmail and ntfy.sh push notifications on a 10-minute GitHub Actions cron schedule.

**Architecture:** A Python script orchestrates three components: (1) a Recreation.gov adapter that uses the RIDB API for park-name-to-campground-ID lookup and the unofficial availability API for vacancy checking, (2) a state tracker that persists seen vacancies to `state.json` committed back to the repo, and (3) a notifier that delivers merged alerts via Gmail SMTP and ntfy.sh with quiet-hours suppression and 24-hour dedup logic. GitHub Actions triggers the script every 10 minutes.

**Tech Stack:** Python 3.11, requests, PyYAML, pytz, pytest, pytest-mock, responses, smtplib (stdlib), GitHub Actions

---

## File Map

| File | Responsibility |
|---|---|
| `config.yaml` | User-editable monitor configuration (parks, dates, notification settings) |
| `state.json` | Auto-managed living snapshot of alerted vacancies |
| `cache/park_lookup.json` | Auto-managed RIDB lookup cache (24h TTL) |
| `state.py` | Pure functions for reading/writing/querying `state.json` |
| `notifier.py` | Alert formatting, quiet-hours logic, Gmail SMTP send, ntfy.sh send |
| `adapters/__init__.py` | Package marker |
| `adapters/base.py` | `Site` dataclass + `BaseAdapter` abstract interface |
| `adapters/recreation_gov.py` | RIDB lookup + Recreation.gov availability API |
| `main.py` | Orchestration entry point; `--dry-run` and `--test-notify` modes |
| `fixtures/sample_availability.json` | Canned availability data for `--dry-run` |
| `tests/test_state.py` | Unit tests for state management |
| `tests/test_notifier.py` | Unit tests for notification logic |
| `tests/test_recreation_gov.py` | Unit tests for Recreation.gov adapter |
| `tests/test_main.py` | Integration tests for orchestration |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes `__pycache__`, `.env`; does NOT exclude `state.json` or `cache/` |
| `.github/workflows/check.yml` | Cron workflow; commits state back to repo |

---

## Chunk 1: Scaffolding + Recreation.gov Adapter

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `config.yaml`
- Create: `state.json`
- Create: `tests/__init__.py`
- Create: `adapters/__init__.py`
- Create: `fixtures/` (empty dir placeholder)

- [ ] **Step 1: Create `requirements.txt`**

```
requests==2.31.0
PyYAML==6.0.1
pytz==2024.1
pytest==8.0.0
pytest-mock==3.12.0
responses==0.25.0
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
.pytest_cache/
```

Note: `state.json` and `cache/` are intentionally NOT ignored — they must be committed.

- [ ] **Step 3: Create `config.yaml` template**

```yaml
notifications:
  email: you@gmail.com
  # ntfy_topic and Gmail credentials come from GitHub Secrets (NTFY_TOPIC,
  # GMAIL_ADDRESS, GMAIL_APP_PASSWORD) — do not put them here.
  timezone: "America/Los_Angeles"
  quiet_hours:
    start: "23:00"
    end: "06:00"

targets:
  - park: "Yosemite National Park"
    active: true
    date_ranges:
      - start: "2025-07-01"
        end: "2025-07-07"
```

- [ ] **Step 4: Create `state.json`**

```json
{}
```

- [ ] **Step 5: Create package markers**

```bash
touch tests/__init__.py adapters/__init__.py
mkdir -p fixtures cache
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: All packages install without errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore config.yaml state.json tests/__init__.py adapters/__init__.py
git commit -m "chore: project scaffolding"
```

---

### Task 2: Site Dataclass + Base Adapter Interface

**Files:**
- Create: `adapters/base.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_base.py`:

```python
from adapters.base import Site, BaseAdapter
import pytest


def test_site_dataclass_fields():
    site = Site(
        site_id="123",
        campground_id="456",
        name="Curry Cabin",
        park="Yosemite National Park",
        available_dates=["2025-07-03", "2025-07-04"],
        url="https://www.recreation.gov/camping/campsites/123",
    )
    assert site.site_id == "123"
    assert site.park == "Yosemite National Park"
    assert len(site.available_dates) == 2


def test_base_adapter_is_abstract():
    with pytest.raises(TypeError):
        BaseAdapter()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_base.py -v
```

Expected: `ImportError` — `adapters.base` does not exist yet.

- [ ] **Step 3: Create `adapters/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Site:
    site_id: str
    campground_id: str
    name: str
    park: str
    available_dates: list
    url: str


class BaseAdapter(ABC):
    @abstractmethod
    def get_available_sites(self, park_name: str, date_ranges: list) -> list:
        """
        Returns a list of Site objects available within any of the given date ranges.

        Args:
            park_name: Human-readable park name (e.g. "Yosemite National Park")
            date_ranges: list of {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}

        Returns:
            list of Site objects
        """
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_base.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add adapters/base.py tests/test_base.py
git commit -m "feat: add Site dataclass and BaseAdapter interface"
```

---

### Task 3: Recreation.gov Adapter — RIDB Park Lookup

**Files:**
- Create: `adapters/recreation_gov.py`
- Create: `tests/test_recreation_gov.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recreation_gov.py`:

```python
import json
import pytest
import responses as resp_mock
from adapters.recreation_gov import RecreationGovAdapter

RIDB_BASE = "https://ridb.recreation.gov/api/v1"


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_recreation_gov.py -v
```

Expected: `ImportError` — `adapters.recreation_gov` does not exist.

- [ ] **Step 3: Create `adapters/recreation_gov.py` with RIDB lookup**

```python
import json
import os
from datetime import datetime, timezone, timedelta

import requests

from .base import BaseAdapter, Site

RIDB_BASE = "https://ridb.recreation.gov/api/v1"
AVAIL_BASE = "https://www.recreation.gov/api/camps/availability/campground"
CACHE_FILE = "cache/park_lookup.json"
CACHE_TTL_HOURS = 24


class RecreationGovAdapter(BaseAdapter):
    def __init__(self, api_key: str):
        self.api_key = api_key

    # ── Park lookup ────────────────────────────────────────────────────────────

    def get_campground_ids(self, park_name: str) -> list:
        cache = self._load_cache()
        entry = cache.get(park_name)
        if entry and not self._cache_expired(entry["fetched_at"]):
            return entry["ids"]
        ids = self._fetch_campground_ids(park_name)
        cache[park_name] = {
            "ids": ids,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_cache(cache)
        return ids

    def _fetch_campground_ids(self, park_name: str) -> list:
        resp = requests.get(
            f"{RIDB_BASE}/facilities",
            params={"query": park_name, "activity": 9, "full": "true", "limit": 50},
            headers={"apikey": self.api_key},
        )
        resp.raise_for_status()
        return [str(f["FacilityID"]) for f in resp.json().get("RECDATA", [])]

    def _cache_expired(self, fetched_at: str) -> bool:
        fetched = datetime.fromisoformat(fetched_at)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - fetched > timedelta(hours=CACHE_TTL_HOURS)

    def _load_cache(self) -> dict:
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_cache(self, cache: dict):
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)

    # ── Availability (stub — implemented in Task 4) ────────────────────────────

    def get_available_sites(self, park_name: str, date_ranges: list) -> list:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_recreation_gov.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add adapters/recreation_gov.py tests/test_recreation_gov.py
git commit -m "feat: Recreation.gov adapter — RIDB park lookup with 24h cache"
```

---

### Task 4: Recreation.gov Adapter — Availability Check

**Files:**
- Modify: `adapters/recreation_gov.py`
- Modify: `tests/test_recreation_gov.py`

**Recreation.gov availability API:**
```
GET https://www.recreation.gov/api/camps/availability/campground/{campground_id}/month
    ?start_date=YYYY-MM-01T00:00:00.000Z
```

Response shape (relevant fields only):
```json
{
  "campsites": {
    "12345": {
      "site": "Cabin 4",
      "campsite_type": "CABIN NONELECTRIC",
      "availabilities": {
        "2025-07-03T00:00:00Z": "Available",
        "2025-07-04T00:00:00Z": "Reserved"
      }
    }
  }
}
```

- [ ] **Step 1: Append availability tests to `tests/test_recreation_gov.py`**

```python
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
```

- [ ] **Step 2: Run tests to verify the new tests fail**

```bash
pytest tests/test_recreation_gov.py::test_get_available_sites_returns_sites_in_date_range -v
```

Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement `get_available_sites` in `adapters/recreation_gov.py`**

Replace the stub with:

```python
from datetime import date, timedelta

def get_available_sites(self, park_name: str, date_ranges: list) -> list:
    campground_ids = self.get_campground_ids(park_name)
    sites = []
    for cgid in campground_ids:
        sites.extend(self._check_campground(cgid, park_name, date_ranges))
    return sites

def _check_campground(self, campground_id: str, park_name: str, date_ranges: list) -> list:
    months = self._months_to_query(date_ranges)
    raw_sites = {}

    for month_start in months:
        try:
            resp = requests.get(
                f"{AVAIL_BASE}/{campground_id}/month",
                params={"start_date": f"{month_start.isoformat()}T00:00:00.000Z"},
            )
            resp.raise_for_status()
            for site_id, data in resp.json().get("campsites", {}).items():
                if site_id not in raw_sites:
                    raw_sites[site_id] = {"meta": data, "avail": {}}
                raw_sites[site_id]["avail"].update(data.get("availabilities", {}))
        except requests.RequestException:
            continue

    result = []
    for site_id, entry in raw_sites.items():
        available_dates = [
            dt_str[:10]
            for dt_str, status in entry["avail"].items()
            if status == "Available" and self._in_any_range(dt_str[:10], date_ranges)
        ]
        if available_dates:
            result.append(
                Site(
                    site_id=site_id,
                    campground_id=campground_id,
                    name=entry["meta"].get("site", f"Site {site_id}"),
                    park=park_name,
                    available_dates=sorted(available_dates),
                    url=f"https://www.recreation.gov/camping/campsites/{site_id}",
                )
            )
    return result

def _months_to_query(self, date_ranges: list) -> list:
    months = set()
    for dr in date_ranges:
        d = date.fromisoformat(dr["start"]).replace(day=1)
        end = date.fromisoformat(dr["end"])
        while d <= end:
            months.add(d)
            # advance to first day of next month
            if d.month == 12:
                d = d.replace(year=d.year + 1, month=1)
            else:
                d = d.replace(month=d.month + 1)
    return sorted(months)

def _in_any_range(self, date_str: str, date_ranges: list) -> bool:
    night = date.fromisoformat(date_str)
    return any(
        date.fromisoformat(dr["start"]) <= night < date.fromisoformat(dr["end"])
        for dr in date_ranges
    )
```

- [ ] **Step 4: Run all Recreation.gov tests**

```bash
pytest tests/test_recreation_gov.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add adapters/recreation_gov.py tests/test_recreation_gov.py
git commit -m "feat: Recreation.gov adapter — availability check"
```

---

## Chunk 2: State Management + Notifier

---

### Task 5: State Management

**Files:**
- Create: `state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_state.py -v
```

Expected: `ImportError` — `state` module does not exist.

- [ ] **Step 3: Create `state.py`**

```python
import json
from datetime import datetime, timezone, timedelta

STATE_FILE = "state.json"
REALERT_HOURS = 24


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def make_key(site_id: str, date_range_start: str, date_range_end: str) -> str:
    return f"{site_id}_{date_range_start}_{date_range_end}"


def is_new_vacancy(state: dict, key: str) -> bool:
    return key not in state


def should_realert(state: dict, key: str) -> bool:
    if key not in state:
        return False
    first_alerted = datetime.fromisoformat(state[key]["first_alerted"])
    if first_alerted.tzinfo is None:
        first_alerted = first_alerted.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - first_alerted
    return elapsed >= timedelta(hours=REALERT_HOURS)


def add_to_state(state: dict, key: str, vacancy_info: dict):
    state[key] = {"first_alerted": datetime.now(timezone.utc).isoformat(), **vacancy_info}


def reset_timer(state: dict, key: str):
    state[key]["first_alerted"] = datetime.now(timezone.utc).isoformat()


def remove_gone_vacancies(state: dict, current_keys: set) -> dict:
    return {k: v for k, v in state.items() if k in current_keys}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_state.py -v
```

Expected: 11 PASSED.

- [ ] **Step 5: Commit**

```bash
git add state.py tests/test_state.py
git commit -m "feat: state management — load, save, dedup, 24h re-alert logic"
```

---

### Task 6: Notifier — Formatting + Quiet Hours

**Files:**
- Create: `notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_notifier.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_notifier.py -v
```

Expected: `ImportError` — `notifier` does not exist.

- [ ] **Step 3: Create `notifier.py` with quiet hours + formatting**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_notifier.py -v
```

Expected: 10 PASSED.

- [ ] **Step 5: Commit**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "feat: notifier — quiet hours logic and alert formatting"
```

---

### Task 7: Notifier — Email + Push Delivery

**Files:**
- Modify: `notifier.py`
- Modify: `tests/test_notifier.py`

- [ ] **Step 1: Append delivery tests to `tests/test_notifier.py`**

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
pytest tests/test_notifier.py::test_send_email_calls_smtp_with_correct_args -v
```

Expected: FAIL — `send_email` not defined in `notifier`.

- [ ] **Step 3: Add delivery functions to `notifier.py`**

Append to the existing file:

```python
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
    requests.post(
        f"https://ntfy.sh/{ntfy_topic}",
        data=body.encode("utf-8"),
        headers=headers,
    )


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

    quiet = is_quiet_hours(notif["timezone"]) if not force else False
    if not quiet:
        send_push(creds["ntfy_topic"], push_title, push_body, first_url)
```

- [ ] **Step 4: Run all notifier tests**

```bash
pytest tests/test_notifier.py -v
```

Expected: 18 PASSED.

- [ ] **Step 5: Commit**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "feat: notifier — Gmail SMTP and ntfy.sh delivery with quiet hours"
```

---

## Chunk 3: Main Orchestrator + GitHub Actions

---

### Task 8: Main Orchestrator + Run Modes

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`
- Create: `fixtures/sample_availability.json`

- [ ] **Step 1: Create `fixtures/sample_availability.json`**

```json
{
  "Yosemite National Park": [
    {
      "site_id": "fixture_001",
      "campground_id": "232447",
      "name": "Curry Village Cabin #4",
      "park": "Yosemite National Park",
      "available_dates": ["2025-07-03", "2025-07-04"],
      "url": "https://www.recreation.gov/camping/campsites/fixture_001"
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_main.py`:

```python
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

CONFIG = {
    "notifications": {
        "email": "to@example.com",
        "ntfy_topic": "my-topic",
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


def test_multiple_date_ranges_create_separate_keys_and_single_alert(mocker):
    """Two date ranges for same park → two state keys, one merged alert."""
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

    # One state key per (site, date_range) pair
    assert "fixture_001_2025-07-01_2025-07-07" in final_state
    assert "fixture_001_2025-08-01_2025-08-07" in final_state
    # Alert fired exactly once with all vacancies merged
    mock_alert.assert_called_once()
    vacancies_sent = mock_alert.call_args[0][2]
    assert len(vacancies_sent) == 2


def test_dry_run_does_not_write_state(mocker, tmp_path):
    import json as _json
    state_file = tmp_path / "state.json"
    state_file.write_text("{}")
    mocker.patch("main.send_alert")

    from main import run
    run(config=CONFIG, creds=CREDS, state={}, dry_run=True, test_notify=False, adapter=None)

    # state.json must remain unchanged (run() returns state but __main__ skips save_state on dry-run)
    assert _json.loads(state_file.read_text()) == {}
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_main.py -v
```

Expected: `ImportError` — `main` does not exist.

- [ ] **Step 4: Create `main.py`**

```python
import argparse
import json
import os
import sys

import yaml

from adapters.recreation_gov import RecreationGovAdapter
from notifier import send_alert
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


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_creds() -> dict:
    return {
        "gmail_address": os.environ["GMAIL_ADDRESS"],
        "app_password": os.environ["GMAIL_APP_PASSWORD"],
        "ntfy_topic": os.environ["NTFY_TOPIC"],
    }


def run(config: dict, creds: dict, state: dict, dry_run: bool, test_notify: bool, adapter) -> dict:
    """
    Core logic. Returns final state dict.
    Separated from __main__ to allow unit testing without env vars or real files.
    """
    all_new_vacancies = []
    current_keys = set()

    for target in config.get("targets", []):
        if not target.get("active", False):
            continue

        park = target["park"]
        date_ranges = target["date_ranges"]

        if dry_run:
            with open("fixtures/sample_availability.json") as f:
                fixture = json.load(f)
            raw_sites = fixture.get(park, [])
            from adapters.base import Site
            sites = [Site(**s) for s in raw_sites]
        else:
            try:
                sites = adapter.get_available_sites(park, date_ranges)
            except Exception as e:
                print(f"ERROR fetching {park}: {e}", file=sys.stderr)
                continue

        for site in sites:
            for dr in date_ranges:
                key = make_key(site.site_id, dr["start"], dr["end"])
                current_keys.add(key)
                vacancy_info = {
                    "park": park,
                    "name": site.name,
                    "dates": f"{dr['start']} to {dr['end']}",
                    "url": site.url,
                }
                if is_new_vacancy(state, key):
                    add_to_state(state, key, vacancy_info)
                    all_new_vacancies.append(vacancy_info)
                elif should_realert(state, key):
                    reset_timer(state, key)
                    all_new_vacancies.append(vacancy_info)

    state = remove_gone_vacancies(state, current_keys)

    if dry_run:
        print(f"[DRY RUN] Would alert for {len(all_new_vacancies)} vacancy(ies):")
        for v in all_new_vacancies:
            print(f"  - {v['name']} ({v['park']}): {v['url']}")
    elif test_notify:
        payload = all_new_vacancies or [{
            "park": "Test Park",
            "name": "Test Site",
            "dates": "test",
            "url": "https://www.recreation.gov",
        }]
        send_alert(config, creds, payload, force=True)
    else:
        if all_new_vacancies:
            send_alert(config, creds, all_new_vacancies)

    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="National park vacancy checker")
    parser.add_argument("--dry-run", action="store_true", help="Use fixture data, print alerts, do not send")
    parser.add_argument("--test-notify", action="store_true", help="Send real test notification immediately")
    args = parser.parse_args()

    cfg = load_config()
    creds = load_creds()
    state = load_state()
    adapter = RecreationGovAdapter(api_key=os.environ["RIDB_API_KEY"])

    final_state = run(
        config=cfg,
        creds=creds,
        state=state,
        dry_run=args.dry_run,
        test_notify=args.test_notify,
        adapter=adapter,
    )

    if not args.dry_run:
        save_state(final_state)
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/test_main.py -v
```

Expected: 8 PASSED.

- [ ] **Step 6: Run full test suite to catch regressions**

```bash
pytest -v
```

Expected: All PASSED.

- [ ] **Step 7: Commit**

```bash
git add main.py fixtures/sample_availability.json tests/test_main.py
git commit -m "feat: main orchestrator with --dry-run and --test-notify modes"
```

---

### Task 9: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/check.yml`

- [ ] **Step 1: Create `.github/workflows/check.yml`**

```bash
mkdir -p .github/workflows
```

```yaml
name: Check Park Vacancies

on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch:  # allows manual trigger from GitHub UI

jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # needed to commit state.json back

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run vacancy checker
        env:
          RIDB_API_KEY: ${{ secrets.RIDB_API_KEY }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: python main.py

      - name: Commit updated state
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state.json cache/
          git diff --staged --quiet || git commit -m "chore: update vacancy state [skip ci]"
          git push
```

Note: `[skip ci]` in the commit message prevents the commit from triggering another workflow run.

Note on `NTFY_TOPIC`: credentials (Gmail + ntfy topic) are loaded exclusively from GitHub Secrets at runtime — not from `config.yaml`. The `ntfy_topic` field in `config.yaml` is intentionally absent. If a user sets `NTFY_TOPIC` in Secrets, that is the single source of truth.

- [ ] **Step 2: Verify workflow file is valid YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/check.yml'))"
```

Expected: No output (parses without error).

- [ ] **Step 3: Run full test suite one final time**

```bash
pytest -v
```

Expected: All PASSED.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/check.yml
git commit -m "feat: GitHub Actions cron workflow — runs every 10 minutes"
```

---

## Setup Instructions (after implementation)

These steps are for the user after the code is merged:

1. **Get a free RIDB API key** at [ridb.recreation.gov](https://ridb.recreation.gov) → Register → API Keys
2. **Get a Gmail app password**: Google Account → Security → 2-Step Verification → App passwords → generate one for "Mail"
3. **Pick an ntfy.sh topic**: Any unique string, e.g. `hanara-park-alerts`. Install the ntfy app on your phone and subscribe to it.
4. **Add GitHub Secrets**: Repo → Settings → Secrets and variables → Actions → New repository secret:
   - `RIDB_API_KEY`
   - `GMAIL_ADDRESS`
   - `GMAIL_APP_PASSWORD`
   - `NTFY_TOPIC`
5. **Test notifications**: `python main.py --test-notify`
6. **Test logic**: `python main.py --dry-run`
7. **Edit `config.yaml`** with your real parks and dates, commit and push.
