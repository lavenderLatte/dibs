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
