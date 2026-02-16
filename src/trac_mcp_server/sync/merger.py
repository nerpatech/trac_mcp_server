"""Three-way merge and diff utilities for the sync engine.

Uses the ``merge3`` library for three-way merging (the same algorithm used
by Bazaar/Breezy) and ``difflib`` for unified diff generation.

Key design choices:

* Merge operates on **Markdown content** (the common intermediate format),
  never on raw TracWiki.  Conversion happens before/after merge.
* Conflict markers follow Git convention with custom labels:
  ``<<<<<<< LOCAL``, ``=======``, ``>>>>>>> REMOTE``.
* ``generate_diff`` is a thin wrapper around ``difflib.unified_diff``
  for display purposes (sync reports, conflict review).
"""

from __future__ import annotations

import difflib

from merge3 import Merge3


def attempt_merge(
    base_content: str,
    local_content: str,
    remote_content: str,
) -> tuple[str, bool]:
    """Perform a three-way merge of local and remote changes against a base.

    Args:
        base_content: The common ancestor (archive) content.
        local_content: The current local file content.
        remote_content: The current remote wiki content.

    Returns:
        A tuple of ``(merged_text, has_conflicts)`` where *merged_text* is
        the result of the merge (possibly containing conflict markers) and
        *has_conflicts* is ``True`` if conflict markers are present.
    """
    base_lines = base_content.splitlines(True)
    local_lines = local_content.splitlines(True)
    remote_lines = remote_content.splitlines(True)

    m3 = Merge3(base_lines, local_lines, remote_lines)

    merged_lines = list(
        m3.merge_lines(
            name_a="LOCAL",
            name_b="REMOTE",
            start_marker="<<<<<<< LOCAL",
            mid_marker="=======",
            end_marker=">>>>>>> REMOTE",
        )
    )

    merged_text = "".join(merged_lines)
    has_conflicts = "<<<<<<< LOCAL" in merged_text

    return merged_text, has_conflicts


def generate_diff(
    old_content: str,
    new_content: str,
    label_old: str = "old",
    label_new: str = "new",
) -> str:
    """Generate a unified diff between two strings.

    Args:
        old_content: The original content.
        new_content: The modified content.
        label_old: Label for the old file in the diff header.
        label_new: Label for the new file in the diff header.

    Returns:
        A unified diff string.  Empty string if the contents are identical.
    """
    old_lines = old_content.splitlines(True)
    new_lines = new_content.splitlines(True)

    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=label_old,
        tofile=label_new,
    )

    return "".join(diff_lines)
