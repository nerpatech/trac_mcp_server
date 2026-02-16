"""Tests for sync reporter formatting functions.

Covers:
- format_sync_report with various result combinations
- format_dry_run_preview formatting
- format_conflict_diff with diffs and merge info
- report_to_json structure and completeness
- Empty report (all skipped) produces concise output
"""

from __future__ import annotations

from trac_mcp_server.sync.models import (
    ConflictInfo,
    SyncAction,
    SyncReport,
    SyncResult,
)
from trac_mcp_server.sync.reporter import (
    format_conflict_diff,
    format_dry_run_preview,
    format_sync_report,
    report_to_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(
    results: list[SyncResult] | None = None,
    dry_run: bool = False,
    profile: str = "planning",
) -> SyncReport:
    """Build a SyncReport with sensible defaults."""
    return SyncReport(
        profile_name=profile,
        dry_run=dry_run,
        results=results or [],
        started_at="2026-02-07T10:00:00Z",
        completed_at="2026-02-07T10:01:00Z",
    )


def _result(
    action: SyncAction,
    local: str = "docs/readme.md",
    wiki: str = "Planning/Readme",
    success: bool = True,
    error: str | None = None,
) -> SyncResult:
    return SyncResult(
        local_path=local,
        wiki_page=wiki,
        action=action,
        success=success,
        error=error,
    )


# ---------------------------------------------------------------------------
# format_sync_report
# ---------------------------------------------------------------------------


class TestFormatSyncReport:
    """Tests for format_sync_report()."""

    def test_header_contains_profile_name(self):
        report = _make_report(profile="my-docs")
        text = format_sync_report(report)
        assert "my-docs" in text

    def test_dry_run_indicator_in_header(self):
        report = _make_report(dry_run=True)
        text = format_sync_report(report)
        assert "DRY RUN" in text

    def test_no_dry_run_indicator_when_false(self):
        report = _make_report(dry_run=False)
        text = format_sync_report(report)
        assert "DRY RUN" not in text

    def test_summary_line_counts(self):
        results = [
            _result(SyncAction.PUSH, "a.md", "Wiki/A"),
            _result(SyncAction.PUSH, "b.md", "Wiki/B"),
            _result(SyncAction.PULL, "c.md", "Wiki/C"),
            _result(SyncAction.CREATE_REMOTE, "d.md", "Wiki/D"),
            _result(SyncAction.CONFLICT, "e.md", "Wiki/E"),
            _result(SyncAction.SKIP, "f.md", "Wiki/F"),
        ]
        text = format_sync_report(_make_report(results))
        assert "6 files" in text
        assert "2 pushed" in text
        assert "1 pulled" in text
        assert "1 created" in text
        assert "1 conflicts" in text

    def test_pushed_section(self):
        results = [_result(SyncAction.PUSH, "a.md", "Wiki/A")]
        text = format_sync_report(_make_report(results))
        assert "Pushed to wiki:" in text
        assert "a.md -> Wiki/A" in text

    def test_pulled_section(self):
        results = [_result(SyncAction.PULL, "a.md", "Wiki/A")]
        text = format_sync_report(_make_report(results))
        assert "Pulled from wiki:" in text
        assert "Wiki/A -> a.md" in text

    def test_created_remote_section(self):
        results = [
            _result(SyncAction.CREATE_REMOTE, "new.md", "Wiki/New")
        ]
        text = format_sync_report(_make_report(results))
        assert "Created (remote):" in text
        assert "new.md -> Wiki/New" in text

    def test_created_local_section(self):
        results = [
            _result(SyncAction.CREATE_LOCAL, "new.md", "Wiki/New")
        ]
        text = format_sync_report(_make_report(results))
        assert "Created (local):" in text
        assert "Wiki/New -> new.md" in text

    def test_conflicts_section(self):
        results = [
            _result(
                SyncAction.CONFLICT,
                "e.md",
                "Wiki/E",
                error="both sides changed",
            )
        ]
        text = format_sync_report(_make_report(results))
        assert "Conflicts:" in text
        assert "e.md <-> Wiki/E: both sides changed" in text

    def test_errors_section(self):
        results = [
            _result(
                SyncAction.PUSH,
                "bad.md",
                "Wiki/Bad",
                success=False,
                error="connection refused",
            )
        ]
        text = format_sync_report(_make_report(results))
        assert "Errors:" in text
        assert "bad.md: connection refused" in text

    def test_skipped_shows_count_only(self):
        results = [
            _result(SyncAction.SKIP, f"skip{i}.md", f"Wiki/Skip{i}")
            for i in range(10)
        ]
        text = format_sync_report(_make_report(results))
        assert "Skipped: 10 files" in text
        # Should NOT list individual skipped paths
        assert "skip0.md" not in text.split("Skipped:")[1]

    def test_empty_report_concise(self):
        """Report with no results produces minimal output."""
        text = format_sync_report(_make_report())
        assert "0 files" in text
        # No action sections
        assert "Pushed to wiki:" not in text
        assert "Pulled from wiki:" not in text

    def test_timestamps_in_output(self):
        report = _make_report()
        text = format_sync_report(report)
        assert "2026-02-07T10:00:00Z" in text
        assert "2026-02-07T10:01:00Z" in text


# ---------------------------------------------------------------------------
# format_dry_run_preview
# ---------------------------------------------------------------------------


class TestFormatDryRunPreview:
    """Tests for format_dry_run_preview()."""

    def test_header(self):
        report = _make_report(dry_run=True)
        text = format_dry_run_preview(report)
        assert "DRY RUN" in text
        assert "No changes will be made" in text

    def test_groups_by_action(self):
        results = [
            _result(SyncAction.PUSH, "a.md", "Wiki/A"),
            _result(SyncAction.PUSH, "b.md", "Wiki/B"),
            _result(SyncAction.PULL, "c.md", "Wiki/C"),
        ]
        text = format_dry_run_preview(
            _make_report(results, dry_run=True)
        )
        assert "[PUSH]" in text
        assert "[PULL]" in text
        assert "a.md <-> Wiki/A" in text
        assert "c.md <-> Wiki/C" in text

    def test_skip_count_shown(self):
        results = [
            _result(SyncAction.SKIP, "x.md", "Wiki/X"),
            _result(SyncAction.SKIP, "y.md", "Wiki/Y"),
        ]
        text = format_dry_run_preview(
            _make_report(results, dry_run=True)
        )
        assert "Skipped: 2 files" in text

    def test_no_changes_needed(self):
        """When all results are SKIP, show 'No changes needed'."""
        results = [_result(SyncAction.SKIP, "x.md", "Wiki/X")]
        text = format_dry_run_preview(
            _make_report(results, dry_run=True)
        )
        assert "No changes needed" in text

    def test_create_remote_label(self):
        results = [
            _result(SyncAction.CREATE_REMOTE, "new.md", "Wiki/New")
        ]
        text = format_dry_run_preview(
            _make_report(results, dry_run=True)
        )
        assert "[CREATE REMOTE]" in text

    def test_conflict_label(self):
        results = [_result(SyncAction.CONFLICT, "e.md", "Wiki/E")]
        text = format_dry_run_preview(
            _make_report(results, dry_run=True)
        )
        assert "[CONFLICT]" in text

    def test_empty_dry_run(self):
        text = format_dry_run_preview(_make_report(dry_run=True))
        assert "No changes needed" in text


# ---------------------------------------------------------------------------
# format_conflict_diff
# ---------------------------------------------------------------------------


class TestFormatConflictDiff:
    """Tests for format_conflict_diff()."""

    def test_shows_paths(self):
        conflict = ConflictInfo(
            local_path="docs/intro.md",
            wiki_page="Planning/Intro",
            action=SyncAction.CONFLICT,
            local_content="hello\n",
            remote_content="world\n",
            has_markers=False,
        )
        text = format_conflict_diff(conflict)
        assert "docs/intro.md" in text
        assert "Planning/Intro" in text

    def test_unified_diff(self):
        conflict = ConflictInfo(
            local_path="a.md",
            wiki_page="Wiki/A",
            action=SyncAction.CONFLICT,
            local_content="line1\nline2\n",
            remote_content="line1\nchanged\n",
            has_markers=False,
        )
        text = format_conflict_diff(conflict)
        assert "---" in text  # diff header
        assert "+++" in text
        assert "-line2" in text
        assert "+changed" in text

    def test_merge_preview(self):
        conflict = ConflictInfo(
            local_path="a.md",
            wiki_page="Wiki/A",
            action=SyncAction.CONFLICT,
            local_content="local\n",
            remote_content="remote\n",
            merged_content="merged result here\n",
            has_markers=False,
        )
        text = format_conflict_diff(conflict)
        assert "Merge result preview" in text
        assert "merged result here" in text

    def test_merge_preview_truncated(self):
        """Long merge content is truncated to 20 lines."""
        long_content = "\n".join(f"line {i}" for i in range(30))
        conflict = ConflictInfo(
            local_path="a.md",
            wiki_page="Wiki/A",
            action=SyncAction.CONFLICT,
            local_content="local\n",
            remote_content="remote\n",
            merged_content=long_content,
            has_markers=False,
        )
        text = format_conflict_diff(conflict)
        assert "10 more lines" in text

    def test_has_markers_warning(self):
        conflict = ConflictInfo(
            local_path="a.md",
            wiki_page="Wiki/A",
            action=SyncAction.CONFLICT,
            local_content="local\n",
            remote_content="remote\n",
            has_markers=True,
        )
        text = format_conflict_diff(conflict)
        assert "conflict markers" in text

    def test_no_markers_no_warning(self):
        conflict = ConflictInfo(
            local_path="a.md",
            wiki_page="Wiki/A",
            action=SyncAction.CONFLICT,
            local_content="local\n",
            remote_content="remote\n",
            has_markers=False,
        )
        text = format_conflict_diff(conflict)
        assert "conflict markers" not in text

    def test_identical_content(self):
        """When local and remote are identical, show a no-diff message."""
        conflict = ConflictInfo(
            local_path="a.md",
            wiki_page="Wiki/A",
            action=SyncAction.CONFLICT,
            local_content="same\n",
            remote_content="same\n",
            has_markers=False,
        )
        text = format_conflict_diff(conflict)
        assert "no textual differences" in text


# ---------------------------------------------------------------------------
# report_to_json
# ---------------------------------------------------------------------------


class TestReportToJson:
    """Tests for report_to_json()."""

    def test_basic_structure(self):
        report = _make_report()
        data = report_to_json(report)
        assert data["profile_name"] == "planning"
        assert data["dry_run"] is False
        assert "started_at" in data
        assert "completed_at" in data
        assert "counts" in data
        assert "results" in data

    def test_counts_match(self):
        results = [
            _result(SyncAction.PUSH, "a.md", "Wiki/A"),
            _result(SyncAction.PULL, "b.md", "Wiki/B"),
            _result(SyncAction.SKIP, "c.md", "Wiki/C"),
            _result(SyncAction.CONFLICT, "d.md", "Wiki/D"),
        ]
        data = report_to_json(_make_report(results))
        assert data["counts"]["total"] == 4
        assert data["counts"]["pushed"] == 1
        assert data["counts"]["pulled"] == 1
        assert data["counts"]["skipped"] == 1
        assert data["counts"]["conflicts"] == 1

    def test_result_entries(self):
        results = [
            _result(SyncAction.PUSH, "a.md", "Wiki/A"),
            _result(
                SyncAction.PUSH,
                "b.md",
                "Wiki/B",
                success=False,
                error="fail",
            ),
        ]
        data = report_to_json(_make_report(results))
        assert len(data["results"]) == 2
        assert data["results"][0]["action"] == "push"
        assert data["results"][0]["success"] is True
        assert "error" not in data["results"][0]
        assert data["results"][1]["error"] == "fail"

    def test_empty_report_json(self):
        data = report_to_json(_make_report())
        assert data["counts"]["total"] == 0
        assert data["results"] == []

    def test_dry_run_flag(self):
        data = report_to_json(_make_report(dry_run=True))
        assert data["dry_run"] is True


# ---------------------------------------------------------------------------
# SyncReport property and summary() tests
# ---------------------------------------------------------------------------


class TestSyncReport:
    """Tests for SyncReport properties and summary()."""

    def test_created_local_filters_correctly(self):
        """created_local returns only CREATE_LOCAL results."""
        results = [
            _result(SyncAction.CREATE_LOCAL, "a.md", "Wiki/A"),
            _result(SyncAction.PUSH, "b.md", "Wiki/B"),
            _result(SyncAction.CREATE_LOCAL, "c.md", "Wiki/C"),
        ]
        report = _make_report(results)

        assert len(report.created_local) == 2
        for r in report.created_local:
            assert r.action == SyncAction.CREATE_LOCAL

    def test_created_remote_filters_correctly(self):
        """created_remote returns only CREATE_REMOTE results."""
        results = [
            _result(SyncAction.CREATE_REMOTE, "a.md", "Wiki/A"),
            _result(SyncAction.PULL, "b.md", "Wiki/B"),
        ]
        report = _make_report(results)

        assert len(report.created_remote) == 1
        assert report.created_remote[0].action == SyncAction.CREATE_REMOTE

    def test_updated_local_filters_pull(self):
        """updated_local returns only PULL results."""
        results = [
            _result(SyncAction.PULL, "a.md", "Wiki/A"),
            _result(SyncAction.PUSH, "b.md", "Wiki/B"),
            _result(SyncAction.PULL, "c.md", "Wiki/C"),
        ]
        report = _make_report(results)

        assert len(report.updated_local) == 2
        for r in report.updated_local:
            assert r.action == SyncAction.PULL

    def test_updated_remote_filters_push(self):
        """updated_remote returns only PUSH results."""
        results = [
            _result(SyncAction.PUSH, "a.md", "Wiki/A"),
            _result(SyncAction.PULL, "b.md", "Wiki/B"),
        ]
        report = _make_report(results)

        assert len(report.updated_remote) == 1
        assert report.updated_remote[0].action == SyncAction.PUSH

    def test_skipped_filters_correctly(self):
        """skipped returns only SKIP results."""
        results = [
            _result(SyncAction.SKIP, "a.md", "Wiki/A"),
            _result(SyncAction.PUSH, "b.md", "Wiki/B"),
            _result(SyncAction.SKIP, "c.md", "Wiki/C"),
        ]
        report = _make_report(results)

        assert len(report.skipped) == 2
        for r in report.skipped:
            assert r.action == SyncAction.SKIP

    def test_conflicts_filters_correctly(self):
        """conflicts returns only CONFLICT results."""
        results = [
            _result(SyncAction.CONFLICT, "a.md", "Wiki/A"),
            _result(SyncAction.PUSH, "b.md", "Wiki/B"),
        ]
        report = _make_report(results)

        assert len(report.conflicts) == 1
        assert report.conflicts[0].action == SyncAction.CONFLICT

    def test_errors_filters_by_success_false(self):
        """errors returns only results with success=False."""
        results = [
            _result(SyncAction.PUSH, "a.md", "Wiki/A", success=True),
            _result(
                SyncAction.PUSH,
                "b.md",
                "Wiki/B",
                success=False,
                error="timeout",
            ),
            _result(
                SyncAction.PULL,
                "c.md",
                "Wiki/C",
                success=False,
                error="auth",
            ),
        ]
        report = _make_report(results)

        assert len(report.errors) == 2
        for r in report.errors:
            assert r.success is False

    def test_summary_format(self):
        """summary() contains profile name and all count lines."""
        results = [
            _result(SyncAction.CREATE_LOCAL, "a.md", "Wiki/A"),
            _result(SyncAction.PUSH, "b.md", "Wiki/B"),
            _result(SyncAction.PULL, "c.md", "Wiki/C"),
            _result(SyncAction.SKIP, "d.md", "Wiki/D"),
            _result(SyncAction.CONFLICT, "e.md", "Wiki/E"),
        ]
        report = _make_report(results, profile="test-docs")

        text = report.summary()

        assert "test-docs" in text
        assert "Created local:" in text
        assert "Created remote:" in text
        assert "Updated local:" in text
        assert "Updated remote:" in text
        assert "Skipped:" in text
        assert "Conflicts:" in text
        assert "Errors:" in text
        assert "Total:" in text

    def test_empty_report_properties(self):
        """Empty results list — all properties return empty lists."""
        report = _make_report([])

        assert report.created_local == []
        assert report.created_remote == []
        assert report.updated_local == []
        assert report.updated_remote == []
        assert report.skipped == []
        assert report.conflicts == []
        assert report.errors == []

    def test_summary_dry_run_label(self):
        """dry_run=True shows '(dry run)' in summary output."""
        report = _make_report(dry_run=True)

        text = report.summary()

        assert "(dry run)" in text
