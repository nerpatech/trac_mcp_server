"""Tests for sync/merger.py — three-way merge and diff utilities.

Covers:
- attempt_merge() with clean merges, conflicts, and edge cases
- generate_diff() with additions, removals, and no-change scenarios
"""

from trac_mcp_server.sync.merger import attempt_merge, generate_diff


# ---------------------------------------------------------------------------
# attempt_merge tests
# ---------------------------------------------------------------------------


class TestAttemptMerge:
    """Tests for attempt_merge()."""

    def test_clean_merge_both_sides(self):
        """Both sides add non-conflicting content — should merge cleanly."""
        base = "line1\nline2\n"
        local = "line1\nLOCAL\nline2\n"
        remote = "line1\nline2\nREMOTE\n"

        merged, has_conflicts = attempt_merge(base, local, remote)

        assert not has_conflicts
        assert "LOCAL" in merged
        assert "REMOTE" in merged

    def test_conflict_same_line(self):
        """Both sides modify the same content — should produce conflict markers."""
        base = "line1\n"
        local = "LOCAL change\n"
        remote = "REMOTE change\n"

        merged, has_conflicts = attempt_merge(base, local, remote)

        assert has_conflicts
        assert "<<<<<<< LOCAL" in merged
        assert "=======" in merged
        assert ">>>>>>> REMOTE" in merged

    def test_identical_content(self):
        """All three inputs identical — no merge needed."""
        content = "same\n"

        merged, has_conflicts = attempt_merge(content, content, content)

        assert not has_conflicts
        assert merged == content

    def test_local_only_change(self):
        """Only local differs — merged should be local content."""
        base = "old\n"
        local = "new\n"
        remote = "old\n"

        merged, has_conflicts = attempt_merge(base, local, remote)

        assert not has_conflicts
        assert merged == local

    def test_remote_only_change(self):
        """Only remote differs — merged should be remote content."""
        base = "old\n"
        local = "old\n"
        remote = "new\n"

        merged, has_conflicts = attempt_merge(base, local, remote)

        assert not has_conflicts
        assert merged == remote

    def test_empty_base(self):
        """Empty base with content on both sides — should handle gracefully."""
        base = ""
        local = "local content\n"
        remote = "remote content\n"

        merged, has_conflicts = attempt_merge(base, local, remote)

        # Both sides added everything from scratch — likely conflicts
        # The important thing is it doesn't crash
        assert isinstance(merged, str)
        assert isinstance(has_conflicts, bool)

    def test_multiline_non_overlapping_additions(self):
        """Both sides add different sections at different locations — clean merge."""
        base = "header\n\nmiddle\n\nfooter\n"
        local = "header\n\nlocal section\n\nmiddle\n\nfooter\n"
        remote = "header\n\nmiddle\n\nremote section\n\nfooter\n"

        merged, has_conflicts = attempt_merge(base, local, remote)

        assert not has_conflicts
        assert "local section" in merged
        assert "remote section" in merged

    def test_return_types(self):
        """Verify return types are (str, bool)."""
        merged, has_conflicts = attempt_merge("a", "b", "c")

        assert isinstance(merged, str)
        assert isinstance(has_conflicts, bool)

    def test_empty_all(self):
        """All empty strings — should return empty with no conflicts."""
        merged, has_conflicts = attempt_merge("", "", "")

        assert not has_conflicts
        assert merged == ""

    def test_conflict_markers_format(self):
        """Verify conflict markers use Git-style labels."""
        base = "original\n"
        local = "local version\n"
        remote = "remote version\n"

        merged, has_conflicts = attempt_merge(base, local, remote)

        assert has_conflicts
        assert "<<<<<<< LOCAL" in merged
        assert ">>>>>>> REMOTE" in merged


# ---------------------------------------------------------------------------
# generate_diff tests
# ---------------------------------------------------------------------------


class TestGenerateDiff:
    """Tests for generate_diff()."""

    def test_basic_diff(self):
        """Changed line shows removal and addition."""
        old = "line1\nline2\n"
        new = "line1\nchanged\n"

        diff = generate_diff(old, new)

        assert "---" in diff
        assert "+++" in diff
        assert "-line2" in diff
        assert "+changed" in diff

    def test_no_changes(self):
        """Identical content produces empty diff."""
        content = "same\n"

        diff = generate_diff(content, content)

        assert diff == ""

    def test_additions_only(self):
        """Added lines appear with + prefix."""
        old = "line1\n"
        new = "line1\nnew line\n"

        diff = generate_diff(old, new)

        assert "+new line" in diff

    def test_custom_labels(self):
        """Custom labels appear in diff header."""
        old = "old\n"
        new = "new\n"

        diff = generate_diff(old, new, label_old="before.md", label_new="after.md")

        assert "before.md" in diff
        assert "after.md" in diff

    def test_deletions_only(self):
        """Removed lines appear with - prefix."""
        old = "line1\nline2\n"
        new = "line1\n"

        diff = generate_diff(old, new)

        assert "-line2" in diff

    def test_default_labels(self):
        """Default labels are 'old' and 'new'."""
        diff = generate_diff("a\n", "b\n")

        assert "old" in diff
        assert "new" in diff
