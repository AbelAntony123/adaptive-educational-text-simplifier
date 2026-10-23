"""Keep previous results for the current browser session only.

The functions take any dict-like ``state`` (Streamlit's ``st.session_state`` in
the app, a plain dict in tests). Nothing is saved to disk.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, MutableMapping

HISTORY_KEY = "history"
COUNTER_KEY = "history_counter"
MAX_ENTRIES = 25


def init_history(state: MutableMapping) -> None:
    if HISTORY_KEY not in state:
        state[HISTORY_KEY] = []
    if COUNTER_KEY not in state:
        state[COUNTER_KEY] = 0


def add_entry(state: MutableMapping, result: dict) -> dict:
    """Store a copy of ``result`` (newest first) and return the stored entry."""
    init_history(state)
    state[COUNTER_KEY] += 1
    entry = copy.deepcopy(result)
    entry["id"] = state[COUNTER_KEY]
    entry["created_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    state[HISTORY_KEY] = [entry] + list(state[HISTORY_KEY])[: MAX_ENTRIES - 1]
    return entry


def get_entries(state: MutableMapping) -> list[dict]:
    init_history(state)
    return list(state[HISTORY_KEY])


def get_entry(state: MutableMapping, entry_id: Any) -> dict | None:
    for entry in get_entries(state):
        if entry["id"] == entry_id:
            return entry
    return None


def clear_history(state: MutableMapping) -> None:
    state[HISTORY_KEY] = []
