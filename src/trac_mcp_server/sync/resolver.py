"""Conflict resolution strategies for the sync engine.

Provides multiple conflict resolution approaches:

- ``InteractiveResolver``: Attempts three-way merge; accumulates unresolved
  conflicts for human review (no I/O -- prepares data for the engine to
  present).
- ``UnattendedResolver``: Attempts three-way merge; writes conflict markers
  and accumulates ticket-creation data for unresolved conflicts.
- ``LocalWinsResolver``: Always picks local content.
- ``RemoteWinsResolver``: Always picks remote content.

The ``create_resolver()`` factory maps config strategy strings to resolver
instances.
"""

from __future__ import annotations

import difflib
import logging
from typing import Protocol

from trac_mcp_server.sync.merger import attempt_merge
from trac_mcp_server.sync.models import ConflictInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ConflictResolver(Protocol):
    """Protocol that all conflict resolvers must satisfy."""

    def resolve(self, conflict: ConflictInfo) -> str:
        """Determine the resolution for a conflict.

        Args:
            conflict: Details about the conflicting file/page pair.

        Returns:
            Resolution string: ``"local"``, ``"remote"``, ``"merged"``,
            ``"skip"``, or ``"markers"``.
        """
        ...  # pragma: no cover

    def get_resolved_content(
        self, conflict: ConflictInfo, resolution: str
    ) -> str | None:
        """Return the content to use for the given resolution.

        Args:
            conflict: The conflict details.
            resolution: The resolution string returned by ``resolve()``.

        Returns:
            The content string to write, or ``None`` if no content change
            is needed (e.g. ``"skip"``).
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Interactive resolver
# ---------------------------------------------------------------------------


class InteractiveResolver:
    """Resolve conflicts interactively.

    Attempts a three-way merge first.  If the merge is clean the conflict
    is auto-resolved.  If there are conflict markers, the conflict is
    accumulated in ``pending_conflicts`` for the engine to present to the
    user.  The resolver itself does no I/O.
    """

    def __init__(self) -> None:
        self.pending_conflicts: list[ConflictInfo] = []

    def resolve(self, conflict: ConflictInfo) -> str:
        """Attempt auto-merge; accumulate unresolvable conflicts."""
        if conflict.base_content is not None:
            merged_text, has_conflicts = attempt_merge(
                conflict.base_content,
                conflict.local_content,
                conflict.remote_content,
            )
            if not has_conflicts:
                logger.info(
                    "Clean three-way merge for %s", conflict.local_path
                )
                # Store merged content on a mutable copy-like approach:
                # we return "merged" and get_resolved_content will re-merge.
                return "merged"

            # Has conflict markers -- prepare diff for human review
            _diff = "".join(
                difflib.unified_diff(
                    conflict.local_content.splitlines(True),
                    conflict.remote_content.splitlines(True),
                    fromfile=f"local/{conflict.local_path}",
                    tofile=f"remote/{conflict.wiki_page}",
                )
            )
            logger.info(
                "Conflict with markers for %s -- pending human review",
                conflict.local_path,
            )
            # Store the conflict with diff info for engine to present
            enriched = ConflictInfo(
                local_path=conflict.local_path,
                wiki_page=conflict.wiki_page,
                action=conflict.action,
                base_content=conflict.base_content,
                local_content=conflict.local_content,
                remote_content=conflict.remote_content,
                merged_content=merged_text,
                has_markers=True,
            )
            self.pending_conflicts.append(enriched)
            return "skip"

        # No base content -- cannot three-way merge
        logger.warning(
            "No base content for %s -- cannot auto-merge, pending review",
            conflict.local_path,
        )
        self.pending_conflicts.append(conflict)
        return "skip"

    def get_resolved_content(
        self, conflict: ConflictInfo, resolution: str
    ) -> str | None:
        """Return content for the chosen resolution."""
        if resolution == "merged" and conflict.base_content is not None:
            merged_text, _ = attempt_merge(
                conflict.base_content,
                conflict.local_content,
                conflict.remote_content,
            )
            return merged_text
        if resolution == "local":
            return conflict.local_content
        if resolution == "remote":
            return conflict.remote_content
        # "skip" or unknown
        return None


# ---------------------------------------------------------------------------
# Unattended resolver
# ---------------------------------------------------------------------------


class UnattendedResolver:
    """Resolve conflicts in unattended / scheduled mode.

    Attempts a three-way merge first.  If the merge is clean, auto-resolves.
    If there are conflict markers, returns ``"markers"`` and accumulates
    ticket creation data.
    """

    def __init__(self) -> None:
        self.tickets_to_create: list[dict] = []

    def resolve(self, conflict: ConflictInfo) -> str:
        """Attempt auto-merge; write markers for unresolvable conflicts."""
        if conflict.base_content is not None:
            merged_text, has_conflicts = attempt_merge(
                conflict.base_content,
                conflict.local_content,
                conflict.remote_content,
            )
            if not has_conflicts:
                logger.info(
                    "Clean three-way merge for %s (unattended)",
                    conflict.local_path,
                )
                return "merged"

            # Has markers -- record ticket info
            logger.info(
                "Conflict markers written for %s -- ticket queued",
                conflict.local_path,
            )
            self.tickets_to_create.append(
                {
                    "local_path": conflict.local_path,
                    "wiki_page": conflict.wiki_page,
                    "description": (
                        f"Sync conflict detected between local file "
                        f"'{conflict.local_path}' and wiki page "
                        f"'{conflict.wiki_page}'. Conflict markers have "
                        f"been written to the local file. Please resolve "
                        f"manually."
                    ),
                }
            )
            return "markers"

        # No base content -- full conflict, write markers with both versions
        logger.warning(
            "No base content for %s (unattended) -- writing markers",
            conflict.local_path,
        )
        self.tickets_to_create.append(
            {
                "local_path": conflict.local_path,
                "wiki_page": conflict.wiki_page,
                "description": (
                    f"Sync conflict detected between local file "
                    f"'{conflict.local_path}' and wiki page "
                    f"'{conflict.wiki_page}'. No merge base available; "
                    f"both versions differ. Please resolve manually."
                ),
            }
        )
        return "markers"

    def get_resolved_content(
        self, conflict: ConflictInfo, resolution: str
    ) -> str | None:
        """Return content for the chosen resolution."""
        if resolution == "merged" and conflict.base_content is not None:
            merged_text, _ = attempt_merge(
                conflict.base_content,
                conflict.local_content,
                conflict.remote_content,
            )
            return merged_text
        if (
            resolution == "markers"
            and conflict.base_content is not None
        ):
            merged_text, _ = attempt_merge(
                conflict.base_content,
                conflict.local_content,
                conflict.remote_content,
            )
            return merged_text
        if resolution == "markers" and conflict.base_content is None:
            # No base -- write both versions with markers
            return (
                "<<<<<<< LOCAL\n"
                + conflict.local_content
                + "\n=======\n"
                + conflict.remote_content
                + "\n>>>>>>> REMOTE\n"
            )
        if resolution == "local":
            return conflict.local_content
        if resolution == "remote":
            return conflict.remote_content
        return None


# ---------------------------------------------------------------------------
# Simple resolvers
# ---------------------------------------------------------------------------


class LocalWinsResolver:
    """Always resolve conflicts in favour of local content."""

    def resolve(self, conflict: ConflictInfo) -> str:
        """Always return ``"local"``."""
        return "local"

    def get_resolved_content(
        self, conflict: ConflictInfo, resolution: str
    ) -> str | None:
        """Return local content."""
        if resolution == "local":
            return conflict.local_content
        if resolution == "remote":
            return conflict.remote_content
        return None


class RemoteWinsResolver:
    """Always resolve conflicts in favour of remote content."""

    def resolve(self, conflict: ConflictInfo) -> str:
        """Always return ``"remote"``."""
        return "remote"

    def get_resolved_content(
        self, conflict: ConflictInfo, resolution: str
    ) -> str | None:
        """Return remote content."""
        if resolution == "remote":
            return conflict.remote_content
        if resolution == "local":
            return conflict.local_content
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_STRATEGY_MAP: dict[str, type] = {
    "interactive": InteractiveResolver,
    "markers": UnattendedResolver,
    "local-wins": LocalWinsResolver,
    "remote-wins": RemoteWinsResolver,
}


def create_resolver(strategy: str) -> ConflictResolver:
    """Create a conflict resolver for the given strategy string.

    Args:
        strategy: One of ``"interactive"``, ``"markers"``,
            ``"local-wins"``, ``"remote-wins"``.

    Returns:
        A ``ConflictResolver`` implementation instance.

    Raises:
        ValueError: If the strategy string is not recognised.
    """
    cls = _STRATEGY_MAP.get(strategy)
    if cls is None:
        raise ValueError(
            f"Unknown conflict strategy: '{strategy}'. Valid strategies: {sorted(_STRATEGY_MAP.keys())}"
        )
    return cls()  # type: ignore[return-value]
