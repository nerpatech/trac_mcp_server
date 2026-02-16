"""Bidirectional document sync engine.

Public API for synchronising local project files (Markdown) with Trac
wiki pages (TracWiki format).

Architecture
------------
The sync engine uses **Unison-style archive-based reconciliation** to
detect changes on both sides since the last sync.  Each side is compared
against its own archived content hash -- local Markdown hashes are never
compared directly to remote TracWiki hashes.

Modules:

- ``engine``    -- ``SyncEngine``: orchestrates a full sync cycle.
- ``state``     -- ``SyncState``: load/save/query JSON state files.
- ``mapper``    -- ``PathMapper``: config-driven local-path-to-wiki mapping.
- ``models``    -- ``SyncAction``, ``SyncEntry``, ``ConflictInfo``,
  ``SyncResult``, ``SyncReport``: core data contracts.
- ``merger``    -- Three-way merge via ``merge3`` library.
- ``resolver``  -- Conflict resolution strategies (interactive, markers,
  local-wins, remote-wins).
- ``reporter``  -- Human-readable and JSON report formatting.

Public exports
--------------
``SyncEngine``, ``PathMapper``, ``SyncState``, ``SyncAction``,
``SyncEntry``, ``ConflictInfo``, ``SyncResult``, ``SyncReport``,
``format_sync_report``, ``format_dry_run_preview``, ``report_to_json``.

Usage example
-------------
::

    from pathlib import Path
    from trac_mcp_server.config_schema import SyncProfileConfig
    from trac_mcp_server.core.client import TracClient
    from trac_mcp_server.sync import SyncEngine, format_sync_report

    profile = SyncProfileConfig(
        source=".planning/",
        destination="Planning",
        direction="bidirectional",
        conflict_strategy="local-wins",
        git_safety="none",
    )

    engine = SyncEngine(
        client=trac_client,          # TracClient instance
        profile=profile,
        profile_name="planning",
        source_root=Path(".planning"),
    )

    # Dry-run first to preview changes
    preview = engine.run(dry_run=True)
    print(format_sync_report(preview))

    # Execute the sync
    report = engine.run(dry_run=False)
    print(format_sync_report(report))
"""

from .engine import SyncEngine
from .mapper import PathMapper
from .models import (
    ConflictInfo,
    SyncAction,
    SyncEntry,
    SyncReport,
    SyncResult,
)
from .reporter import (
    format_dry_run_preview,
    format_sync_report,
    report_to_json,
)
from .state import SyncState

__all__ = [
    "ConflictInfo",
    "PathMapper",
    "SyncAction",
    "SyncEngine",
    "SyncEntry",
    "SyncReport",
    "SyncResult",
    "SyncState",
    "format_dry_run_preview",
    "format_sync_report",
    "report_to_json",
]
