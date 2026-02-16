"""Sync state persistence layer.

Manages the JSON state files that track per-path sync metadata in the
``.trac_mcp/`` directory.  Each sync profile gets its own state file
(``sync_{profile_name}.json``) containing version info, timestamps, and
per-path entries used for conflict detection.

Key design choices:

* **Atomic writes** -- ``save()`` writes to a temp file then calls
  ``os.replace()`` so readers never see partial data.
* **Content hashing** -- ``content_hash()`` normalises content (BOM,
  line-endings, trailing whitespace) before SHA-256 so hashes are stable
  across platforms.
* **Dict-based state** -- state is a plain ``dict`` rather than a Pydantic
  model so callers can mutate it freely during a sync run and persist once
  at the end.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class SyncState:
    """Load, save, and query sync state for a given profile.

    Args:
        state_dir: Path to the directory where state files are stored
            (typically ``.trac_mcp/``).
    """

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self, profile_name: str) -> dict:
        """Load sync state from disk.

        Args:
            profile_name: The sync profile name (used in the filename).

        Returns:
            The state dict.  If the file does not exist an empty state
            with ``version=1`` is returned.
        """
        path = self._state_path(profile_name)
        if not path.exists():
            return {
                "version": 1,
                "last_sync": None,
                "profile": profile_name,
                "entries": {},
            }
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, profile_name: str, state: dict) -> None:
        """Persist sync state to disk atomically.

        Writes to a temporary file in the same directory then atomically
        replaces the target.  Creates ``state_dir`` if it does not exist.

        The ``last_sync`` field is set to the current UTC ISO 8601 timestamp
        before writing.

        Args:
            profile_name: The sync profile name.
            state: The state dict to persist.
        """
        self._state_dir.mkdir(parents=True, exist_ok=True)
        state["last_sync"] = datetime.now(timezone.utc).isoformat()

        target = self._state_path(profile_name)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_dir), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
            os.replace(tmp_path, target)
        except BaseException:
            # Clean up temp file on any failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Entry helpers
    # ------------------------------------------------------------------

    def get_entry(self, state: dict, local_path: str) -> dict | None:
        """Return the entry for *local_path*, or ``None`` if absent."""
        return state.get("entries", {}).get(local_path)

    def update_entry(
        self, state: dict, local_path: str, entry: dict
    ) -> None:
        """Upsert *entry* into ``state["entries"]`` under *local_path*.

        Mutates *state* in place.
        """
        state.setdefault("entries", {})[local_path] = entry

    def remove_entry(self, state: dict, local_path: str) -> None:
        """Remove *local_path* from ``state["entries"]``.

        No-op if not present.
        """
        state.get("entries", {}).pop(local_path, None)

    # ------------------------------------------------------------------
    # Content hashing
    # ------------------------------------------------------------------

    @staticmethod
    def content_hash(content: str) -> str:
        """Compute a normalised SHA-256 hex digest of *content*.

        Normalisation steps (applied in order):

        1. Strip BOM (``\\ufeff``).
        2. Replace ``\\r\\n`` with ``\\n``.
        3. Right-strip each line.
        4. Strip trailing empty lines.

        The result is encoded as UTF-8 before hashing.
        """
        # 1. Strip BOM
        text = content.lstrip("\ufeff")
        # 2. Normalise line endings
        text = text.replace("\r\n", "\n")
        # 3. rstrip each line
        lines = [line.rstrip() for line in text.split("\n")]
        # 4. Strip trailing empty lines
        while lines and lines[-1] == "":
            lines.pop()
        normalised = "\n".join(lines)
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Conflict query
    # ------------------------------------------------------------------

    def is_conflicted(self, state: dict, local_path: str) -> bool:
        """Return ``True`` if the entry for *local_path* is marked conflicted."""
        entry = self.get_entry(state, local_path)
        if entry is None:
            return False
        return bool(entry.get("conflicted", False))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _state_path(self, profile_name: str) -> Path:
        """Return the path to the state file for *profile_name*."""
        return self._state_dir / f"sync_{profile_name}.json"
