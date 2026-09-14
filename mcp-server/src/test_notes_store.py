"""
Unit tests for notes_store: the path fence and the persistence round-trip.

Run from the mcp-server/ folder:
    python src/test_notes_store.py

The fence tests feed deliberate traversal payloads (``../..`` chains, absolute
paths) and assert each is refused with a ValueError that names the path -- not
silently resolved, not silently returning nothing. Each refusal is printed so
you can see exactly what the caller would get back.

Exits 0 when the fence holds and persistence works, 1 (with a message) on any
regression -- same gating role as test_connection.py.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from notes_store import (  # noqa: E402  (path insert must come first)
    DATA_ROOT,
    NOTES_FILENAME,
    load_notes,
    resolve_within,
    save_notes,
)


def _run(name, fn):
    try:
        fn()
    except AssertionError as exc:
        print(f"FAIL: {name}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"PASS: {name}")


def test_allows_the_notes_file():
    resolved = resolve_within(DATA_ROOT, NOTES_FILENAME)
    assert resolved == DATA_ROOT.resolve() / NOTES_FILENAME
    assert resolved.is_relative_to(DATA_ROOT.resolve())


def test_rejects_dotdot_traversal():
    payloads = [
        "../../etc/hosts",
        "../../../../etc/passwd",
        "notes/../../../secret.txt",
    ]
    for payload in payloads:
        try:
            resolve_within(DATA_ROOT, payload)
        except ValueError as exc:
            print(f"       refused {payload!r} -> {exc}")
            continue
        raise AssertionError(f"{payload!r} was NOT refused")


def test_rejects_absolute_path_outside_root():
    outside = "C:\\Windows\\win.ini" if sys.platform == "win32" else "/etc/hosts"
    try:
        resolve_within(DATA_ROOT, outside)
    except ValueError as exc:
        print(f"       refused {outside!r} -> {exc}")
        return
    raise AssertionError(f"{outside!r} was NOT refused")


def test_persistence_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        seeded = load_notes(root)
        assert (root / NOTES_FILENAME).exists(), "first load did not create the store file"
        assert isinstance(seeded, list) and seeded, "seeded store should be a non-empty list"

        seeded.append(
            {"id": "marker", "title": "persisted", "content": "x", "created_at": "now"}
        )
        save_notes(seeded, root)

        reloaded = load_notes(root)
        assert any(n["id"] == "marker" for n in reloaded), "saved note did not survive reload"


def test_corrupt_store_errors_loudly():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / NOTES_FILENAME).write_text("{ not valid json", encoding="utf-8")
        try:
            load_notes(root)
        except RuntimeError as exc:
            print(f"       corrupt store raised -> {exc}")
            return
        raise AssertionError("corrupt store was read as empty instead of raising")


if __name__ == "__main__":
    _run("fence allows the notes file", test_allows_the_notes_file)
    _run("fence rejects ../ traversal", test_rejects_dotdot_traversal)
    _run("fence rejects absolute path outside root", test_rejects_absolute_path_outside_root)
    _run("persistence round-trips", test_persistence_round_trip)
    _run("corrupt store errors loudly", test_corrupt_store_errors_loudly)
    print("\nALL PASS: fence holds, persistence works.")
