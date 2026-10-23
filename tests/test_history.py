from services.backend_adapter import simplify
from services.mock_data import SAMPLE_TEXT
from ui.history import MAX_ENTRIES, add_entry, clear_history, get_entries, get_entry, init_history


def run(level="Beginner"):
    return simplify(SAMPLE_TEXT, level, mode="mock")


def test_history_starts_empty():
    state = {}
    init_history(state)
    assert get_entries(state) == []


def test_newest_entry_comes_first_with_unique_ids():
    state = {}
    first = add_entry(state, run("Beginner"))
    second = add_entry(state, run("Advanced"))
    assert [e["id"] for e in get_entries(state)] == [second["id"], first["id"]]
    assert first["id"] != second["id"]


def test_entry_records_time_and_source():
    entry = add_entry({}, run())
    assert entry["created_at"]
    assert entry["source"] == "mock"


def test_stored_entry_is_a_copy():
    state = {}
    result = run()
    add_entry(state, result)
    result["level"] = "changed"
    assert get_entries(state)[0]["level"] == "Beginner"


def test_get_entry_by_id_and_missing_id():
    state = {}
    entry = add_entry(state, run())
    assert get_entry(state, entry["id"])["id"] == entry["id"]
    assert get_entry(state, 999) is None


def test_history_is_capped():
    state = {}
    for _ in range(MAX_ENTRIES + 5):
        add_entry(state, run())
    assert len(get_entries(state)) == MAX_ENTRIES


def test_clear_history_keeps_ids_unique():
    state = {}
    old = add_entry(state, run())
    clear_history(state)
    assert get_entries(state) == []
    assert add_entry(state, run())["id"] != old["id"]
