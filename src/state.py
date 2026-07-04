"""Tracks item IDs that were already analyzed, so daily runs only pay for new content."""

import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "seen_ids.json"


def item_key(item: dict) -> str:
    return f"{item.get('source', 'unknown')}:{item.get('id', '')}"


def load_seen_ids() -> set:
    if STATE_PATH.exists():
        return set(json.loads(STATE_PATH.read_text()))
    return set()


def save_seen_ids(seen: set) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(sorted(seen), indent=2) + "\n")
