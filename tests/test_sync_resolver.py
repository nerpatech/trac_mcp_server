"""Tests for sync conflict resolver strategies."""

from __future__ import annotations

import pytest

from trac_mcp_server.sync.models import ConflictInfo, SyncAction
from trac_mcp_server.sync.resolver import (
    InteractiveResolver,
    LocalWinsResolver,
    RemoteWinsResolver,
    UnattendedResolver,
    create_resolver,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conflict(
    *,
    base: str | None = None,
    local: str = "local content\n",
    remote: str = "remote content\n",
    has_markers: bool = False,
) -> ConflictInfo:
    """Build a minimal ConflictInfo for testing."""
    return ConflictInfo(
        local_path="docs/readme.md",
        wiki_page="Docs/Readme",
        action=SyncAction.CONFLICT,
        base_content=base,
        local_content=local,
        remote_content=remote,
        has_markers=has_markers,
    )


# ---------------------------------------------------------------------------
# InteractiveResolver
# ---------------------------------------------------------------------------


class TestInteractiveResolver:
    """Tests for InteractiveResolver."""

    def test_clean_merge_returns_merged(self) -> None:
        """Clean three-way merge auto-resolves to 'merged'."""
        base = "aaa\nbbb\nccc\nddd\neee\n"
        local = "aaa\nBBB\nccc\nddd\neee\n"
        remote = "aaa\nbbb\nccc\nddd\nEEE\n"

        resolver = InteractiveResolver()
        conflict = _make_conflict(base=base, local=local, remote=remote)
        resolution = resolver.resolve(conflict)

        assert resolution == "merged"
        assert len(resolver.pending_conflicts) == 0

    def test_clean_merge_content(self) -> None:
        """get_resolved_content returns merged text for clean merge."""
        base = "aaa\nbbb\nccc\nddd\neee\n"
        local = "aaa\nBBB\nccc\nddd\neee\n"
        remote = "aaa\nbbb\nccc\nddd\nEEE\n"

        resolver = InteractiveResolver()
        conflict = _make_conflict(base=base, local=local, remote=remote)
        resolution = resolver.resolve(conflict)

        content = resolver.get_resolved_content(conflict, resolution)
        assert content is not None
        assert "BBB" in content
        assert "EEE" in content

    def test_dirty_merge_accumulates_conflict(self) -> None:
        """Conflicting three-way merge returns 'skip' and accumulates."""
        base = "line 1\nline 2\nline 3\n"
        local = "line 1\nline 2 changed locally\nline 3\n"
        remote = "line 1\nline 2 changed remotely\nline 3\n"

        resolver = InteractiveResolver()
        conflict = _make_conflict(base=base, local=local, remote=remote)
        resolution = resolver.resolve(conflict)

        assert resolution == "skip"
        assert len(resolver.pending_conflicts) == 1
        pending = resolver.pending_conflicts[0]
        assert pending.has_markers is True
        assert pending.merged_content is not None
        assert "<<<<<<< LOCAL" in pending.merged_content

    def test_no_base_accumulates_conflict(self) -> None:
        """Without base content, conflict is accumulated as pending."""
        resolver = InteractiveResolver()
        conflict = _make_conflict(base=None)
        resolution = resolver.resolve(conflict)

        assert resolution == "skip"
        assert len(resolver.pending_conflicts) == 1

    def test_get_resolved_content_local(self) -> None:
        """get_resolved_content returns local content for 'local'."""
        resolver = InteractiveResolver()
        conflict = _make_conflict()
        content = resolver.get_resolved_content(conflict, "local")
        assert content == conflict.local_content

    def test_get_resolved_content_remote(self) -> None:
        """get_resolved_content returns remote content for 'remote'."""
        resolver = InteractiveResolver()
        conflict = _make_conflict()
        content = resolver.get_resolved_content(conflict, "remote")
        assert content == conflict.remote_content

    def test_get_resolved_content_skip_returns_none(self) -> None:
        """get_resolved_content returns None for 'skip'."""
        resolver = InteractiveResolver()
        conflict = _make_conflict()
        content = resolver.get_resolved_content(conflict, "skip")
        assert content is None


# ---------------------------------------------------------------------------
# UnattendedResolver
# ---------------------------------------------------------------------------


class TestUnattendedResolver:
    """Tests for UnattendedResolver."""

    def test_clean_merge_returns_merged(self) -> None:
        """Clean three-way merge auto-resolves to 'merged'."""
        base = "aaa\nbbb\nccc\nddd\neee\n"
        local = "aaa\nBBB\nccc\nddd\neee\n"
        remote = "aaa\nbbb\nccc\nddd\nEEE\n"

        resolver = UnattendedResolver()
        conflict = _make_conflict(base=base, local=local, remote=remote)
        resolution = resolver.resolve(conflict)

        assert resolution == "merged"
        assert len(resolver.tickets_to_create) == 0

    def test_dirty_merge_returns_markers(self) -> None:
        """Conflicting merge returns 'markers' and queues ticket."""
        base = "line 1\nline 2\nline 3\n"
        local = "line 1\nline 2 changed locally\nline 3\n"
        remote = "line 1\nline 2 changed remotely\nline 3\n"

        resolver = UnattendedResolver()
        conflict = _make_conflict(base=base, local=local, remote=remote)
        resolution = resolver.resolve(conflict)

        assert resolution == "markers"
        assert len(resolver.tickets_to_create) == 1
        ticket = resolver.tickets_to_create[0]
        assert ticket["local_path"] == "docs/readme.md"
        assert ticket["wiki_page"] == "Docs/Readme"
        assert "conflict" in ticket["description"].lower()

    def test_dirty_merge_content_has_markers(self) -> None:
        """get_resolved_content returns marker-bearing text."""
        base = "line 1\nline 2\nline 3\n"
        local = "line 1\nline 2 changed locally\nline 3\n"
        remote = "line 1\nline 2 changed remotely\nline 3\n"

        resolver = UnattendedResolver()
        conflict = _make_conflict(base=base, local=local, remote=remote)
        resolution = resolver.resolve(conflict)
        content = resolver.get_resolved_content(conflict, resolution)

        assert content is not None
        assert "<<<<<<< LOCAL" in content

    def test_no_base_returns_markers(self) -> None:
        """Without base content, returns 'markers' with both versions."""
        resolver = UnattendedResolver()
        conflict = _make_conflict(base=None)
        resolution = resolver.resolve(conflict)

        assert resolution == "markers"
        assert len(resolver.tickets_to_create) == 1

    def test_no_base_marker_content(self) -> None:
        """Marker content without base wraps both versions."""
        resolver = UnattendedResolver()
        conflict = _make_conflict(
            base=None, local="my local\n", remote="my remote\n"
        )
        resolution = resolver.resolve(conflict)
        content = resolver.get_resolved_content(conflict, resolution)

        assert content is not None
        assert "<<<<<<< LOCAL" in content
        assert "my local" in content
        assert "my remote" in content
        assert ">>>>>>> REMOTE" in content

    def test_clean_merge_content(self) -> None:
        """get_resolved_content returns merged text for clean merge."""
        base = "aaa\nbbb\nccc\nddd\neee\n"
        local = "aaa\nBBB\nccc\nddd\neee\n"
        remote = "aaa\nbbb\nccc\nddd\nEEE\n"

        resolver = UnattendedResolver()
        conflict = _make_conflict(base=base, local=local, remote=remote)
        resolution = resolver.resolve(conflict)
        content = resolver.get_resolved_content(conflict, resolution)

        assert content is not None
        assert "<<<<<<< LOCAL" not in content
        assert "BBB" in content
        assert "EEE" in content


# ---------------------------------------------------------------------------
# LocalWinsResolver
# ---------------------------------------------------------------------------


class TestLocalWinsResolver:
    """Tests for LocalWinsResolver."""

    def test_always_returns_local(self) -> None:
        """resolve() always returns 'local'."""
        resolver = LocalWinsResolver()
        conflict = _make_conflict()
        assert resolver.resolve(conflict) == "local"

    def test_content_is_local(self) -> None:
        """get_resolved_content returns local content."""
        resolver = LocalWinsResolver()
        conflict = _make_conflict(local="LOCAL\n")
        content = resolver.get_resolved_content(conflict, "local")
        assert content == "LOCAL\n"


# ---------------------------------------------------------------------------
# RemoteWinsResolver
# ---------------------------------------------------------------------------


class TestRemoteWinsResolver:
    """Tests for RemoteWinsResolver."""

    def test_always_returns_remote(self) -> None:
        """resolve() always returns 'remote'."""
        resolver = RemoteWinsResolver()
        conflict = _make_conflict()
        assert resolver.resolve(conflict) == "remote"

    def test_content_is_remote(self) -> None:
        """get_resolved_content returns remote content."""
        resolver = RemoteWinsResolver()
        conflict = _make_conflict(remote="REMOTE\n")
        content = resolver.get_resolved_content(conflict, "remote")
        assert content == "REMOTE\n"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateResolver:
    """Tests for create_resolver factory."""

    def test_interactive(self) -> None:
        resolver = create_resolver("interactive")
        assert isinstance(resolver, InteractiveResolver)

    def test_markers(self) -> None:
        resolver = create_resolver("markers")
        assert isinstance(resolver, UnattendedResolver)

    def test_local_wins(self) -> None:
        resolver = create_resolver("local-wins")
        assert isinstance(resolver, LocalWinsResolver)

    def test_remote_wins(self) -> None:
        resolver = create_resolver("remote-wins")
        assert isinstance(resolver, RemoteWinsResolver)

    def test_unknown_raises(self) -> None:
        with pytest.raises(
            ValueError, match="Unknown conflict strategy"
        ):
            create_resolver("nonexistent")
