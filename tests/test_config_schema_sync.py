"""Tests for bidirectional sync fields on SyncProfileConfig and SyncMappingRule.

Validates the new direction, conflict_strategy, git_safety, mappings, exclude,
and state_dir fields added for configurable bidirectional document sync.
"""

import logging

import pytest
from pydantic import ValidationError

from trac_mcp_server.config_schema import (
    SyncMappingRule,
    SyncProfileConfig,
    UnifiedConfig,
    build_config,
)

# ---------------------------------------------------------------------------
# SyncMappingRule tests
# ---------------------------------------------------------------------------


class TestSyncMappingRule:
    """Tests for the SyncMappingRule model."""

    def test_basic_mapping_rule(self):
        """Basic mapping rule with pattern and namespace."""
        rule = SyncMappingRule(
            pattern="phases/*/*.md",
            namespace="Planning/Phases/{parent}/",
        )
        assert rule.pattern == "phases/*/*.md"
        assert rule.namespace == "Planning/Phases/{parent}/"
        assert rule.name_rules is None

    def test_mapping_rule_with_name_rules(self):
        """Mapping rule with name_rules override."""
        rule = SyncMappingRule(
            pattern="*.md",
            namespace="Docs/",
            name_rules={
                "README.md": "Home",
                "CHANGELOG.md": "ChangeLog",
            },
        )
        assert rule.name_rules == {
            "README.md": "Home",
            "CHANGELOG.md": "ChangeLog",
        }

    def test_mapping_rule_without_name_rules(self):
        """Mapping rule without name_rules defaults to None."""
        rule = SyncMappingRule(pattern="**/*.md", namespace="Wiki/")
        assert rule.name_rules is None

    def test_mapping_rule_frozen(self):
        """SyncMappingRule is frozen (immutable)."""
        rule = SyncMappingRule(pattern="*.md", namespace="Docs/")
        with pytest.raises(ValidationError):
            rule.pattern = "*.rst"

    def test_mapping_rule_pattern_required(self):
        """pattern is a required field."""
        with pytest.raises(ValidationError):
            SyncMappingRule(namespace="Docs/")  # type: ignore[call-arg]

    def test_mapping_rule_namespace_required(self):
        """namespace is a required field."""
        with pytest.raises(ValidationError):
            SyncMappingRule(pattern="*.md")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# SyncProfileConfig new fields tests
# ---------------------------------------------------------------------------


class TestSyncProfileConfigBidirectional:
    """Tests for the new bidirectional sync fields on SyncProfileConfig."""

    def test_default_values(self):
        """New fields have correct default values."""
        config = SyncProfileConfig(
            source=".planning/", destination="wiki"
        )
        assert config.direction == "bidirectional"
        assert config.conflict_strategy == "interactive"
        assert config.git_safety == "block"
        assert config.mappings == []
        assert config.exclude == []
        assert config.state_dir == ".trac_mcp"

    def test_existing_fields_unchanged(self):
        """Existing source, destination, format fields still work."""
        config = SyncProfileConfig(
            source=".planning/",
            destination="wiki",
            format="tracwiki",
        )
        assert config.source == ".planning/"
        assert config.destination == "wiki"
        assert config.format == "tracwiki"

    def test_valid_config_with_mappings(self):
        """Full config with mappings and all new fields."""
        config = SyncProfileConfig(
            source=".planning/",
            destination="wiki",
            format="tracwiki",
            direction="push",
            conflict_strategy="markers",
            git_safety="warn",
            mappings=[
                SyncMappingRule(
                    pattern="phases/*/*.md",
                    namespace="Planning/Phases/{parent}/",
                ),
                SyncMappingRule(
                    pattern="*.md",
                    namespace="Planning/",
                    name_rules={"README.md": "Home"},
                ),
            ],
            exclude=["*.tmp", ".git/**"],
            state_dir=".sync_state",
        )
        assert config.direction == "push"
        assert config.conflict_strategy == "markers"
        assert config.git_safety == "warn"
        assert len(config.mappings) == 2
        assert config.mappings[0].pattern == "phases/*/*.md"
        assert config.mappings[1].name_rules == {"README.md": "Home"}
        assert config.exclude == ["*.tmp", ".git/**"]
        assert config.state_dir == ".sync_state"

    def test_direction_accepts_push(self):
        """direction accepts 'push'."""
        config = SyncProfileConfig(
            source="src/", destination="wiki", direction="push"
        )
        assert config.direction == "push"

    def test_direction_accepts_pull(self):
        """direction accepts 'pull'."""
        config = SyncProfileConfig(
            source="src/", destination="wiki", direction="pull"
        )
        assert config.direction == "pull"

    def test_direction_accepts_bidirectional(self):
        """direction accepts 'bidirectional'."""
        config = SyncProfileConfig(
            source="src/", destination="wiki", direction="bidirectional"
        )
        assert config.direction == "bidirectional"

    def test_direction_rejects_invalid(self):
        """direction rejects invalid values."""
        with pytest.raises(ValidationError):
            SyncProfileConfig(
                source="src/",
                destination="wiki",
                direction="sync",  # type: ignore[arg-type]
            )

    def test_conflict_strategy_accepts_interactive(self):
        """conflict_strategy accepts 'interactive'."""
        config = SyncProfileConfig(
            source="src/",
            destination="wiki",
            conflict_strategy="interactive",
        )
        assert config.conflict_strategy == "interactive"

    def test_conflict_strategy_accepts_markers(self):
        """conflict_strategy accepts 'markers'."""
        config = SyncProfileConfig(
            source="src/",
            destination="wiki",
            conflict_strategy="markers",
        )
        assert config.conflict_strategy == "markers"

    def test_conflict_strategy_accepts_local_wins(self):
        """conflict_strategy accepts 'local-wins'."""
        config = SyncProfileConfig(
            source="src/",
            destination="wiki",
            conflict_strategy="local-wins",
        )
        assert config.conflict_strategy == "local-wins"

    def test_conflict_strategy_accepts_remote_wins(self):
        """conflict_strategy accepts 'remote-wins'."""
        config = SyncProfileConfig(
            source="src/",
            destination="wiki",
            conflict_strategy="remote-wins",
        )
        assert config.conflict_strategy == "remote-wins"

    def test_conflict_strategy_rejects_invalid(self):
        """conflict_strategy rejects invalid values."""
        with pytest.raises(ValidationError):
            SyncProfileConfig(
                source="src/",
                destination="wiki",
                conflict_strategy="auto-merge",  # type: ignore[arg-type]
            )

    def test_git_safety_accepts_block(self):
        """git_safety accepts 'block'."""
        config = SyncProfileConfig(
            source="src/", destination="wiki", git_safety="block"
        )
        assert config.git_safety == "block"

    def test_git_safety_accepts_warn(self):
        """git_safety accepts 'warn'."""
        config = SyncProfileConfig(
            source="src/", destination="wiki", git_safety="warn"
        )
        assert config.git_safety == "warn"

    def test_git_safety_accepts_none(self):
        """git_safety accepts 'none'."""
        config = SyncProfileConfig(
            source="src/", destination="wiki", git_safety="none"
        )
        assert config.git_safety == "none"

    def test_git_safety_rejects_invalid(self):
        """git_safety rejects invalid values."""
        with pytest.raises(ValidationError):
            SyncProfileConfig(
                source="src/",
                destination="wiki",
                git_safety="error",  # type: ignore[arg-type]
            )

    def test_frozen_immutability_new_fields(self):
        """New fields on SyncProfileConfig are frozen."""
        config = SyncProfileConfig(source="src/", destination="wiki")
        with pytest.raises(ValidationError):
            config.direction = "push"
        with pytest.raises(ValidationError):
            config.conflict_strategy = "markers"
        with pytest.raises(ValidationError):
            config.git_safety = "none"

    def test_empty_mappings_warning(self, caplog):
        """Empty mappings triggers a logger warning."""
        with caplog.at_level(
            logging.WARNING, logger="trac_mcp_server.config_schema"
        ):
            SyncProfileConfig(source=".planning/", destination="wiki")
        assert "no mappings" in caplog.text.lower()

    def test_non_empty_mappings_no_warning(self, caplog):
        """Non-empty mappings does not trigger a warning."""
        with caplog.at_level(
            logging.WARNING, logger="trac_mcp_server.config_schema"
        ):
            SyncProfileConfig(
                source=".planning/",
                destination="wiki",
                mappings=[
                    SyncMappingRule(pattern="*.md", namespace="Docs/"),
                ],
            )
        assert "no mappings" not in caplog.text.lower()

    def test_backward_compatible_minimal_config(self):
        """Existing minimal configs (source + destination only) still work."""
        config = SyncProfileConfig(
            source=".planning/", destination="wiki"
        )
        assert config.source == ".planning/"
        assert config.destination == "wiki"
        assert config.format == "auto"

    def test_unified_config_with_new_sync_fields(self):
        """UnifiedConfig with sync profile using new fields parses correctly."""
        config = UnifiedConfig(
            sync={
                "planning": SyncProfileConfig(
                    source=".planning/",
                    destination="wiki",
                    direction="push",
                    conflict_strategy="local-wins",
                    mappings=[
                        SyncMappingRule(
                            pattern="**/*.md", namespace="Planning/"
                        ),
                    ],
                ),
            }
        )
        profile = config.sync["planning"]
        assert profile.direction == "push"
        assert profile.conflict_strategy == "local-wins"
        assert len(profile.mappings) == 1

    def test_build_config_with_new_sync_fields(self):
        """build_config parses new sync fields from raw dict."""
        raw = {
            "sync": {
                "docs": {
                    "source": "docs/",
                    "destination": "wiki",
                    "direction": "bidirectional",
                    "conflict_strategy": "markers",
                    "git_safety": "warn",
                    "mappings": [
                        {
                            "pattern": "**/*.md",
                            "namespace": "Documentation/",
                        },
                    ],
                    "exclude": ["drafts/**"],
                    "state_dir": ".sync",
                },
            }
        }
        config = build_config(raw)
        profile = config.sync["docs"]
        assert profile.direction == "bidirectional"
        assert profile.conflict_strategy == "markers"
        assert profile.git_safety == "warn"
        assert len(profile.mappings) == 1
        assert profile.mappings[0].pattern == "**/*.md"
        assert profile.exclude == ["drafts/**"]
        assert profile.state_dir == ".sync"
