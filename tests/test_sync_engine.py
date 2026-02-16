"""Tests for the core sync engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from trac_mcp_server.config_schema import SyncProfileConfig
from trac_mcp_server.sync.engine import SyncEngine
from trac_mcp_server.sync.models import SyncAction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(**overrides: Any) -> SyncProfileConfig:
    """Build a minimal SyncProfileConfig for testing."""
    defaults = {
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


class FakeTracClient:
    """Minimal TracClient replacement for testing.

    Simulates wiki page storage with an in-memory dict.
    """

    def __init__(
        self,
        pages: Optional[Dict[str, str]] = None,
        versions: Optional[Dict[str, int]] = None,
    ) -> None:
        self.pages: Dict[str, str] = pages or {}
        self.versions: Dict[str, int] = versions or {}
        self.put_calls: list[tuple] = []

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


def _setup_engine(
    tmp_path: Path,
    profile_overrides: Optional[Dict[str, Any]] = None,
    client: Optional[FakeTracClient] = None,
    local_files: Optional[Dict[str, str]] = None,
    state_entries: Optional[Dict[str, dict]] = None,
) -> tuple[SyncEngine, FakeTracClient]:
    """Create a SyncEngine with a temp directory and mock client."""
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

    # Write initial state if needed
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

    return engine, fake_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDryRun:
    """Dry-run should produce a report without executing changes."""

    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        """Dry run with local file but no remote produces CREATE_REMOTE."""
        engine, client = _setup_engine(
            tmp_path,
            local_files={"readme.md": "# Hello\n"},
        )

        report = engine.run(dry_run=True)

        assert report.dry_run is True
        assert len(report.results) == 1
        result = report.results[0]
        assert result.action == SyncAction.CREATE_REMOTE
        # No put calls on client
        assert len(client.put_calls) == 0

    def test_dry_run_with_existing_state(self, tmp_path: Path) -> None:
        """Dry run with unchanged content shows SKIP."""
        from trac_mcp_server.sync.state import SyncState

        local_content = "# Hello\n"
        remote_content = "= Hello =\n"
        local_hash = SyncState.content_hash(local_content)
        remote_hash = SyncState.content_hash(remote_content)

        engine, client = _setup_engine(
            tmp_path,
            local_files={"readme.md": local_content},
            client=FakeTracClient(
                pages={"Docs/readme": remote_content},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": local_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=True)
        assert report.dry_run is True
        # Should be SKIP since nothing changed
        skip_results = [
            r for r in report.results if r.action == SyncAction.SKIP
        ]
        assert len(skip_results) >= 1


class TestPushFlow:
    """Test pushing local changes to remote."""

    def test_push_changed_local(self, tmp_path: Path) -> None:
        """Local changed, remote unchanged -> PUSH."""
        from trac_mcp_server.sync.state import SyncState

        old_local = "# Old\n"
        new_local = "# New content\n"
        remote_content = "= Old =\n"
        old_local_hash = SyncState.content_hash(old_local)
        remote_hash = SyncState.content_hash(remote_content)

        engine, client = _setup_engine(
            tmp_path,
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": remote_content},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_local_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        push_results = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(push_results) == 1
        assert push_results[0].success is True
        assert len(client.put_calls) == 1


class TestPullFlow:
    """Test pulling remote changes to local."""

    def test_pull_changed_remote(self, tmp_path: Path) -> None:
        """Remote changed, local unchanged -> PULL."""
        from trac_mcp_server.sync.state import SyncState

        local_content = "# Hello\n"
        old_remote = "= Hello =\n"
        new_remote = "= Updated =\n"
        local_hash = SyncState.content_hash(local_content)
        old_remote_hash = SyncState.content_hash(old_remote)

        engine, client = _setup_engine(
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

        pull_results = [
            r for r in report.results if r.action == SyncAction.PULL
        ]
        assert len(pull_results) == 1
        assert pull_results[0].success is True

        # Local file should have been updated
        abs_path = engine.source_root / "readme.md"
        assert abs_path.exists()
        updated = abs_path.read_text(encoding="utf-8")
        # Content was converted from TracWiki -> Markdown
        assert len(updated) > 0


class TestSkipFlow:
    """Test that unchanged content produces SKIP."""

    def test_no_changes_skip(self, tmp_path: Path) -> None:
        """Both sides unchanged -> SKIP."""
        from trac_mcp_server.sync.state import SyncState

        local_content = "# Hello\n"
        remote_content = "= Hello =\n"
        local_hash = SyncState.content_hash(local_content)
        remote_hash = SyncState.content_hash(remote_content)

        engine, client = _setup_engine(
            tmp_path,
            local_files={"readme.md": local_content},
            client=FakeTracClient(
                pages={"Docs/readme": remote_content},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": local_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        skip_results = [
            r for r in report.results if r.action == SyncAction.SKIP
        ]
        assert len(skip_results) >= 1
        assert len(client.put_calls) == 0


class TestConflictDelegation:
    """Test that conflicts are delegated to the resolver."""

    def test_conflict_with_local_wins(self, tmp_path: Path) -> None:
        """Both sides changed -> CONFLICT, local-wins resolver picks local."""
        from trac_mcp_server.sync.state import SyncState

        old_content = "# Original\n"
        new_local = "# Changed locally\n"
        new_remote = "= Changed remotely =\n"
        old_hash = SyncState.content_hash(old_content)

        engine, client = _setup_engine(
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

        conflict_results = [
            r for r in report.results if r.action == SyncAction.CONFLICT
        ]
        assert len(conflict_results) == 1
        assert conflict_results[0].success is True


class TestDirectionFiltering:
    """Test that direction filtering restricts allowed actions."""

    def test_push_only_skips_pull(self, tmp_path: Path) -> None:
        """Push-only mode downgrades PULL to SKIP."""
        from trac_mcp_server.sync.state import SyncState

        local_content = "# Hello\n"
        old_remote = "= Hello =\n"
        new_remote = "= Updated =\n"
        local_hash = SyncState.content_hash(local_content)
        old_remote_hash = SyncState.content_hash(old_remote)

        engine, client = _setup_engine(
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

        # PULL should have been downgraded to SKIP
        pull_results = [
            r for r in report.results if r.action == SyncAction.PULL
        ]
        assert len(pull_results) == 0
        skip_results = [
            r for r in report.results if r.action == SyncAction.SKIP
        ]
        assert len(skip_results) >= 1

    def test_pull_only_skips_push(self, tmp_path: Path) -> None:
        """Pull-only mode downgrades PUSH to SKIP."""
        from trac_mcp_server.sync.state import SyncState

        old_local = "# Old\n"
        new_local = "# New content\n"
        remote_content = "= Old =\n"
        old_local_hash = SyncState.content_hash(old_local)
        remote_hash = SyncState.content_hash(remote_content)

        engine, client = _setup_engine(
            tmp_path,
            profile_overrides={"direction": "pull"},
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": remote_content},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_local_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        report = engine.run(dry_run=False)

        push_results = [
            r for r in report.results if r.action == SyncAction.PUSH
        ]
        assert len(push_results) == 0
        skip_results = [
            r for r in report.results if r.action == SyncAction.SKIP
        ]
        assert len(skip_results) >= 1


class TestGitSafety:
    """Test git safety check behavior."""

    def test_git_safety_block(self, tmp_path: Path) -> None:
        """Git safety 'block' prevents sync with uncommitted changes."""
        engine, client = _setup_engine(
            tmp_path,
            profile_overrides={"git_safety": "block"},
            local_files={"readme.md": "# Hello\n"},
        )

        # Mock subprocess to report uncommitted changes
        with patch(
            "trac_mcp_server.sync.engine.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                stdout=" M some_file.py\n", returncode=0
            )
            report = engine.run(dry_run=False)

        # Should have a single error result about git safety
        assert len(report.results) == 1
        assert report.results[0].success is False
        assert "git safety" in report.results[0].error.lower()

    def test_git_safety_none_allows(self, tmp_path: Path) -> None:
        """Git safety 'none' allows sync regardless."""
        engine, client = _setup_engine(
            tmp_path,
            profile_overrides={"git_safety": "none"},
            local_files={"readme.md": "# Hello\n"},
        )

        report = engine.run(dry_run=True)

        # Should proceed normally (at least one result)
        assert len(report.results) >= 1


class TestStateUpdate:
    """Test that state is updated after successful sync."""

    def test_state_updated_after_push(self, tmp_path: Path) -> None:
        """State file updated after a successful PUSH."""
        from trac_mcp_server.sync.state import SyncState

        old_local = "# Old\n"
        new_local = "# New content\n"
        remote_content = "= Old =\n"
        old_local_hash = SyncState.content_hash(old_local)
        remote_hash = SyncState.content_hash(remote_content)

        state_dir = tmp_path / ".trac_mcp"
        engine, client = _setup_engine(
            tmp_path,
            profile_overrides={"state_dir": str(state_dir)},
            local_files={"readme.md": new_local},
            client=FakeTracClient(
                pages={"Docs/readme": remote_content},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": old_local_hash,
                    "remote_hash": remote_hash,
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": False,
                }
            },
        )

        engine.run(dry_run=False)

        # Check state file was updated
        state_file = state_dir / "sync_test-profile.json"
        assert state_file.exists()
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        entry = state_data["entries"].get("readme.md")
        assert entry is not None
        assert entry["local_hash"] is not None
        assert entry["local_hash"] != old_local_hash  # hash changed


class TestErrorIsolation:
    """Test that a single file error doesn't abort the entire sync."""

    def test_error_does_not_abort(self, tmp_path: Path) -> None:
        """One file error, other files still sync."""

        # Two local files, but one remote page will error
        engine, _ = _setup_engine(
            tmp_path,
            local_files={
                "good.md": "# Good file\n",
                "bad.md": "# Bad file\n",
            },
        )

        # Create a client where one page info call fails
        class PartialFailClient(FakeTracClient):
            def get_wiki_page_info(
                self, page_name: str, version: Optional[int] = None
            ) -> Dict[str, Any]:
                if "bad" in page_name.lower():
                    raise RuntimeError("Simulated remote error")
                return super().get_wiki_page_info(page_name, version)

        engine.client = PartialFailClient()  # type: ignore[assignment]

        report = engine.run(dry_run=False)

        # Should have results for both files
        assert len(report.results) >= 2

        # At least one should succeed (the good file)
        successes = [r for r in report.results if r.success]
        assert len(successes) >= 1


class TestConflictedPathSkip:
    """Test that paths marked as conflicted are skipped."""

    def test_conflicted_path_skipped(self, tmp_path: Path) -> None:
        """Paths with conflicted=True in state are skipped."""
        engine, client = _setup_engine(
            tmp_path,
            local_files={"readme.md": "# Hello\n"},
            client=FakeTracClient(
                pages={"Docs/readme": "= Hello =\n"},
                versions={"Docs/readme": 1},
            ),
            state_entries={
                "readme.md": {
                    "wiki_page": "Docs/readme",
                    "local_hash": "abc",
                    "remote_hash": "def",
                    "remote_version": 1,
                    "last_synced": "2026-01-01T00:00:00Z",
                    "conflicted": True,
                }
            },
        )

        report = engine.run(dry_run=False)

        skip_results = [
            r for r in report.results if r.action == SyncAction.SKIP
        ]
        assert len(skip_results) >= 1
        # Should have the "unresolved conflict" note
        conflict_skips = [
            r
            for r in skip_results
            if r.error and "unresolved conflict" in r.error
        ]
        assert len(conflict_skips) >= 1
