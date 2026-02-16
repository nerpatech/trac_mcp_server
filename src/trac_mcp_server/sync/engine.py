"""Core sync engine that orchestrates the full bidirectional sync cycle.

The ``SyncEngine`` ties together state, mapper, reconciler, merger, and
resolver into a complete sync run.  It:

1. Loads persisted sync state for the profile.
2. Discovers local/remote pairs via the path mapper.
3. Gathers current content hashes on both sides.
4. Reconciles each pair to determine the sync action.
5. Filters actions by the configured direction.
6. Executes actions (push, pull, create, conflict resolution).
7. Updates state per-entry for crash safety.
8. Builds and returns a ``SyncReport``.

Error handling is per-pair: a single file failure does not abort the run.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from xmlrpc.client import Fault

from trac_mcp_server.config_schema import SyncProfileConfig
from trac_mcp_server.core.client import TracClient
from trac_mcp_server.sync.mapper import PathMapper
from trac_mcp_server.sync.models import (
    ConflictInfo,
    SyncAction,
    SyncReport,
    SyncResult,
)
from trac_mcp_server.sync.resolver import create_resolver
from trac_mcp_server.sync.state import SyncState

logger = logging.getLogger(__name__)


class SyncEngine:
    """Orchestrate a full bidirectional sync cycle for one profile.

    Args:
        client: TracClient for wiki operations.
        profile: The sync profile configuration.
        profile_name: Name of the sync profile (used for state files).
        source_root: Absolute path to the source directory.
    """

    def __init__(
        self,
        client: TracClient,
        profile: SyncProfileConfig,
        profile_name: str,
        source_root: Path,
    ) -> None:
        self.client = client
        self.profile = profile
        self.profile_name = profile_name
        self.source_root = source_root

        self.mapper = PathMapper(profile)
        self.state_store = SyncState(Path(profile.state_dir))
        self.resolver = create_resolver(profile.conflict_strategy)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, dry_run: bool = False) -> SyncReport:
        """Execute a full sync cycle.

        Args:
            dry_run: If ``True``, compute actions but do not execute them.

        Returns:
            A ``SyncReport`` summarising what was (or would be) done.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        results: list[SyncResult] = []

        # Git safety check for pull operations
        if self.profile.direction in ("pull", "bidirectional"):
            if not self._check_git_safety():
                return SyncReport(
                    profile_name=self.profile_name,
                    dry_run=dry_run,
                    results=[
                        SyncResult(
                            local_path="",
                            wiki_page="",
                            action=SyncAction.SKIP,
                            success=False,
                            error="Git safety check failed: uncommitted changes",
                        )
                    ],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

        # Step a: Load state
        state = self.state_store.load(self.profile_name)

        # Step b: Discover pairs
        try:
            wiki_pages = self.client.list_wiki_pages()
        except Exception as exc:
            logger.error("Failed to list wiki pages: %s", exc)
            wiki_pages = []

        pairs = self.mapper.build_pairs(self.source_root, wiki_pages)

        # Include pairs from state that no longer appear (delete detection)
        pair_locals = {lp for lp, _ in pairs}
        for local_path, entry in state.get("entries", {}).items():
            if local_path not in pair_locals:
                wiki_page = entry.get("wiki_page", "")
                if wiki_page:
                    pairs.append((local_path, wiki_page))

        # Process each pair
        for local_path, wiki_page in pairs:
            try:
                result = self._sync_pair(
                    local_path, wiki_page, state, dry_run
                )
                results.append(result)
            except Exception as exc:
                logger.error(
                    "Error syncing %s <-> %s: %s",
                    local_path,
                    wiki_page,
                    exc,
                )
                results.append(
                    SyncResult(
                        local_path=local_path,
                        wiki_page=wiki_page,
                        action=SyncAction.SKIP,
                        success=False,
                        error=str(exc),
                    )
                )

        completed_at = datetime.now(timezone.utc).isoformat()
        return SyncReport(
            profile_name=self.profile_name,
            dry_run=dry_run,
            results=results,
            started_at=started_at,
            completed_at=completed_at,
        )

    # ------------------------------------------------------------------
    # Per-pair sync
    # ------------------------------------------------------------------

    def _sync_pair(
        self,
        local_path: str,
        wiki_page: str,
        state: dict,
        dry_run: bool,
    ) -> SyncResult:
        """Sync a single local-path / wiki-page pair.

        Returns a ``SyncResult`` and mutates *state* in place on success.
        """
        # Check if path is conflicted in state
        if self.state_store.is_conflicted(state, local_path):
            logger.warning("Skipping conflicted path: %s", local_path)
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=SyncAction.SKIP,
                success=True,
                error="path has unresolved conflict",
            )

        # Step c: Gather current state
        local_content, local_hash = self._read_local(local_path)
        remote_content, remote_hash, remote_version = self._read_remote(
            wiki_page
        )

        # Get archive hashes from state (per-side, since formats differ)
        entry = self.state_store.get_entry(state, local_path)
        archive_local_hash = entry.get("local_hash") if entry else None
        archive_remote_hash = (
            entry.get("remote_hash") if entry else None
        )

        # Step d: Reconcile using dual-sided comparison
        # Local and remote are different formats (Markdown vs TracWiki),
        # so we compare each side against its own archived hash.
        action = self._dual_reconcile(
            local_hash,
            remote_hash,
            archive_local_hash,
            archive_remote_hash,
        )

        # Step e: Direction filtering
        action = self._filter_by_direction(action)

        # Step f: Execute (or skip if dry_run)
        if dry_run:
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=action,
                success=True,
            )

        return self._execute_action(
            action,
            local_path,
            wiki_page,
            local_content,
            local_hash,
            remote_content,
            remote_hash,
            remote_version,
            archive_local_hash,
            archive_remote_hash,
            entry,
            state,
        )

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    def _execute_action(
        self,
        action: SyncAction,
        local_path: str,
        wiki_page: str,
        local_content: str | None,
        local_hash: str | None,
        remote_content: str | None,
        remote_hash: str | None,
        remote_version: int | None,
        archive_local_hash: str | None,
        archive_remote_hash: str | None,
        entry: dict | None,
        state: dict,
    ) -> SyncResult:
        """Execute a sync action for one pair."""
        if action == SyncAction.SKIP:
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=action,
                success=True,
            )

        if action == SyncAction.PUSH:
            return self._do_push(
                local_path,
                wiki_page,
                local_content,
                local_hash,
                remote_hash,
                remote_version,
                state,
            )

        if action == SyncAction.CREATE_REMOTE:
            return self._do_push(
                local_path,
                wiki_page,
                local_content,
                local_hash,
                remote_hash,
                None,  # No remote version for new page
                state,
            )

        if action == SyncAction.PULL:
            return self._do_pull(
                local_path,
                wiki_page,
                remote_content,
                local_hash,
                remote_hash,
                remote_version,
                state,
            )

        if action == SyncAction.CREATE_LOCAL:
            return self._do_pull(
                local_path,
                wiki_page,
                remote_content,
                local_hash,
                remote_hash,
                remote_version,
                state,
            )

        if action in (
            SyncAction.DELETE_REMOTE,
            SyncAction.DELETE_LOCAL,
        ):
            logger.info(
                "Delete propagation disabled for %s (action=%s)",
                local_path,
                action.value,
            )
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=action,
                success=True,
                error="delete propagation disabled",
            )

        if action == SyncAction.CONFLICT:
            return self._do_conflict(
                local_path,
                wiki_page,
                local_content,
                local_hash,
                remote_content,
                remote_hash,
                remote_version,
                archive_local_hash,
                archive_remote_hash,
                entry,
                state,
            )

        # Fallback -- should not happen
        return SyncResult(
            local_path=local_path,
            wiki_page=wiki_page,
            action=action,
            success=False,
            error=f"Unhandled action: {action}",
        )

    def _do_push(
        self,
        local_path: str,
        wiki_page: str,
        local_content: str | None,
        local_hash: str | None,
        remote_hash: str | None,
        remote_version: int | None,
        state: dict,
    ) -> SyncResult:
        """Push local content to remote wiki."""
        from trac_mcp_server.converters.markdown_to_tracwiki import (
            markdown_to_tracwiki,
        )

        if local_content is None:
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=SyncAction.PUSH,
                success=False,
                error="No local content to push",
            )

        tracwiki_content = markdown_to_tracwiki(local_content)
        try:
            self.client.put_wiki_page(
                wiki_page,
                tracwiki_content,
                comment=f"Synced from {local_path}",
                version=remote_version,
            )
        except Exception as exc:
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=SyncAction.PUSH,
                success=False,
                error=str(exc),
            )

        # Get new remote hash after push
        new_remote_hash = SyncState.content_hash(tracwiki_content)
        # Fetch updated version info
        try:
            info = self.client.get_wiki_page_info(wiki_page)
            new_version = info.get("version")
        except Exception:
            new_version = (remote_version or 0) + 1

        self._update_state(
            state,
            local_path,
            wiki_page,
            local_hash,
            new_remote_hash,
            new_version,
        )

        return SyncResult(
            local_path=local_path,
            wiki_page=wiki_page,
            action=SyncAction.PUSH,
            success=True,
        )

    def _do_pull(
        self,
        local_path: str,
        wiki_page: str,
        remote_content: str | None,
        local_hash: str | None,
        remote_hash: str | None,
        remote_version: int | None,
        state: dict,
    ) -> SyncResult:
        """Pull remote content to local file."""
        from trac_mcp_server.converters.tracwiki_to_markdown import (
            tracwiki_to_markdown,
        )
        from trac_mcp_server.file_handler import write_file

        if remote_content is None:
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=SyncAction.PULL,
                success=False,
                error="No remote content to pull",
            )

        conversion_result = tracwiki_to_markdown(remote_content)
        md_content = conversion_result.text

        abs_path = self.source_root / local_path
        try:
            write_file(abs_path, md_content)
        except Exception as exc:
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=SyncAction.PULL,
                success=False,
                error=str(exc),
            )

        new_local_hash = SyncState.content_hash(md_content)

        self._update_state(
            state,
            local_path,
            wiki_page,
            new_local_hash,
            remote_hash,
            remote_version,
        )

        return SyncResult(
            local_path=local_path,
            wiki_page=wiki_page,
            action=SyncAction.PULL,
            success=True,
        )

    def _do_conflict(
        self,
        local_path: str,
        wiki_page: str,
        local_content: str | None,
        local_hash: str | None,
        remote_content: str | None,
        remote_hash: str | None,
        remote_version: int | None,
        archive_local_hash: str | None,
        archive_remote_hash: str | None,
        entry: dict | None,
        state: dict,
    ) -> SyncResult:
        """Handle a conflict via the configured resolver."""
        from trac_mcp_server.file_handler import write_file

        # Build ConflictInfo
        base_content = self._get_base_content(wiki_page, entry)

        conflict = ConflictInfo(
            local_path=local_path,
            wiki_page=wiki_page,
            action=SyncAction.CONFLICT,
            base_content=base_content,
            local_content=local_content or "",
            remote_content=remote_content or "",
            has_markers=False,
        )

        resolution = self.resolver.resolve(conflict)
        resolved_content = self.resolver.get_resolved_content(
            conflict, resolution
        )

        if resolution == "skip" or resolved_content is None:
            return SyncResult(
                local_path=local_path,
                wiki_page=wiki_page,
                action=SyncAction.CONFLICT,
                success=True,
                error=f"conflict skipped (resolution={resolution})",
            )

        if resolution in ("local", "merged"):
            # Write resolved content locally and push to remote
            abs_path = self.source_root / local_path
            try:
                write_file(abs_path, resolved_content)
            except Exception as exc:
                return SyncResult(
                    local_path=local_path,
                    wiki_page=wiki_page,
                    action=SyncAction.CONFLICT,
                    success=False,
                    error=str(exc),
                )

            new_local_hash = SyncState.content_hash(resolved_content)
            self._update_state(
                state,
                local_path,
                wiki_page,
                new_local_hash,
                remote_hash,
                remote_version,
            )

        elif resolution == "remote":
            # Write remote content to local
            abs_path = self.source_root / local_path
            try:
                write_file(abs_path, resolved_content)
            except Exception as exc:
                return SyncResult(
                    local_path=local_path,
                    wiki_page=wiki_page,
                    action=SyncAction.CONFLICT,
                    success=False,
                    error=str(exc),
                )

            new_local_hash = SyncState.content_hash(resolved_content)
            self._update_state(
                state,
                local_path,
                wiki_page,
                new_local_hash,
                remote_hash,
                remote_version,
            )

        elif resolution == "markers":
            # Write marker content to local file, mark as conflicted
            abs_path = self.source_root / local_path
            try:
                write_file(abs_path, resolved_content)
            except Exception as exc:
                return SyncResult(
                    local_path=local_path,
                    wiki_page=wiki_page,
                    action=SyncAction.CONFLICT,
                    success=False,
                    error=str(exc),
                )

            # Mark conflicted in state so future syncs skip this path
            self.state_store.update_entry(
                state,
                local_path,
                {
                    "wiki_page": wiki_page,
                    "local_hash": local_hash,
                    "remote_hash": remote_hash,
                    "remote_version": remote_version,
                    "last_synced": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "conflicted": True,
                },
            )
            self.state_store.save(self.profile_name, state)

        return SyncResult(
            local_path=local_path,
            wiki_page=wiki_page,
            action=SyncAction.CONFLICT,
            success=True,
        )

    # ------------------------------------------------------------------
    # Git safety
    # ------------------------------------------------------------------

    def _check_git_safety(self) -> bool:
        """Check git working tree for uncommitted changes.

        Returns:
            ``True`` if safe to proceed, ``False`` if blocked.
        """
        if self.profile.git_safety == "none":
            return True

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.source_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            has_changes = bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # No git or timeout -- treat as no changes
            return True

        if not has_changes:
            return True

        if self.profile.git_safety == "block":
            logger.error(
                "Git safety check failed: uncommitted changes in %s",
                self.source_root,
            )
            return False

        if self.profile.git_safety == "warn":
            logger.warning(
                "Uncommitted changes detected in %s (git_safety=warn)",
                self.source_root,
            )
            return True

        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_local(
        self, local_path: str
    ) -> tuple[str | None, str | None]:
        """Read local file content and compute hash.

        Returns ``(content, hash)`` or ``(None, None)`` if missing.
        """
        from trac_mcp_server.file_handler import read_file_with_encoding

        abs_path = self.source_root / local_path
        if not abs_path.exists():
            return None, None

        try:
            content, _ = read_file_with_encoding(abs_path)
            return content, SyncState.content_hash(content)
        except Exception as exc:
            logger.error("Error reading %s: %s", abs_path, exc)
            return None, None

    def _read_remote(
        self, wiki_page: str
    ) -> tuple[str | None, str | None, int | None]:
        """Read remote wiki page content, hash, and version.

        Returns ``(content, hash, version)`` or ``(None, None, None)``
        if the page does not exist.
        """
        try:
            info = self.client.get_wiki_page_info(wiki_page)
            version = info.get("version")
            content = self.client.get_wiki_page(wiki_page)
            return content, SyncState.content_hash(content), version
        except Fault:
            # Page does not exist
            return None, None, None
        except Exception as exc:
            logger.error(
                "Error reading remote page %s: %s", wiki_page, exc
            )
            return None, None, None

    def _get_base_content(
        self, wiki_page: str, entry: dict | None
    ) -> str | None:
        """Retrieve the merge base content from Trac version history.

        Returns ``None`` if the base cannot be retrieved.
        """
        if entry is None:
            return None

        archive_version = entry.get("remote_version")
        if archive_version is None:
            return None

        try:
            return self.client.get_wiki_page(
                wiki_page, version=archive_version
            )
        except Exception as exc:
            logger.warning(
                "Could not retrieve base version %s for %s: %s",
                archive_version,
                wiki_page,
                exc,
            )
            return None

    def _dual_reconcile(
        self,
        local_hash: str | None,
        remote_hash: str | None,
        archive_local_hash: str | None,
        archive_remote_hash: str | None,
    ) -> SyncAction:
        """Reconcile using per-side archive comparison.

        Since local content is Markdown and remote is TracWiki, their
        hashes are never directly comparable.  Instead we compare each
        side against its own archived hash to detect changes.
        """
        local_exists = local_hash is not None
        remote_exists = remote_hash is not None
        has_archive = (
            archive_local_hash is not None
            or archive_remote_hash is not None
        )

        # Both absent
        if not local_exists and not remote_exists:
            return SyncAction.SKIP

        # No archive (first sync)
        if not has_archive:
            if local_exists and not remote_exists:
                return SyncAction.CREATE_REMOTE
            if not local_exists and remote_exists:
                return SyncAction.CREATE_LOCAL
            # Both exist, no archive -- conflict (both created independently)
            return SyncAction.CONFLICT

        # Archive exists -- compare each side against its archived hash
        local_changed = (
            local_exists and local_hash != archive_local_hash
        )
        remote_changed = (
            remote_exists and remote_hash != archive_remote_hash
        )
        local_deleted = not local_exists
        remote_deleted = not remote_exists

        # Deletion cases
        if local_deleted and remote_deleted:
            return SyncAction.SKIP

        if local_deleted:
            if remote_changed:
                return SyncAction.CONFLICT
            return SyncAction.DELETE_REMOTE

        if remote_deleted:
            if local_changed:
                return SyncAction.CONFLICT
            return SyncAction.DELETE_LOCAL

        # Both exist
        if not local_changed and not remote_changed:
            return SyncAction.SKIP

        if local_changed and not remote_changed:
            return SyncAction.PUSH

        if not local_changed and remote_changed:
            return SyncAction.PULL

        # Both changed
        return SyncAction.CONFLICT

    def _filter_by_direction(self, action: SyncAction) -> SyncAction:
        """Downgrade actions that are not allowed by the profile direction."""
        direction = self.profile.direction

        if direction == "bidirectional":
            return action

        push_only = {
            SyncAction.PUSH,
            SyncAction.CREATE_REMOTE,
            SyncAction.DELETE_REMOTE,
        }
        pull_only = {
            SyncAction.PULL,
            SyncAction.CREATE_LOCAL,
            SyncAction.DELETE_LOCAL,
        }

        if direction == "push" and action in pull_only:
            logger.info(
                "Downgrading %s to SKIP (direction=push)", action.value
            )
            return SyncAction.SKIP
        if direction == "pull" and action in push_only:
            logger.info(
                "Downgrading %s to SKIP (direction=pull)", action.value
            )
            return SyncAction.SKIP

        return action

    def _update_state(
        self,
        state: dict,
        local_path: str,
        wiki_page: str,
        local_hash: str | None,
        remote_hash: str | None,
        remote_version: int | None,
    ) -> None:
        """Update sync state for one path and persist immediately."""
        self.state_store.update_entry(
            state,
            local_path,
            {
                "wiki_page": wiki_page,
                "local_hash": local_hash,
                "remote_hash": remote_hash,
                "remote_version": remote_version,
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "conflicted": False,
            },
        )
        self.state_store.save(self.profile_name, state)
