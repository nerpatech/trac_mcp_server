"""Pydantic models for the bidirectional sync engine.

Defines the core data contracts used across all sync modules:

- ``SyncAction``: Enum of possible sync operations.
- ``SyncEntry``: State of a single file/page pair.
- ``ConflictInfo``: Details about a merge conflict.
- ``SyncResult``: Outcome of syncing one path.
- ``SyncReport``: Aggregate results for a full sync run.

All models are frozen (immutable) for safety.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class SyncAction(str, Enum):
    """Possible sync operations for a file/page pair."""

    SKIP = "skip"
    PUSH = "push"
    PULL = "pull"
    CONFLICT = "conflict"
    CREATE_REMOTE = "create_remote"
    CREATE_LOCAL = "create_local"
    DELETE_REMOTE = "delete_remote"
    DELETE_LOCAL = "delete_local"


class SyncEntry(BaseModel):
    """State of a single file/page pair in the sync manifest.

    Attributes:
        local_path: Relative path from source root.
        wiki_page: Wiki page name.
        local_hash: SHA-256 of normalized local content.
        remote_hash: SHA-256 of normalized remote TracWiki content.
        remote_version: Wiki version number at last sync.
        local_mtime: File modification time at last sync.
        last_synced: ISO 8601 timestamp of last successful sync.
        conflicted: True if unresolved conflict markers are present.
    """

    local_path: str
    wiki_page: str
    local_hash: str | None = None
    remote_hash: str | None = None
    remote_version: int | None = None
    local_mtime: float | None = None
    last_synced: str | None = None
    conflicted: bool = False

    model_config = {"frozen": True}


class ConflictInfo(BaseModel):
    """Details about a specific merge conflict.

    Attributes:
        local_path: Relative path from source root.
        wiki_page: Wiki page name.
        action: Sync action (should be CONFLICT).
        base_content: Archive base content for three-way merge.
        local_content: Current local file content.
        remote_content: Current remote wiki content.
        merged_content: Result of auto-merge attempt.
        has_markers: Whether merged content contains conflict markers.
    """

    local_path: str
    wiki_page: str
    action: SyncAction
    base_content: str | None = None
    local_content: str
    remote_content: str
    merged_content: str | None = None
    has_markers: bool

    model_config = {"frozen": True}


class SyncResult(BaseModel):
    """Result of syncing one file/page pair.

    Attributes:
        local_path: Relative path from source root.
        wiki_page: Wiki page name.
        action: Sync action that was performed.
        success: Whether the sync operation succeeded.
        error: Error message if the operation failed.
    """

    local_path: str
    wiki_page: str
    action: SyncAction
    success: bool
    error: str | None = None

    model_config = {"frozen": True}


class SyncReport(BaseModel):
    """Aggregate report for a full sync run.

    Attributes:
        profile_name: Name of the sync profile used.
        dry_run: Whether this was a dry-run (no changes applied).
        results: List of individual sync results.
        started_at: ISO 8601 timestamp when sync started.
        completed_at: ISO 8601 timestamp when sync completed.
    """

    profile_name: str
    dry_run: bool = False
    results: list[SyncResult] = []
    started_at: str
    completed_at: str | None = None

    model_config = {"frozen": True}

    @property
    def created_local(self) -> list[SyncResult]:
        """Results where action is CREATE_LOCAL."""
        return [
            r
            for r in self.results
            if r.action == SyncAction.CREATE_LOCAL
        ]

    @property
    def created_remote(self) -> list[SyncResult]:
        """Results where action is CREATE_REMOTE."""
        return [
            r
            for r in self.results
            if r.action == SyncAction.CREATE_REMOTE
        ]

    @property
    def updated_local(self) -> list[SyncResult]:
        """Results where action is PULL."""
        return [r for r in self.results if r.action == SyncAction.PULL]

    @property
    def updated_remote(self) -> list[SyncResult]:
        """Results where action is PUSH."""
        return [r for r in self.results if r.action == SyncAction.PUSH]

    @property
    def skipped(self) -> list[SyncResult]:
        """Results where action is SKIP."""
        return [r for r in self.results if r.action == SyncAction.SKIP]

    @property
    def conflicts(self) -> list[SyncResult]:
        """Results where action is CONFLICT."""
        return [
            r for r in self.results if r.action == SyncAction.CONFLICT
        ]

    @property
    def errors(self) -> list[SyncResult]:
        """Results where success is False."""
        return [r for r in self.results if not r.success]

    def summary(self) -> str:
        """Format a human-readable summary of the sync run.

        Returns:
            Multi-line summary string with counts by action.
        """
        lines = [
            f"Sync report for profile '{self.profile_name}'"
            + (" (dry run)" if self.dry_run else ""),
            f"  Created local:  {len(self.created_local)}",
            f"  Created remote: {len(self.created_remote)}",
            f"  Updated local:  {len(self.updated_local)}",
            f"  Updated remote: {len(self.updated_remote)}",
            f"  Skipped:        {len(self.skipped)}",
            f"  Conflicts:      {len(self.conflicts)}",
            f"  Errors:         {len(self.errors)}",
            f"  Total:          {len(self.results)}",
        ]
        return "\n".join(lines)
