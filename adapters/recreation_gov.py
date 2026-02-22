import json
import os
from datetime import date, datetime, timezone, timedelta

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

    # ── Availability ───────────────────────────────────────────────────────────

    def get_available_sites(self, park_name: str, date_ranges: list[dict]) -> list["Site"]:
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
            except (requests.RequestException, json.JSONDecodeError):
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
