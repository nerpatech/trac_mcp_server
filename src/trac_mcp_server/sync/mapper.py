"""Config-driven path mapper for bidirectional document sync.

Translates between local file paths (relative to the sync profile source)
and wiki page names using the ordered mapping rules defined in a
``SyncProfileConfig``.

Mapping resolution:

1. **Exclude check** -- if the path matches any exclude glob, it is skipped.
2. **Ordered mappings** -- first matching ``SyncMappingRule`` wins.
3. **Namespace template** -- ``{parent}``, ``{stem}``, ``{path}`` are
   resolved from the local path.
4. **Name rules** -- optional per-filename overrides in the mapping.
5. **Flat fallback** -- if no mapping matches, ``destination/stem`` is used.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

from trac_mcp_server.config_schema import SyncProfileConfig


class PathMapper:
    """Map local file paths to wiki page names and vice-versa.

    Args:
        profile: The sync profile configuration containing source,
            destination, mappings, and exclude rules.
    """

    def __init__(self, profile: SyncProfileConfig) -> None:
        self._profile = profile

    # ------------------------------------------------------------------
    # Local -> Wiki
    # ------------------------------------------------------------------

    def map_local_to_wiki(self, local_path: str) -> str | None:
        """Map a local file path (relative to source) to a wiki page name.

        Args:
            local_path: File path relative to the profile source directory
                (e.g. ``"phases/41-sync/41-01-PLAN.md"``).

        Returns:
            Wiki page name, or ``None`` if the path is excluded.
        """
        # Check excludes first
        for pattern in self._profile.exclude:
            if fnmatch.fnmatch(local_path, pattern):
                return None

        p = PurePosixPath(local_path)

        # Try ordered mappings (first match wins)
        for mapping in self._profile.mappings:
            if fnmatch.fnmatch(local_path, mapping.pattern):
                namespace = self._resolve_namespace(
                    mapping.namespace, p
                )
                page_name = self._resolve_page_name(
                    p, mapping.name_rules
                )
                raw = f"{self._profile.destination}/{namespace}/{page_name}"
                return self._clean_wiki_path(raw)

        # Flat fallback: destination/stem
        stem = p.stem if p.suffix == ".md" else p.name
        raw = f"{self._profile.destination}/{stem}"
        return self._clean_wiki_path(raw)

    # ------------------------------------------------------------------
    # Wiki -> Local (best-effort reverse)
    # ------------------------------------------------------------------

    def map_wiki_to_local(self, wiki_page: str) -> str | None:
        """Best-effort reverse mapping from wiki page name to local path.

        This is inherently lossy because multiple local paths could map to
        the same wiki page.  For reliable reverse lookups, store the
        canonical mapping in sync state.

        Args:
            wiki_page: Full wiki page name (e.g.
                ``"Planning/Phases/41-sync/Plan01"``).

        Returns:
            Guessed local file path (with ``.md`` extension), or ``None``
            if the wiki page does not start with the destination prefix.
        """
        dest = self._profile.destination.rstrip("/")
        if not wiki_page.startswith(dest):
            return None

        # Strip destination prefix
        remainder = wiki_page[len(dest) :].lstrip("/")
        if not remainder:
            return None

        # Best-effort: add .md extension
        return f"{remainder}.md"

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_local_files(self, source_root: Path) -> list[str]:
        """Scan *source_root* for files matching mapping patterns.

        Files matching any exclude pattern are filtered out.

        Args:
            source_root: Absolute path to the sync source directory.

        Returns:
            Sorted list of relative paths (POSIX-style forward slashes).
        """
        if not source_root.is_dir():
            return []

        # Collect all .md files under source_root
        candidates: list[str] = []
        for path in sorted(source_root.rglob("*.md")):
            if path.is_file():
                rel = str(path.relative_to(source_root))
                # Normalise to forward slashes for consistent matching
                rel = rel.replace("\\", "/")
                candidates.append(rel)

        # If mappings exist, filter to those matching at least one pattern
        if self._profile.mappings:
            matching: list[str] = []
            for rel in candidates:
                for mapping in self._profile.mappings:
                    if fnmatch.fnmatch(rel, mapping.pattern):
                        matching.append(rel)
                        break
            candidates = matching

        # Apply excludes
        result: list[str] = []
        for rel in candidates:
            excluded = False
            for pattern in self._profile.exclude:
                if fnmatch.fnmatch(rel, pattern):
                    excluded = True
                    break
            if not excluded:
                result.append(rel)

        return sorted(result)

    # ------------------------------------------------------------------
    # Pair building
    # ------------------------------------------------------------------

    def build_pairs(
        self, source_root: Path, wiki_pages: list[str]
    ) -> list[tuple[str, str]]:
        """Build all ``(local_path, wiki_page)`` pairs.

        Combines locally-discovered files with remotely-known wiki pages
        to produce a deduplicated list of sync pairs.

        Args:
            source_root: Absolute path to the sync source directory.
            wiki_pages: List of wiki page names known to exist remotely.

        Returns:
            Sorted, deduplicated list of ``(local_path, wiki_page)`` tuples.
        """
        seen: dict[str, str] = {}  # local_path -> wiki_page

        # Local files -> wiki pages
        for local_path in self.discover_local_files(source_root):
            wiki_page = self.map_local_to_wiki(local_path)
            if wiki_page is not None:
                seen[local_path] = wiki_page

        # Remote wiki pages -> local paths (for new remote pages)
        for wiki_page in wiki_pages:
            local_path = self.map_wiki_to_local(wiki_page)
            if local_path is not None and local_path not in seen:
                seen[local_path] = wiki_page

        return sorted(seen.items())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_namespace(template: str, path: PurePosixPath) -> str:
        """Resolve namespace template variables.

        Supported variables:
        - ``{parent}`` -- parent directory name
        - ``{stem}`` -- filename without ``.md`` extension
        - ``{path}`` -- full relative path without extension
        """
        parent = path.parent.name if path.parent.name else ""
        stem = path.stem if path.suffix == ".md" else path.name
        # Full path without extension
        if path.suffix == ".md":
            path_no_ext = str(path.with_suffix(""))
        else:
            path_no_ext = str(path)

        result = template.replace("{parent}", parent)
        result = result.replace("{stem}", stem)
        result = result.replace("{path}", path_no_ext)
        return result

    @staticmethod
    def _resolve_page_name(
        path: PurePosixPath,
        name_rules: dict[str, str] | None,
    ) -> str:
        """Resolve the wiki page name for a file.

        If *name_rules* is provided, check if the filename matches any
        rule pattern; if so, use the replacement.  Otherwise, use the
        stem (filename without ``.md``).
        """
        filename = path.name
        if name_rules:
            for pattern, replacement in name_rules.items():
                if fnmatch.fnmatch(filename, pattern):
                    return replacement

        return path.stem if path.suffix == ".md" else path.name

    @staticmethod
    def _clean_wiki_path(raw: str) -> str:
        """Clean up a raw wiki path.

        Removes double slashes and trailing slashes.
        """
        # Collapse double (or more) slashes
        while "//" in raw:
            raw = raw.replace("//", "/")
        return raw.rstrip("/")
