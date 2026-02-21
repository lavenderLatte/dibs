# National Park Vacancy Alert System — Design Spec

**Date:** 2026-02-20
**Status:** Approved

---

## Overview

A free, automated system that monitors Recreation.gov for cabin and accommodation vacancies in specified national parks across user-defined date ranges. Alerts are delivered via email and phone push notification (ntfy.sh). Runs entirely on GitHub Actions — no server required.

---

## Goals

- Alert the user as soon as any accommodation opens up in a watched park and date range
- Require zero recurring cost
- Be extensible to additional booking platforms in the future
- Minimize alert noise (merged alerts, dedup, quiet hours)

---

## Stack

| Concern | Tool | Cost |
|---|---|---|
| Scheduling | GitHub Actions cron (public repo) | Free |
| Availability data | Recreation.gov availability API + RIDB API | Free |
| Push notifications | ntfy.sh | Free |
| Email notifications | Gmail SMTP with app password | Free |
| State persistence | `state.json` committed back to repo | Free |

---

## Repository Structure

```
repo-root/
├── config.yaml                  ← user edits to add/remove monitors
├── state.json                   ← auto-managed, tracks seen vacancies
├── cache/
│   └── park_lookup.json         ← auto-managed, RIDB results cached 24h
├── main.py                      ← entry point, orchestrates everything
├── notifier.py                  ← Gmail + ntfy.sh, quiet hours, dedup
├── adapters/
│   ├── base.py                  ← abstract adapter interface
│   └── recreation_gov.py        ← Recreation.gov API implementation
├── fixtures/
│   └── sample_availability.json ← canned response for dry-run/tests
├── tests/
│   └── test_*.py                ← unit tests
└── .github/
    └── workflows/
        └── check.yml            ← cron every 10 min
```

---

## Configuration

`config.yaml` lives at the repo root. The user edits this file and pushes to GitHub to add, modify, or toggle monitors.

```yaml
notifications:
  email: you@gmail.com
  ntfy_topic: your-ntfy-topic
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
      - start: "2025-08-10"
        end: "2025-08-15"

  - park: "Zion National Park"
    active: false
    date_ranges:
      - start: "2025-09-01"
        end: "2025-09-05"
```

- Set `active: false` to pause a monitor without deleting it
- Multiple date ranges per park are supported
- Multiple parks supported

---

## How It Works

### Park Name → Campground IDs

The RIDB API (Recreation.gov's official free API, requires a free API key) is used to look up all campground/facility IDs within a named national park. This lookup result is cached in `cache/park_lookup.json` with a 24-hour TTL to avoid repeated API calls. The cache file is committed to the repo alongside `state.json`.

### Availability Check

For each active target and date range, the Recreation.gov availability API is queried per campground:

```
GET https://www.recreation.gov/api/camps/availability/campground/{id}/month
    ?start_date=YYYY-MM-01T00:00:00.000Z
```

All available accommodations (cabins, tent cabins, rooms, etc.) across all campgrounds in the park are collected.

### State Tracking

`state.json` is a living snapshot of currently open vacancies that have been alerted. Keys are scoped to `{site_id}_{start_date}_{end_date}` so the same physical site watched across multiple date ranges is tracked independently (each with its own 24h dedup timer):

```json
{
  "site_123_2025-07-03_2025-07-05": {
    "first_alerted": "2026-02-20T10:00:00",
    "park": "Yosemite National Park",
    "name": "Curry Village Cabin #4",
    "dates": "Jul 3–5",
    "url": "https://www.recreation.gov/camping/campsites/123"
  }
}
```

On every run:
- **New vacancy** (not in state) → alert + add to state with `first_alerted: now`
- **Existing vacancy still open, under 24h** → no alert, keep in state
- **Existing vacancy still open, over 24h** → re-alert, reset `first_alerted`
- **Vacancy gone (booked)** → remove from state, no alert

### Alert Logic

All new vacancies for a given run are merged into a single notification:

**Push notification (ntfy.sh):**
```
Title: 🏕️ Yosemite — 2 vacancies found
Body:  Curry Village Cabin #4 (Jul 3–5) + 1 more
       [link to first result]
```

**Email:**
```
Subject: 🏕️ Vacancy Alert — Yosemite National Park

2 accommodations just opened for your watched dates:

• Curry Village Cabin #4 — Jul 3–5
  Book now: https://recreation.gov/...

• High Sierra Camp Tent Cabin — Jul 10–12
  Book now: https://recreation.gov/...
```

### Quiet Hours

Between 11pm–6am (user's configured timezone):
- Email is still sent
- Push notification is suppressed

### Deduplication

A vacancy is only re-alerted after it has been continuously open for 24 hours. This prevents spam while still reminding the user of lingering opportunities.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Recreation.gov API down / rate-limited | Skip run, log error, do not update state |
| Email send fails | Log failure, do not update `first_alerted` (retry next run) |
| ntfy.sh send fails | Log failure, do not update `first_alerted` (retry next run) |
| GitHub Actions run fails | GitHub sends automatic failure email to repo owner |

---

## Testing

### Unit Tests

`tests/` covers all core logic with mocked API responses and mocked system time:

| Test case | Description |
|---|---|
| New vacancy | state empty, API returns sites → alert sent |
| No new vacancy | site in state + API, under 24h → no alert |
| Re-alert after 24h | site in state over 24h → re-alert, timer reset |
| Vacancy booked | site in state, API no longer returns it → removed from state |
| Merged alert | 3 new vacancies → one notification |
| Quiet hours — push suppressed | new vacancy at 2am → email only |
| Quiet hours — push allowed | new vacancy at 10am → email + push |
| Multiple date ranges | vacancies across two date windows → merged into one alert |

### Run Modes

- `--dry-run`: Uses `fixtures/sample_availability.json` instead of live API. Prints what would be sent without sending anything. Use to verify logic and config.
- `--test-notify`: Hits live API but also sends a real test notification immediately (bypasses quiet hours and dedup). Use once during setup to confirm Gmail and ntfy.sh are wired correctly.

---

## Extensibility

`adapters/base.py` defines a simple interface that all platform adapters implement:

```python
class BaseAdapter:
    def get_available_sites(self, park_name: str, date_ranges: list) -> list[Site]:
        raise NotImplementedError
```

Adding a new platform (Hipcamp, state parks, etc.) means writing one new file in `adapters/` and referencing it in `config.yaml` — no changes to core logic.

---

## Setup Requirements (one-time)

1. Free RIDB API key from ridb.recreation.gov
2. Gmail app password (2-step verification required)
3. ntfy.sh topic (choose any unique string, no account needed)
4. GitHub Secrets: `RIDB_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `NTFY_TOPIC`
