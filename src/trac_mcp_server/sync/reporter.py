"""Sync report formatting functions.

Provides human-readable and machine-readable output for sync operations:

- ``format_sync_report`` -- full post-sync summary.
- ``format_dry_run_preview`` -- dry-run preview grouped by action.
- ``format_conflict_diff`` -- unified diff for interactive conflict review.
- ``report_to_json`` -- structured dict for MCP tool output.
"""

from __future__ import annotations

import difflib
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ConflictInfo, SyncReport

from .models import SyncAction

# ------------------------------------------------------------------
# Human-readable report
# ------------------------------------------------------------------


def format_sync_report(report: SyncReport) -> str:
    """Format a complete sync report as human-readable text.

    Sections are only included when they contain at least one result.
    Skipped paths are summarised by count only to avoid excessive output.

    Args:
        report: The completed sync report.

    Returns:
        Multi-line formatted string.
    """
    lines: list[str] = []

    # Header
    header = f"Sync report for '{report.profile_name}'"
    if report.dry_run:
        header += " (DRY RUN)"
    lines.append(header)
    lines.append(f"Started: {report.started_at}")
    if report.completed_at:
        lines.append(f"Completed: {report.completed_at}")
    lines.append("")

    # Summary line
    total = len(report.results)
    pushed = len(report.updated_remote)
    pulled = len(report.updated_local)
    created_remote = len(report.created_remote)
    created_local = len(report.created_local)
    conflicts = len(report.conflicts)
    errors = len(report.errors)
    skipped = len(report.skipped)

    lines.append(
        f"Synced {total} files: "
        f"{pushed} pushed, {pulled} pulled, "
        f"{created_remote + created_local} created, "
        f"{conflicts} conflicts, {errors} errors"
    )
    lines.append("")

    # Per-action sections (only if non-empty)
    if report.updated_remote:
        lines.append("Pushed to wiki:")
        for r in report.updated_remote:
            lines.append(f"  {r.local_path} -> {r.wiki_page}")
        lines.append("")

    if report.updated_local:
        lines.append("Pulled from wiki:")
        for r in report.updated_local:
            lines.append(f"  {r.wiki_page} -> {r.local_path}")
        lines.append("")

    if report.created_remote:
        lines.append("Created (remote):")
        for r in report.created_remote:
            lines.append(f"  {r.local_path} -> {r.wiki_page}")
        lines.append("")

    if report.created_local:
        lines.append("Created (local):")
        for r in report.created_local:
            lines.append(f"  {r.wiki_page} -> {r.local_path}")
        lines.append("")

    if report.conflicts:
        lines.append("Conflicts:")
        for r in report.conflicts:
            desc = r.error or "both sides changed"
            lines.append(f"  {r.local_path} <-> {r.wiki_page}: {desc}")
        lines.append("")

    if report.errors:
        lines.append("Errors:")
        for r in report.errors:
            lines.append(f"  {r.local_path}: {r.error}")
        lines.append("")

    if skipped > 0:
        lines.append(f"Skipped: {skipped} files")
        lines.append("")

    return "\n".join(lines).rstrip()


# ------------------------------------------------------------------
# Dry-run preview
# ------------------------------------------------------------------


def format_dry_run_preview(report: SyncReport) -> str:
    """Format a dry-run preview grouped by action type.

    Each proposed action is shown as ``[ACTION] local_path <-> wiki_page``.

    Args:
        report: A dry-run sync report (``dry_run=True``).

    Returns:
        Multi-line formatted string.
    """
    lines: list[str] = []
    lines.append("DRY RUN -- No changes will be made")
    lines.append(f"Profile: {report.profile_name}")
    lines.append("")

    # Group by action
    groups: dict[SyncAction, list[tuple[str, str]]] = defaultdict(list)
    for r in report.results:
        groups[r.action].append((r.local_path, r.wiki_page))

    # Display order (skip SKIP for brevity)
    display_order = [
        SyncAction.PUSH,
        SyncAction.PULL,
        SyncAction.CREATE_REMOTE,
        SyncAction.CREATE_LOCAL,
        SyncAction.DELETE_REMOTE,
        SyncAction.DELETE_LOCAL,
        SyncAction.CONFLICT,
    ]

    for action in display_order:
        if action not in groups:
            continue
        pairs = groups[action]
        label = action.value.upper().replace("_", " ")
        lines.append(f"[{label}]")
        for local_path, wiki_page in pairs:
            lines.append(f"  {local_path} <-> {wiki_page}")
        lines.append("")

    # Mention skipped count if any
    skip_count = len(groups.get(SyncAction.SKIP, []))
    if skip_count > 0:
        lines.append(f"Skipped: {skip_count} files (unchanged)")
        lines.append("")

    if not any(a != SyncAction.SKIP for a in groups):
        lines.append("No changes needed.")
        lines.append("")

    return "\n".join(lines).rstrip()


# ------------------------------------------------------------------
# Conflict diff
# ------------------------------------------------------------------


def format_conflict_diff(conflict: ConflictInfo) -> str:
    """Format a single conflict for interactive review.

    Shows a unified diff between local and remote content, plus merge
    result information when available.

    Args:
        conflict: The conflict details.

    Returns:
        Multi-line formatted string with diff and merge info.
    """
    lines: list[str] = []
    lines.append(
        f"Conflict: {conflict.local_path} <-> {conflict.wiki_page}"
    )
    lines.append("")

    # Unified diff
    local_lines = conflict.local_content.splitlines(keepends=True)
    remote_lines = conflict.remote_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        local_lines,
        remote_lines,
        fromfile=f"local: {conflict.local_path}",
        tofile=f"remote: {conflict.wiki_page}",
    )
    diff_text = "".join(diff)
    if diff_text:
        lines.append(diff_text.rstrip())
    else:
        lines.append("(no textual differences)")
    lines.append("")

    # Merge info
    if conflict.merged_content is not None:
        lines.append("--- Merge result preview ---")
        # Show first 20 lines of merged content
        merge_lines = conflict.merged_content.splitlines()
        preview = merge_lines[:20]
        for ml in preview:
            lines.append(f"  {ml}")
        if len(merge_lines) > 20:
            lines.append(f"  ... ({len(merge_lines) - 20} more lines)")
        lines.append("")

    if conflict.has_markers:
        lines.append(
            "WARNING: Merged content contains conflict markers."
        )

    return "\n".join(lines).rstrip()


# ------------------------------------------------------------------
# JSON output
# ------------------------------------------------------------------


def report_to_json(report: SyncReport) -> dict:
    """Convert a sync report to a structured dict for JSON serialisation.

    Suitable for MCP ``structuredContent`` output.

    Args:
        report: The sync report.

    Returns:
        Dict with profile info, counts, and per-result details.
    """
    results_list = []
    for r in report.results:
        entry: dict = {
            "local_path": r.local_path,
            "wiki_page": r.wiki_page,
            "action": r.action.value,
            "success": r.success,
        }
        if r.error:
            entry["error"] = r.error
        results_list.append(entry)

    return {
        "profile_name": report.profile_name,
        "dry_run": report.dry_run,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
        "counts": {
            "total": len(report.results),
            "pushed": len(report.updated_remote),
            "pulled": len(report.updated_local),
            "created_remote": len(report.created_remote),
            "created_local": len(report.created_local),
            "conflicts": len(report.conflicts),
            "errors": len(report.errors),
            "skipped": len(report.skipped),
        },
        "results": results_list,
    }
