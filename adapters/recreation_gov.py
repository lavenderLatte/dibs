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

    def get_available_sites(self, park_name: str, date_ranges: list[dict]) -> list["Site"]:
        raise NotImplementedError
