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
