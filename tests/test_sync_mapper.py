"""Tests for the config-driven path mapper.

Covers:
- Simple flat mapping (no mappings configured)
- Pattern matching with namespace templates ({parent}, {stem}, {path})
- name_rules override default stem
- First-match-wins for overlapping patterns
- Exclude patterns prevent mapping
- discover_local_files finds .md files matching patterns
- build_pairs combines local and remote sources
- map_wiki_to_local reverse mapping
"""

from __future__ import annotations

from pathlib import Path

from trac_mcp_server.config_schema import (
    SyncMappingRule,
    SyncProfileConfig,
)
from trac_mcp_server.sync.mapper import PathMapper


def _make_profile(
    source: str = ".planning/",
    destination: str = "Planning",
    mappings: list[SyncMappingRule] | None = None,
    exclude: list[str] | None = None,
) -> SyncProfileConfig:
    """Helper to create a SyncProfileConfig with sensible defaults."""
    kwargs: dict = {
        "source": source,
        "destination": destination,
    }
    if mappings is not None:
        kwargs["mappings"] = mappings
    if exclude is not None:
        kwargs["exclude"] = exclude
    return SyncProfileConfig(**kwargs)


# ---------------------------------------------------------------------------
# Flat mapping (no mappings configured)
# ---------------------------------------------------------------------------


class TestFlatMapping:
    """When no mappings are configured, files map flat to destination/stem."""

    def test_simple_file(self):
        """A single .md file maps to destination/stem."""
        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("README.md")
        assert result == "Wiki/README"

    def test_nested_file_uses_stem_only(self):
        """Nested files still use stem for flat mapping."""
        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("docs/guide/intro.md")
        assert result == "Wiki/intro"

    def test_no_double_slashes(self):
        """Destination with trailing slash doesn't cause double slashes."""
        profile = _make_profile(destination="Wiki/")
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("README.md")
        assert "//" not in result


# ---------------------------------------------------------------------------
# Pattern matching with namespace templates
# ---------------------------------------------------------------------------


class TestNamespaceTemplates:
    """Test namespace template resolution: {parent}, {stem}, {path}."""

    def test_parent_template(self):
        """{parent} resolves to the parent directory name."""
        profile = _make_profile(
            destination="Planning",
            mappings=[
                SyncMappingRule(
                    pattern="phases/*/*.md",
                    namespace="Phases/{parent}",
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki(
            "phases/41-configurable-document-sync/41-01-PLAN.md"
        )
        assert (
            result
            == "Planning/Phases/41-configurable-document-sync/41-01-PLAN"
        )

    def test_stem_template(self):
        """{stem} resolves to the filename without .md extension."""
        profile = _make_profile(
            destination="Docs",
            mappings=[
                SyncMappingRule(
                    pattern="*.md",
                    namespace="{stem}",
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("README.md")
        # destination/{stem}/{stem} but page name is also stem
        # namespace = "README", page = "README"
        assert result == "Docs/README/README"

    def test_path_template(self):
        """{path} resolves to the full relative path without extension."""
        profile = _make_profile(
            destination="Wiki",
            mappings=[
                SyncMappingRule(
                    pattern="docs/**/*.md",
                    namespace="{path}",
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("docs/guide/intro.md")
        # namespace = "docs/guide/intro", page = "intro"
        assert result == "Wiki/docs/guide/intro/intro"

    def test_parent_template_with_trailing_slash(self):
        """Namespace template with trailing slash is cleaned up."""
        profile = _make_profile(
            destination="Planning",
            mappings=[
                SyncMappingRule(
                    pattern="phases/*/*.md",
                    namespace="Phases/{parent}/",
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki(
            "phases/41-sync/41-01-PLAN.md"
        )
        assert result == "Planning/Phases/41-sync/41-01-PLAN"


# ---------------------------------------------------------------------------
# Name rules
# ---------------------------------------------------------------------------


class TestNameRules:
    """Test that name_rules override the default stem."""

    def test_name_rule_overrides_stem(self):
        """A matching name_rule replaces the default stem."""
        profile = _make_profile(
            destination="Planning",
            mappings=[
                SyncMappingRule(
                    pattern="*.md",
                    namespace="",
                    name_rules={"README.md": "Home"},
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("README.md")
        assert result == "Planning/Home"

    def test_name_rule_no_match_uses_stem(self):
        """When no name_rule matches, the stem is used."""
        profile = _make_profile(
            destination="Planning",
            mappings=[
                SyncMappingRule(
                    pattern="*.md",
                    namespace="",
                    name_rules={"README.md": "Home"},
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("CHANGELOG.md")
        assert result == "Planning/CHANGELOG"

    def test_name_rule_glob_pattern(self):
        """name_rules can use glob patterns for matching."""
        profile = _make_profile(
            destination="Wiki",
            mappings=[
                SyncMappingRule(
                    pattern="phases/*/*.md",
                    namespace="Phases/{parent}",
                    name_rules={
                        "*-PLAN.md": "Plan",
                        "*-SUMMARY.md": "Summary",
                    },
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki(
            "phases/41-sync/41-01-PLAN.md"
        )
        assert result == "Wiki/Phases/41-sync/Plan"

        result2 = mapper.map_local_to_wiki(
            "phases/41-sync/41-01-SUMMARY.md"
        )
        assert result2 == "Wiki/Phases/41-sync/Summary"


# ---------------------------------------------------------------------------
# First-match-wins
# ---------------------------------------------------------------------------


class TestFirstMatchWins:
    """Test that overlapping patterns use first-match-wins."""

    def test_first_mapping_wins(self):
        """When multiple mappings match, the first one is used."""
        profile = _make_profile(
            destination="Wiki",
            mappings=[
                SyncMappingRule(
                    pattern="phases/*/*.md",
                    namespace="Phases/{parent}",
                ),
                SyncMappingRule(
                    pattern="**/*.md",
                    namespace="Catch-All",
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki(
            "phases/41-sync/41-01-PLAN.md"
        )
        # Should match first mapping, not second
        assert "Phases/41-sync" in result
        assert "Catch-All" not in result

    def test_second_mapping_if_first_doesnt_match(self):
        """Second mapping is used when first doesn't match."""
        profile = _make_profile(
            destination="Wiki",
            mappings=[
                SyncMappingRule(
                    pattern="phases/*/*.md",
                    namespace="Phases/{parent}",
                ),
                SyncMappingRule(
                    pattern="*.md",
                    namespace="TopLevel",
                ),
            ],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("README.md")
        assert result == "Wiki/TopLevel/README"


# ---------------------------------------------------------------------------
# Exclude patterns
# ---------------------------------------------------------------------------


class TestExcludePatterns:
    """Test that exclude patterns prevent mapping."""

    def test_excluded_file_returns_none(self):
        """Files matching exclude patterns return None."""
        profile = _make_profile(
            destination="Wiki",
            exclude=["*.tmp", "drafts/*"],
        )
        mapper = PathMapper(profile)
        assert mapper.map_local_to_wiki("notes.tmp") is None
        assert mapper.map_local_to_wiki("drafts/wip.md") is None

    def test_non_excluded_file_maps(self):
        """Files not matching exclude patterns map normally."""
        profile = _make_profile(
            destination="Wiki",
            exclude=["*.tmp"],
        )
        mapper = PathMapper(profile)
        result = mapper.map_local_to_wiki("README.md")
        assert result is not None
        assert result == "Wiki/README"


# ---------------------------------------------------------------------------
# discover_local_files
# ---------------------------------------------------------------------------


class TestDiscoverLocalFiles:
    """Test discover_local_files finds .md files matching patterns."""

    def test_discovers_md_files(self, tmp_path: Path):
        """Discovers .md files in subdirectories."""
        # Create sample file structure
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("guide")
        (tmp_path / "docs" / "api.md").write_text("api")
        (tmp_path / "readme.md").write_text("readme")
        (tmp_path / "data.json").write_text("{}")  # Not .md

        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        files = mapper.discover_local_files(tmp_path)

        assert "readme.md" in files
        assert "docs/guide.md" in files
        assert "docs/api.md" in files
        assert "data.json" not in files

    def test_filters_by_mapping_patterns(self, tmp_path: Path):
        """Only files matching mapping patterns are returned."""
        (tmp_path / "phases").mkdir()
        (tmp_path / "phases" / "plan.md").write_text("plan")
        (tmp_path / "other.md").write_text("other")

        profile = _make_profile(
            destination="Wiki",
            mappings=[
                SyncMappingRule(
                    pattern="phases/*.md",
                    namespace="Phases",
                ),
            ],
        )
        mapper = PathMapper(profile)
        files = mapper.discover_local_files(tmp_path)

        assert "phases/plan.md" in files
        assert "other.md" not in files

    def test_excludes_patterns(self, tmp_path: Path):
        """Excluded patterns are filtered out."""
        (tmp_path / "readme.md").write_text("readme")
        (tmp_path / "draft.md").write_text("draft")

        profile = _make_profile(
            destination="Wiki",
            exclude=["draft.md"],
        )
        mapper = PathMapper(profile)
        files = mapper.discover_local_files(tmp_path)

        assert "readme.md" in files
        assert "draft.md" not in files

    def test_empty_directory(self, tmp_path: Path):
        """Empty directory returns empty list."""
        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        files = mapper.discover_local_files(tmp_path)
        assert files == []

    def test_nonexistent_directory(self, tmp_path: Path):
        """Non-existent directory returns empty list."""
        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        files = mapper.discover_local_files(tmp_path / "nonexistent")
        assert files == []


# ---------------------------------------------------------------------------
# build_pairs
# ---------------------------------------------------------------------------


class TestBuildPairs:
    """Test build_pairs combines local and remote sources."""

    def test_local_files_produce_pairs(self, tmp_path: Path):
        """Local files are paired with their wiki page names."""
        (tmp_path / "readme.md").write_text("readme")
        (tmp_path / "guide.md").write_text("guide")

        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        pairs = mapper.build_pairs(tmp_path, wiki_pages=[])

        local_paths = [p[0] for p in pairs]
        wiki_pages = [p[1] for p in pairs]
        assert "readme.md" in local_paths
        assert "guide.md" in local_paths
        assert "Wiki/readme" in wiki_pages
        assert "Wiki/guide" in wiki_pages

    def test_remote_pages_add_pairs(self, tmp_path: Path):
        """Remote wiki pages not locally present produce new pairs."""
        (tmp_path / "readme.md").write_text("readme")

        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        pairs = mapper.build_pairs(
            tmp_path,
            wiki_pages=["Wiki/NewPage"],
        )

        local_paths = [p[0] for p in pairs]
        assert "NewPage.md" in local_paths
        assert "readme.md" in local_paths

    def test_deduplication(self, tmp_path: Path):
        """Local files and matching remote pages are deduplicated."""
        (tmp_path / "readme.md").write_text("readme")

        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        pairs = mapper.build_pairs(
            tmp_path,
            wiki_pages=["Wiki/readme"],  # Same page as local readme.md
        )

        # readme.md should appear only once (from local discovery)
        local_paths = [p[0] for p in pairs]
        assert local_paths.count("readme.md") == 1

    def test_pairs_are_sorted(self, tmp_path: Path):
        """Returned pairs are sorted by local path."""
        (tmp_path / "z.md").write_text("z")
        (tmp_path / "a.md").write_text("a")
        (tmp_path / "m.md").write_text("m")

        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        pairs = mapper.build_pairs(tmp_path, wiki_pages=[])

        local_paths = [p[0] for p in pairs]
        assert local_paths == sorted(local_paths)


# ---------------------------------------------------------------------------
# Reverse mapping: map_wiki_to_local
# ---------------------------------------------------------------------------


class TestMapWikiToLocal:
    """Test map_wiki_to_local reverse mapping."""

    def test_simple_reverse(self):
        """Simple wiki page reverses to local file path with .md."""
        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        result = mapper.map_wiki_to_local("Wiki/README")
        assert result == "README.md"

    def test_nested_reverse(self):
        """Nested wiki page reverses to nested local path."""
        profile = _make_profile(destination="Planning")
        mapper = PathMapper(profile)
        result = mapper.map_wiki_to_local(
            "Planning/Phases/41-sync/Plan"
        )
        assert result == "Phases/41-sync/Plan.md"

    def test_wrong_prefix_returns_none(self):
        """Wiki page without matching destination prefix returns None."""
        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        result = mapper.map_wiki_to_local("Other/Page")
        assert result is None

    def test_destination_only_returns_none(self):
        """Wiki page equal to destination prefix returns None."""
        profile = _make_profile(destination="Wiki")
        mapper = PathMapper(profile)
        result = mapper.map_wiki_to_local("Wiki")
        assert result is None

    def test_destination_with_trailing_slash(self):
        """Destination with trailing slash is handled correctly."""
        profile = _make_profile(destination="Wiki/")
        mapper = PathMapper(profile)
        result = mapper.map_wiki_to_local("Wiki/README")
        assert result == "README.md"
