"""Integration tests for the bidirectional sync engine.

Unit-level integration tests (always run) exercise a full sync cycle
with a mocked TracClient, verifying the interaction of all sync
sub-systems: state persistence, path mapping, reconciliation, conflict
resolution, direction filtering, and dry-run mode.

Live Trac integration tests (gated by ``--run-live``) validate
end-to-end round-trip against a real Trac instance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from trac_mcp_server.config_schema import (
    SyncMappingRule,
    SyncProfileConfig,
)
from trac_mcp_server.sync.engine import SyncEngine
from trac_mcp_server.sync.models import SyncAction
from trac_mcp_server.sync.state import SyncState

# ---------------------------------------------------------------------------
# In-memory fake TracClient
# ---------------------------------------------------------------------------


class FakeTracClient:
    """In-memory wiki storage for integration tests.

    Tracks all ``put_wiki_page`` calls and simulates version increments.
    """

    def __init__(
        self,
        pages: Optional[Dict[str, str]] = None,
        versions: Optional[Dict[str, int]] = None,
    ) -> None:
        self.pages: Dict[str, str] = dict(pages) if pages else {}
        self.versions: Dict[str, int] = (
            dict(versions) if versions else {}
        )
        self.put_calls: list[tuple[str, str, str, Optional[int]]] = []

    def list_wiki_pages(self) -> List[str]:
        return list(self.pages.keys())

    def get_wiki_page(
        self, page_name: str, version: Optional[int] = None
    ) -> str:
        if page_name not in self.pages:
            from xmlrpc.client import Fault

            raise Fault(1, f"Page '{page_name}' not found")
        return self.pages[page_name]

    def get_wiki_page_info(
        self, page_name: str, version: Optional[int] = None
    ) -> Dict[str, Any]:
        if page_name not in self.pages:
            from xmlrpc.client import Fault

            raise Fault(1, f"Page '{page_name}' not found")
        return {
            "name": page_name,
            "version": self.versions.get(page_name, 1),
            "author": "test",
            "lastModified": "2026-01-01T00:00:00Z",
        }

    def put_wiki_page(
        self,
        page_name: str,
        content: str,
        comment: str,
        version: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.put_calls.append((page_name, content, comment, version))
        self.pages[page_name] = content
        old_ver = self.versions.get(page_name, 0)
        self.versions[page_name] = old_ver + 1
        return {
            "name": page_name,
            "version": old_ver + 1,
            "author": "test",
            "lastModified": "2026-01-01T00:00:00Z",
            "url": f"http://test/wiki/{page_name}",
        }

    def delete_wiki_page(self, page_name: str) -> bool:
        self.pages.pop(page_name, None)
        self.versions.pop(page_name, None)
        return True


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _make_profile(**overrides: Any) -> SyncProfileConfig:
    """Build a SyncProfileConfig with sensible test defaults."""
    defaults: dict[str, Any] = {
        "source": "docs/",
        "destination": "Docs",
        "format": "auto",
        "direction": "bidirectional",
        "conflict_strategy": "local-wins",
        "git_safety": "none",
        "mappings": [],
        "exclude": [],
    }
    defaults.update(overrides)
    return SyncProfileConfig(**defaults)


def _setup_engine(
    tmp_path: Path,
    profile_overrides: Optional[Dict[str, Any]] = None,
    client: Optional[FakeTracClient] = None,
    local_files: Optional[Dict[str, str]] = None,
    state_entries: Optional[Dict[str, dict]] = None,
) -> tuple[SyncEngine, FakeTracClient, Path]:
    """Create a SyncEngine wired to a temp directory and fake client.

    Returns ``(engine, fake_client, source_dir)`` so callers can
    inspect the filesystem after sync.
    """
    source_dir = tmp_path / "docs"
    source_dir.mkdir(parents=True, exist_ok=True)

    state_dir = tmp_path / ".trac_mcp"
    state_dir.mkdir(parents=True, exist_ok=True)

    overrides = profile_overrides or {}
    overrides.setdefault("state_dir", str(state_dir))

    profile = _make_profile(**overrides)
    fake_client = client or FakeTracClient()

    # Write local files
    if local_files:
        for rel_path, content in local_files.items():
            fp = source_dir / rel_path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")

    # Write initial state
    if state_entries:
        state_file = state_dir / "sync_test-profile.json"
        state_data = {
            "version": 1,
            "last_sync": None,
            "profile": "test-profile",
            "entries": state_entries,
        }
        state_file.write_text(
            json.dumps(state_data, indent=2), encoding="utf-8"
        )

    engine = SyncEngine(
        client=fake_client,  # type: ignore[arg-type]
        profile=profile,
        profile_name="test-profile",
        source_root=source_dir,
    )

    return engine, fake_client, source_dir


# ===================================================================
# 1. Full cycle test with mocked TracClient
# ===================================================================


class TestFullSyncCycle:
    """Validate the full CREATE -> PUSH -> PULL -> CONFLICT cycle."""

    def test_new_local_file_creates_remote(
        self, tmp_path: Path
    ) -> None:
        """A new local file with no archive is pushed to remote.

        Note: The engine maps CREATE_REMOTE to ``_do_push`` which returns
        ``SyncAction.PUSH`` in the result.  Dry-run preserves the original
        reconciled action (CREATE_REMOTE); execution returns PUSH.
        """
        engine, client, source_dir = _setup_engine(
            tmp_path,
            local_files={"readme.md": "# Hello World\n"},
        )

        report = engine.run(dry_run=False)

        # Engine maps CREATE_REMOTE -> _do_push which returns PUSH
        pushes = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(pushes) == 1
        assert pushes[0].success is True
        # Client should have received a put_wiki_page call
        assert len(client.put_calls) == 1
        page_name = client.put_calls[0][0]
        assert "readme" in page_name.lower()

    def test_state_file_created_after_create(
        self, tmp_path: Path
    ) -> None:
        """After CREATE_REMOTE the state file records the entry."""
        state_dir = tmp_path / ".trac_mcp"
        engine, client, _ = _setup_engine(
            tmp_path,
            profile_overrides={"state_dir": str(state_dir)},
            local_files={"readme.md": "# Hello\n"},
        )

        engine.run(dry_run=False)

        state_file = state_dir / "sync_test-profile.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        entries = state.get("entries", {})
        assert len(entries) >= 1
        # Find the entry (the key is the local relative path)
        entry = next(iter(entries.values()))
        assert entry["local_hash"] is not None
        assert entry["remote_hash"] is not None
        assert entry["conflicted"] is False

    def test_modified_local_triggers_push(self, tmp_path: Path) -> None:
        """After initial sync, modifying local file triggers PUSH."""
        old_local = "# Original\n"
        new_local = "# Modified locally\n"
        remote_tw = "= Original =\n"
        old_hash = SyncState.content_hash(old_local)
        remote_hash = SyncState.content_hash(remote_tw)

        engine, client, source_dir = _setup_engine(
            tmp_path,
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": remote_tw},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        pushes = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(pushes) == 1
        assert pushes[0].success is True
        assert len(client.put_calls) == 1

    def test_modified_remote_triggers_pull(
        self, tmp_path: Path
    ) -> None:
        """Remote change with unchanged local triggers PULL."""
        local_content = "# Hello\n"
        old_remote = "= Hello =\n"
        new_remote = "= Updated remotely =\n"
        local_hash = SyncState.content_hash(local_content)
        old_remote_hash = SyncState.content_hash(old_remote)

        engine, client, source_dir = _setup_engine(
            tmp_path,
            local_files={"readme.md": local_content},
            client=FakeTracClient(
                pages={"Docs/readme": new_remote},
                versions={"Docs/readme": 2},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": local_hash,
                    "remote_hash": old_remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        pulls = [
            r for r in report.results if r.action == SyncAction.PULL
        ]
        assert len(pulls) == 1
        assert pulls[0].success is True
        # Local file should have been updated
        local_file = source_dir / "readme.md"
        assert local_file.exists()
        updated = local_file.read_text(encoding="utf-8")
        # Content was pulled and converted (TracWiki -> Markdown)
        assert len(updated) > 0

    def test_both_changed_triggers_conflict(
        self, tmp_path: Path
    ) -> None:
        """Both sides changed since archive produces CONFLICT."""
        old_content = "# Original\n"
        new_local = "# Changed locally\n"
        new_remote = "= Changed remotely =\n"
        old_hash = SyncState.content_hash(old_content)

        engine, client, source_dir = _setup_engine(
            tmp_path,
            profile_overrides={"conflict_strategy": "local-wins"},
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": new_remote},
                versions={"Docs/readme": 2},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_hash,
                    "remote_hash": old_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        conflicts = [
            r for r in report.results if r.action == SyncAction.CONFLICT
        ]
        assert len(conflicts) == 1
        assert conflicts[0].success is True

    def test_state_updated_after_push(self, tmp_path: Path) -> None:
        """State entry is updated after a successful PUSH."""
        old_local = "# Old\n"
        new_local = "# New\n"
        remote_tw = "= Old =\n"
        old_hash = SyncState.content_hash(old_local)
        remote_hash = SyncState.content_hash(remote_tw)

        state_dir = tmp_path / ".trac_mcp"
        engine, client, _ = _setup_engine(
            tmp_path,
            profile_overrides={"state_dir": str(state_dir)},
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": remote_tw},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        engine.run(dry_run=False)

        state_file = state_dir / "sync_test-profile.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        entry = state["entries"]["readme.md"]
        # Hash should have changed from the push
        assert entry["local_hash"] != old_hash
        assert entry["conflicted"] is False


# ===================================================================
# 2. Dry-run test
# ===================================================================


class TestDryRunIntegration:
    """Dry-run computes actions without executing writes."""

    def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        """Dry run does not call put_wiki_page or update local files."""
        old_local = "# Old\n"
        new_local = "# New\n"
        remote_tw = "= Old =\n"
        old_hash = SyncState.content_hash(old_local)
        remote_hash = SyncState.content_hash(remote_tw)

        engine, client, source_dir = _setup_engine(
            tmp_path,
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": remote_tw},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=True)

        assert report.dry_run is True
        # Should report PUSH action
        push_results = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(push_results) == 1
        # No actual writes
        assert len(client.put_calls) == 0
        # Local file content unchanged
        local_content = (source_dir / "readme.md").read_text(
            encoding="utf-8"
        )
        assert local_content == new_local

    def test_dry_run_report_accurate(self, tmp_path: Path) -> None:
        """Dry-run report accurately reflects what *would* happen."""
        engine, client, _ = _setup_engine(
            tmp_path,
            local_files={
                "a.md": "# File A\n",
                "b.md": "# File B\n",
            },
        )

        report = engine.run(dry_run=True)

        # Both new files should show as CREATE_REMOTE
        creates = [
            r
            for r in report.results
            if r.action == SyncAction.CREATE_REMOTE
        ]
        assert len(creates) == 2
        # No actual wiki writes
        assert len(client.put_calls) == 0


# ===================================================================
# 3. Direction filter test
# ===================================================================


class TestDirectionFilterIntegration:
    """Direction settings restrict which actions execute."""

    def test_push_only_skips_pull_actions(self, tmp_path: Path) -> None:
        """In push-only mode, PULL actions become SKIP."""
        local_content = "# Hello\n"
        old_remote = "= Hello =\n"
        new_remote = "= Updated =\n"
        local_hash = SyncState.content_hash(local_content)
        old_remote_hash = SyncState.content_hash(old_remote)

        engine, client, source_dir = _setup_engine(
            tmp_path,
            profile_overrides={"direction": "push"},
            local_files={"readme.md": local_content},
            client=FakeTracClient(
                pages={"Docs/readme": new_remote},
                versions={"Docs/readme": 2},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": local_hash,
                    "remote_hash": old_remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        pulls = [
            r for r in report.results if r.action == SyncAction.PULL
        ]
        assert len(pulls) == 0
        skips = [
            r for r in report.results if r.action == SyncAction.SKIP
        ]
        assert len(skips) >= 1
        # Local file should NOT have been updated
        local_file = source_dir / "readme.md"
        assert local_file.read_text(encoding="utf-8") == local_content

    def test_pull_only_skips_push_actions(self, tmp_path: Path) -> None:
        """In pull-only mode, PUSH actions become SKIP."""
        old_local = "# Old\n"
        new_local = "# New\n"
        remote_tw = "= Old =\n"
        old_hash = SyncState.content_hash(old_local)
        remote_hash = SyncState.content_hash(remote_tw)

        engine, client, _ = _setup_engine(
            tmp_path,
            profile_overrides={"direction": "pull"},
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": remote_tw},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        pushes = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(pushes) == 0
        skips = [
            r for r in report.results if r.action == SyncAction.SKIP
        ]
        assert len(skips) >= 1
        # No wiki writes
        assert len(client.put_calls) == 0

    def test_push_only_allows_create_remote(
        self, tmp_path: Path
    ) -> None:
        """Push-only still allows new-file push (CREATE_REMOTE -> PUSH)."""
        engine, client, _ = _setup_engine(
            tmp_path,
            profile_overrides={"direction": "push"},
            local_files={"readme.md": "# Hello\n"},
        )

        report = engine.run(dry_run=False)

        # Engine executes CREATE_REMOTE via _do_push which returns PUSH
        pushes = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(pushes) == 1
        assert pushes[0].success is True


# ===================================================================
# 4. State persistence test
# ===================================================================


class TestStatePersistence:
    """Verify state continuity across sync runs (no re-sync of unchanged)."""

    def test_second_run_skips_unchanged(self, tmp_path: Path) -> None:
        """Run sync twice with no changes -- second run produces only SKIPs."""
        state_dir = tmp_path / ".trac_mcp"
        engine, client, source_dir = _setup_engine(
            tmp_path,
            profile_overrides={"state_dir": str(state_dir)},
            local_files={"readme.md": "# Hello\n"},
        )

        # First run: pushes new file to remote (CREATE_REMOTE -> PUSH)
        report1 = engine.run(dry_run=False)
        pushes1 = [
            r for r in report1.results if r.action == SyncAction.PUSH
        ]
        assert len(pushes1) == 1

        # Second run with same engine (state persisted):
        # Re-create engine to simulate fresh start with same state
        profile = _make_profile(state_dir=str(state_dir))
        engine2 = SyncEngine(
            client=client,  # type: ignore[arg-type]
            profile=profile,
            profile_name="test-profile",
            source_root=source_dir,
        )

        report2 = engine2.run(dry_run=False)

        # All results should be SKIP (nothing changed)
        non_skips = [
            r for r in report2.results if r.action != SyncAction.SKIP
        ]
        assert len(non_skips) == 0, (
            f"Expected only SKIPs on second run, got: {[(r.action, r.local_path) for r in non_skips]}"
        )
        # No new put calls beyond the first run
        assert len(client.put_calls) == 1

    def test_state_survives_engine_recreation(
        self, tmp_path: Path
    ) -> None:
        """State written by one engine instance is read by another."""
        state_dir = tmp_path / ".trac_mcp"
        local_content = "# Persistent\n"

        # Run 1: create
        engine1, client, source_dir = _setup_engine(
            tmp_path,
            profile_overrides={"state_dir": str(state_dir)},
            local_files={"readme.md": local_content},
        )
        engine1.run(dry_run=False)

        # Verify state file exists
        state_file = state_dir / "sync_test-profile.json"
        assert state_file.exists()

        # Run 2: new engine, same state dir, same client
        profile = _make_profile(state_dir=str(state_dir))
        engine2 = SyncEngine(
            client=client,  # type: ignore[arg-type]
            profile=profile,
            profile_name="test-profile",
            source_root=source_dir,
        )
        report2 = engine2.run(dry_run=False)

        # Nothing should have changed
        skips = [
            r for r in report2.results if r.action == SyncAction.SKIP
        ]
        assert len(skips) >= 1


# ===================================================================
# 5. Config mapping test
# ===================================================================


class TestConfigMappingIntegration:
    """Complex mapping with namespaces, name_rules, and excludes."""

    def test_mapping_with_namespace_templates(
        self, tmp_path: Path
    ) -> None:
        """Namespace template {parent} resolves to parent directory name."""
        mappings = [
            SyncMappingRule(
                pattern="phases/*/*.md",
                namespace="Phases/{parent}",
            ),
        ]

        engine, client, _ = _setup_engine(
            tmp_path,
            profile_overrides={
                "mappings": [m.model_dump() for m in mappings],
            },
            local_files={
                "phases/41-sync/41-01-PLAN.md": "# Plan 01\n",
                "phases/41-sync/41-CONTEXT.md": "# Context\n",
            },
        )

        report = engine.run(dry_run=True)

        # Both files should map to wiki pages
        assert len(report.results) >= 2
        creates = [
            r
            for r in report.results
            if r.action == SyncAction.CREATE_REMOTE
        ]
        assert len(creates) == 2
        # Wiki page names should contain the parent directory
        wiki_pages = [r.wiki_page for r in creates]
        assert any("41-sync" in wp for wp in wiki_pages)

    def test_name_rules_override(self, tmp_path: Path) -> None:
        """Name rules override default stem-based naming."""
        mappings = [
            SyncMappingRule(
                pattern="phases/*/*.md",
                namespace="Phases/{parent}",
                name_rules={
                    "*-CONTEXT.md": "Context",
                    "*-RESEARCH.md": "Research",
                },
            ),
        ]

        engine, client, _ = _setup_engine(
            tmp_path,
            profile_overrides={
                "mappings": [m.model_dump() for m in mappings],
            },
            local_files={
                "phases/41-sync/41-CONTEXT.md": "# Context\n",
                "phases/41-sync/41-RESEARCH.md": "# Research\n",
            },
        )

        report = engine.run(dry_run=True)

        creates = [
            r
            for r in report.results
            if r.action == SyncAction.CREATE_REMOTE
        ]
        wiki_pages = [r.wiki_page for r in creates]
        assert any("Context" in wp for wp in wiki_pages)
        assert any("Research" in wp for wp in wiki_pages)

    def test_exclude_patterns_filter_files(
        self, tmp_path: Path
    ) -> None:
        """Excluded patterns are not synced."""
        engine, client, _ = _setup_engine(
            tmp_path,
            profile_overrides={
                "exclude": ["debug/*"],
                "mappings": [
                    {"pattern": "*.md", "namespace": ""},
                    {"pattern": "debug/*.md", "namespace": "Debug"},
                ],
            },
            local_files={
                "readme.md": "# Included\n",
                "debug/log.md": "# Excluded debug\n",
            },
        )

        report = engine.run(dry_run=True)

        # Only readme.md should be in results (debug excluded)
        creates = [
            r
            for r in report.results
            if r.action == SyncAction.CREATE_REMOTE
        ]
        local_paths = [r.local_path for r in creates]
        assert any("readme" in lp for lp in local_paths)
        assert not any("debug" in lp for lp in local_paths)


# ===================================================================
# 6. Live Trac end-to-end (gated by --run-live)
# ===================================================================


@pytest.mark.live
class TestLiveEndToEnd:
    """End-to-end sync with a real Trac instance.

    These tests require ``--run-live`` and a configured Trac connection.
    They create, modify, verify, and clean up test wiki pages.
    """

    @pytest.fixture
    def live_client(self):
        """Create a real TracClient from environment config."""
        import os

        from trac_mcp_server.config import Config
        from trac_mcp_server.core.client import TracClient

        url = os.environ.get("TRAC_URL", "")
        username = os.environ.get("TRAC_USERNAME", "")
        password = os.environ.get("TRAC_PASSWORD", "")

        if not url:
            pytest.skip("TRAC_URL not set")

        config = Config(
            trac_url=url,
            username=username,
            password=password,
            insecure=True,
        )
        return TracClient(config)

    @pytest.fixture
    def test_namespace(self):
        """Unique namespace to avoid collisions."""
        import time

        return f"SyncTest_{int(time.time())}"

    def test_full_live_cycle(
        self, tmp_path: Path, live_client: Any, test_namespace: str
    ) -> None:
        """Full create -> push -> pull cycle against real Trac."""
        source_dir = tmp_path / "docs"
        source_dir.mkdir()
        state_dir = tmp_path / ".trac_mcp"
        state_dir.mkdir()

        profile = SyncProfileConfig(
            source="docs/",
            destination=test_namespace,
            format="auto",
            direction="bidirectional",
            conflict_strategy="local-wins",
            git_safety="none",
            mappings=[],
            exclude=[],
            state_dir=str(state_dir),
        )

        engine = SyncEngine(
            client=live_client,
            profile=profile,
            profile_name="live-test",
            source_root=source_dir,
        )

        created_pages: list[str] = []

        try:
            # Step 1: Create a local file and sync
            test_file = source_dir / "test_page.md"
            test_file.write_text(
                "# Test Page\n\nCreated by integration test.\n",
                encoding="utf-8",
            )

            report1 = engine.run(dry_run=False)
            # CREATE_REMOTE executed via _do_push returns PUSH
            pushes1 = [
                r
                for r in report1.results
                if r.action == SyncAction.PUSH
            ]
            assert len(pushes1) == 1
            assert pushes1[0].success is True
            created_pages.append(pushes1[0].wiki_page)

            # Step 2: Modify local file and sync again
            test_file.write_text(
                "# Test Page\n\nUpdated by integration test.\n",
                encoding="utf-8",
            )

            report2 = engine.run(dry_run=False)
            pushes = [
                r
                for r in report2.results
                if r.action == SyncAction.PUSH
            ]
            assert len(pushes) == 1
            assert pushes[0].success is True

            # Step 3: Modify wiki page directly, then sync to pull
            wiki_page = pushes1[0].wiki_page
            from trac_mcp_server.converters.markdown_to_tracwiki import (
                markdown_to_tracwiki,
            )

            new_wiki_content = markdown_to_tracwiki(
                "# Test Page\n\nModified on wiki directly.\n"
            )
            live_client.put_wiki_page(
                wiki_page, new_wiki_content, comment="Direct wiki edit"
            )

            report3 = engine.run(dry_run=False)
            pulls = [
                r
                for r in report3.results
                if r.action == SyncAction.PULL
            ]
            assert len(pulls) == 1
            assert pulls[0].success is True

            # Verify local file was updated
            local_content = test_file.read_text(encoding="utf-8")
            assert len(local_content) > 0

            # Verify state has correct entries
            state = engine.state_store.load("live-test")
            entry = state["entries"].get("test_page.md")
            assert entry is not None
            assert entry["local_hash"] is not None
            assert entry["remote_hash"] is not None

        finally:
            # Clean up test wiki pages
            for page in created_pages:
                try:
                    live_client.delete_wiki_page(page)
                except Exception:
                    pass

    def test_format_conversion_round_trip(
        self, tmp_path: Path, live_client: Any, test_namespace: str
    ) -> None:
        """Push Markdown, pull back, verify semantic equivalence."""
        source_dir = tmp_path / "docs"
        source_dir.mkdir()
        state_dir = tmp_path / ".trac_mcp"
        state_dir.mkdir()

        profile = SyncProfileConfig(
            source="docs/",
            destination=test_namespace,
            format="auto",
            direction="bidirectional",
            conflict_strategy="local-wins",
            git_safety="none",
            mappings=[],
            exclude=[],
            state_dir=str(state_dir),
        )

        engine = SyncEngine(
            client=live_client,
            profile=profile,
            profile_name="live-roundtrip",
            source_root=source_dir,
        )

        created_pages: list[str] = []

        try:
            # Create a rich Markdown file
            rich_md = (
                "# Main Title\n\n"
                "## Section One\n\n"
                "A paragraph with **bold** and *italic* text.\n\n"
                "- Item one\n"
                "- Item two\n"
                "- Item three\n\n"
                "## Section Two\n\n"
                "```python\n"
                "def hello():\n"
                '    print("world")\n'
                "```\n\n"
                "A [link](http://example.com) in text.\n"
            )
            test_file = source_dir / "rich.md"
            test_file.write_text(rich_md, encoding="utf-8")

            # Push
            report1 = engine.run(dry_run=False)
            # CREATE_REMOTE executed via _do_push returns PUSH
            pushes1 = [
                r
                for r in report1.results
                if r.action == SyncAction.PUSH
            ]
            assert len(pushes1) == 1
            created_pages.append(pushes1[0].wiki_page)

            # Modify remote slightly to trigger a PULL
            wiki_page = pushes1[0].wiki_page
            current_tw = live_client.get_wiki_page(wiki_page)
            # Add a small change to the TracWiki content
            modified_tw = current_tw + "\nAdditional wiki line.\n"
            live_client.put_wiki_page(
                wiki_page,
                modified_tw,
                comment="Add line for round-trip test",
            )

            # Re-create the local file (restore it so it matches archive)
            test_file.write_text(rich_md, encoding="utf-8")

            # Sync again - should PULL the remote change
            report2 = engine.run(dry_run=False)
            pulls = [
                r
                for r in report2.results
                if r.action == SyncAction.PULL
            ]
            assert len(pulls) == 1

            # Read pulled content
            pulled_content = test_file.read_text(encoding="utf-8")
            # Should contain the core structural elements
            assert (
                "Main Title" in pulled_content
                or "main title" in pulled_content.lower()
            )

            # Push again -- verify no false conflict
            report3 = engine.run(dry_run=True)
            conflicts = [
                r
                for r in report3.results
                if r.action == SyncAction.CONFLICT
            ]
            # After pull, both sides should be in sync, so no conflicts
            assert len(conflicts) == 0

        finally:
            for page in created_pages:
                try:
                    live_client.delete_wiki_page(page)
                except Exception:
                    pass


# ===================================================================
# Additional edge case tests
# ===================================================================


class TestMultipleFilesSync:
    """Test syncing multiple files in a single run."""

    def test_multiple_files_independent(self, tmp_path: Path) -> None:
        """Multiple new files each get pushed to remote."""
        engine, client, _ = _setup_engine(
            tmp_path,
            local_files={
                "alpha.md": "# Alpha\n",
                "beta.md": "# Beta\n",
                "gamma.md": "# Gamma\n",
            },
        )

        report = engine.run(dry_run=False)

        # CREATE_REMOTE is executed via _do_push -> returns PUSH
        pushes = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(pushes) == 3
        assert all(r.success for r in pushes)
        assert len(client.put_calls) == 3

    def test_mixed_actions_single_run(self, tmp_path: Path) -> None:
        """A single run can produce different actions for different files."""
        old_local_a = "# A old\n"
        new_local_a = "# A new\n"
        local_b = "# B unchanged\n"
        remote_a = "= A old =\n"
        remote_b = "= B unchanged =\n"

        engine, client, _ = _setup_engine(
            tmp_path,
            local_files={
                "a.md": new_local_a,
                "b.md": local_b,
                "c.md": "# C new file\n",
            },
            client=FakeTracClient(
                pages={
                    "Docs/a": remote_a,
                    "Docs/b": remote_b,
                },
                versions={"Docs/a": 1, "Docs/b": 1},
            ),
            state_entries={
                "a.md": {
                    "wiki_page": "Docs/a",
                    "local_hash": SyncState.content_hash(old_local_a),
                    "remote_hash": SyncState.content_hash(remote_a),
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                },
                "b.md": {
                    "wiki_page": "Docs/b",
                    "local_hash": SyncState.content_hash(local_b),
                    "remote_hash": SyncState.content_hash(remote_b),
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                },
            },
        )

        report = engine.run(dry_run=False)

        actions = {r.local_path: r.action for r in report.results}
        # a.md: local changed -> PUSH
        assert actions.get("a.md") == SyncAction.PUSH
        # b.md: unchanged -> SKIP
        assert actions.get("b.md") == SyncAction.SKIP
        # c.md: new file -> CREATE_REMOTE executed via _do_push -> PUSH
        assert actions.get("c.md") == SyncAction.PUSH


class TestReportFormatting:
    """Verify the report object has correct summary properties."""

    def test_report_summary_string(self, tmp_path: Path) -> None:
        """SyncReport.summary() produces readable output."""
        engine, client, _ = _setup_engine(
            tmp_path,
            local_files={"readme.md": "# Hello\n"},
        )

        report = engine.run(dry_run=False)

        summary = report.summary()
        assert "test-profile" in summary
        assert "Created remote:" in summary or "1" in summary

    def test_report_property_counts(self, tmp_path: Path) -> None:
        """Report property accessors return correct counts."""
        engine, client, _ = _setup_engine(
            tmp_path,
            local_files={
                "a.md": "# A\n",
                "b.md": "# B\n",
            },
        )

        report = engine.run(dry_run=False)

        # New files are executed via _do_push -> PUSH (not CREATE_REMOTE)
        assert len(report.updated_remote) == 2
        assert len(report.skipped) == 0
        assert len(report.errors) == 0
        assert len(report.conflicts) == 0
