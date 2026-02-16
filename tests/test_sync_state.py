"""Tests for sync state persistence layer.

Covers:
- Load returns empty state when file doesn't exist
- Save creates file atomically (verify file exists after save)
- Save/load round-trip preserves all fields
- content_hash produces consistent results for identical content
- content_hash normalizes BOM, CRLF, trailing whitespace
- content_hash produces different results for different content
- update_entry/get_entry/remove_entry
- is_conflicted
"""

from __future__ import annotations

from pathlib import Path

from trac_mcp_server.sync.state import SyncState

# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


class TestSyncStateLoad:
    """Tests for SyncState.load()."""

    def test_load_returns_empty_state_when_file_missing(
        self, tmp_path: Path
    ):
        """load() returns a well-formed empty state when no file exists."""
        ss = SyncState(tmp_path / "nonexistent")
        state = ss.load("myprofile")
        assert state == {
            "version": 1,
            "last_sync": None,
            "profile": "myprofile",
            "entries": {},
        }

    def test_load_returns_empty_entries_dict(self, tmp_path: Path):
        """Empty state has an entries dict, not None or missing key."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        assert isinstance(state["entries"], dict)
        assert len(state["entries"]) == 0


class TestSyncStateSave:
    """Tests for SyncState.save()."""

    def test_save_creates_file(self, tmp_path: Path):
        """save() creates the state file on disk."""
        state_dir = tmp_path / ".trac_mcp"
        ss = SyncState(state_dir)
        state = ss.load("demo")
        ss.save("demo", state)

        path = state_dir / "sync_demo.json"
        assert path.exists()
        assert path.is_file()

    def test_save_creates_state_dir_if_needed(self, tmp_path: Path):
        """save() creates state_dir when it doesn't exist yet."""
        state_dir = tmp_path / "nested" / "deep" / ".trac_mcp"
        ss = SyncState(state_dir)
        state = ss.load("x")
        ss.save("x", state)
        assert state_dir.exists()

    def test_save_sets_last_sync_timestamp(self, tmp_path: Path):
        """save() updates last_sync to a non-None ISO 8601 timestamp."""
        ss = SyncState(tmp_path)
        state = ss.load("ts")
        assert state["last_sync"] is None
        ss.save("ts", state)
        assert state["last_sync"] is not None
        # Basic ISO 8601 sanity check
        assert "T" in state["last_sync"]


class TestSyncStateRoundTrip:
    """Tests for save/load round-trip fidelity."""

    def test_round_trip_preserves_all_fields(self, tmp_path: Path):
        """save() followed by load() returns the same state."""
        ss = SyncState(tmp_path)
        state = {
            "version": 1,
            "last_sync": None,
            "profile": "roundtrip",
            "entries": {
                "docs/README.md": {
                    "local_path": "docs/README.md",
                    "wiki_page": "Docs/README",
                    "local_hash": "abc123",
                    "remote_hash": "def456",
                    "remote_version": 3,
                    "local_mtime": 1700000000.0,
                    "last_synced": "2025-01-01T00:00:00Z",
                    "conflicted": False,
                },
            },
        }
        ss.save("roundtrip", state)
        loaded = ss.load("roundtrip")

        # last_sync was updated by save
        assert loaded["last_sync"] is not None
        assert loaded["version"] == 1
        assert loaded["profile"] == "roundtrip"

        entry = loaded["entries"]["docs/README.md"]
        assert entry["local_path"] == "docs/README.md"
        assert entry["wiki_page"] == "Docs/README"
        assert entry["local_hash"] == "abc123"
        assert entry["remote_hash"] == "def456"
        assert entry["remote_version"] == 3
        assert entry["local_mtime"] == 1700000000.0
        assert entry["last_synced"] == "2025-01-01T00:00:00Z"
        assert entry["conflicted"] is False

    def test_round_trip_preserves_multiple_entries(
        self, tmp_path: Path
    ):
        """Round-trip with multiple entries preserves all of them."""
        ss = SyncState(tmp_path)
        state = ss.load("multi")
        state["entries"] = {
            "a.md": {"local_path": "a.md", "wiki_page": "A"},
            "b.md": {"local_path": "b.md", "wiki_page": "B"},
            "c.md": {"local_path": "c.md", "wiki_page": "C"},
        }
        ss.save("multi", state)
        loaded = ss.load("multi")
        assert set(loaded["entries"].keys()) == {"a.md", "b.md", "c.md"}


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


class TestContentHash:
    """Tests for SyncState.content_hash()."""

    def test_consistent_for_identical_content(self):
        """Same content always produces the same hash."""
        content = "# Hello World\n\nSome text here.\n"
        h1 = SyncState.content_hash(content)
        h2 = SyncState.content_hash(content)
        assert h1 == h2

    def test_different_for_different_content(self):
        """Different content produces different hashes."""
        h1 = SyncState.content_hash("Hello")
        h2 = SyncState.content_hash("Goodbye")
        assert h1 != h2

    def test_normalizes_bom(self):
        """BOM is stripped before hashing."""
        with_bom = "\ufeff# Title\n"
        without_bom = "# Title\n"
        assert SyncState.content_hash(
            with_bom
        ) == SyncState.content_hash(without_bom)

    def test_normalizes_crlf(self):
        """CRLF is normalised to LF before hashing."""
        crlf = "line1\r\nline2\r\n"
        lf = "line1\nline2\n"
        assert SyncState.content_hash(crlf) == SyncState.content_hash(
            lf
        )

    def test_normalizes_trailing_whitespace(self):
        """Trailing whitespace on lines is stripped before hashing."""
        with_trailing = "line1   \nline2\t\n"
        without_trailing = "line1\nline2\n"
        assert SyncState.content_hash(
            with_trailing
        ) == SyncState.content_hash(without_trailing)

    def test_normalizes_trailing_empty_lines(self):
        """Trailing empty lines are stripped before hashing."""
        with_trailing = "content\n\n\n\n"
        without_trailing = "content"
        assert SyncState.content_hash(
            with_trailing
        ) == SyncState.content_hash(without_trailing)

    def test_returns_hex_string(self):
        """content_hash returns a hexadecimal string (SHA-256 = 64 chars)."""
        h = SyncState.content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_string(self):
        """Hashing empty string does not raise."""
        h = SyncState.content_hash("")
        assert len(h) == 64

    def test_combined_normalization(self):
        """BOM + CRLF + trailing whitespace all normalised together."""
        messy = "\ufeffline1  \r\nline2\t\r\n\r\n"
        clean = "line1\nline2"
        assert SyncState.content_hash(messy) == SyncState.content_hash(
            clean
        )


# ---------------------------------------------------------------------------
# Entry CRUD
# ---------------------------------------------------------------------------


class TestEntryOperations:
    """Tests for get_entry, update_entry, remove_entry."""

    def test_get_entry_returns_none_for_missing(self, tmp_path: Path):
        """get_entry returns None when entry doesn't exist."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        assert ss.get_entry(state, "nonexistent.md") is None

    def test_update_and_get_entry(self, tmp_path: Path):
        """update_entry followed by get_entry returns the entry."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        entry = {
            "local_path": "doc.md",
            "wiki_page": "Doc",
            "conflicted": False,
        }
        ss.update_entry(state, "doc.md", entry)
        retrieved = ss.get_entry(state, "doc.md")
        assert retrieved == entry

    def test_update_entry_upserts(self, tmp_path: Path):
        """update_entry replaces an existing entry."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        ss.update_entry(state, "doc.md", {"version": 1})
        ss.update_entry(state, "doc.md", {"version": 2})
        assert ss.get_entry(state, "doc.md") == {"version": 2}

    def test_remove_entry_removes(self, tmp_path: Path):
        """remove_entry removes an existing entry."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        ss.update_entry(state, "doc.md", {"data": True})
        ss.remove_entry(state, "doc.md")
        assert ss.get_entry(state, "doc.md") is None

    def test_remove_entry_noop_if_missing(self, tmp_path: Path):
        """remove_entry is a no-op when the entry doesn't exist."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        # Should not raise
        ss.remove_entry(state, "nonexistent.md")
        assert ss.get_entry(state, "nonexistent.md") is None


# ---------------------------------------------------------------------------
# Conflict check
# ---------------------------------------------------------------------------


class TestIsConflicted:
    """Tests for SyncState.is_conflicted()."""

    def test_not_conflicted_when_entry_missing(self, tmp_path: Path):
        """is_conflicted returns False when entry doesn't exist."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        assert ss.is_conflicted(state, "missing.md") is False

    def test_not_conflicted_when_false(self, tmp_path: Path):
        """is_conflicted returns False when conflicted is False."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        ss.update_entry(state, "doc.md", {"conflicted": False})
        assert ss.is_conflicted(state, "doc.md") is False

    def test_conflicted_when_true(self, tmp_path: Path):
        """is_conflicted returns True when conflicted is True."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        ss.update_entry(state, "doc.md", {"conflicted": True})
        assert ss.is_conflicted(state, "doc.md") is True

    def test_not_conflicted_when_key_absent(self, tmp_path: Path):
        """is_conflicted returns False when entry has no 'conflicted' key."""
        ss = SyncState(tmp_path)
        state = ss.load("test")
        ss.update_entry(state, "doc.md", {"data": "hello"})
        assert ss.is_conflicted(state, "doc.md") is False
