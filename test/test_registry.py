"""
Tests for registry validation and precedence rules.

Acceptance criteria for bead adc-5x30:
1. Scanner proposal does not clobber an existing agent-authored entry
2. Schema validation rejects a malformed entry with a clear message
3. Demo projects' entries carry every field the demo script needs
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from src.registry import (
    _merge, _validate_project_entry, _validate_registry,
    RegistryValidationError, _build_registry, REGISTRY_PATH
)


class TestRegistryPrecedence:
    """Tests that scanner proposals don't clobber agent-authored entries."""

    def test_yaml_takes_precedence_over_discovered(self):
        """YAML entries should override discovered entries on all fields."""
        discovered = {
            "test-project": {
                "description": "Auto-discovered description",
                "aliases": ["test", "auto"],
                "cluster": "auto-cluster",
                "namespace": "auto-ns",
                "repo_path": "/auto/path",
                "argocd_app": "auto-app",
                "intent_support": ["status"],
                "_discovered": True,
            }
        }

        from_yaml = {
            "test-project": {
                "description": "Agent-authored description",
                "aliases": ["test", "agent"],
                "cluster": "agent-cluster",
                "namespace": "agent-ns",
                "repo_path": "/agent/path",
                "argocd_app": "agent-app",
                "intent_support": ["status", "brainstorm", "task-profile"],
            }
        }

        merged = _merge(discovered, from_yaml)

        # All YAML values should win
        result = merged["test-project"]
        assert result["description"] == "Agent-authored description"
        assert result["cluster"] == "agent-cluster"
        assert result["namespace"] == "agent-ns"
        assert result["repo_path"] == "/agent/path"
        assert result["argocd_app"] == "agent-app"
        assert set(result["intent_support"]) == {"status", "brainstorm", "task-profile"}

        # Aliases should be merged (union of discovered and YAML)
        assert set(result["aliases"]) == {"test", "auto", "agent"}

    def test_discovered_only_entry_preserved(self):
        """Entries only in discovery should be preserved."""
        discovered = {
            "new-project": {
                "description": "New discovered project",
                "aliases": ["new"],
                "cluster": None,
                "namespace": None,
                "repo_path": "/new/path",
                "argocd_app": "new-app",
                "intent_support": ["status"],
                "_discovered": True,
            }
        }

        from_yaml = {}

        merged = _merge(discovered, from_yaml)

        assert "new-project" in merged
        assert merged["new-project"]["description"] == "New discovered project"

    def test_agent_authored_entry_without_discovery(self):
        """Agent-authored entries should exist even without discovery."""
        discovered = {}

        from_yaml = {
            "agent-project": {
                "description": "Pure agent entry",
                "aliases": ["agent"],
                "cluster": "production",
                "namespace": "agent-ns",
                "repo_path": "/agent/path",
                "argocd_app": "agent-app",
                "intent_support": ["status", "task-profile"],
            }
        }

        merged = _merge(discovered, from_yaml)

        assert "agent-project" in merged
        assert merged["agent-project"]["description"] == "Pure agent entry"


class TestRegistryValidation:
    """Tests that schema validation rejects malformed entries with clear messages."""

    def test_valid_entry_passes_validation(self):
        """A complete, valid entry should pass validation."""
        entry = {
            "description": "Test project",
            "aliases": ["test", "demo"],
            "cluster": "test-cluster",
            "namespace": "test-ns",
            "repo_path": "/test/path",
            "argocd_app": "test-app",  # Optional but included
            "intent_support": ["status", "brainstorm", "task-profile"],
        }

        errors = _validate_project_entry("test-project", entry)
        assert errors == []

    def test_missing_required_field(self):
        """Missing required fields should produce clear error messages."""
        entry = {
            "description": "Test project",
            "aliases": ["test"],
            # Missing intent_support (the only truly required field besides description and aliases)
            # cluster, namespace, repo_path, argocd_app are optional
        }

        errors = _validate_project_entry("test-project", entry)
        assert len(errors) == 1
        assert any("intent_support" in e for e in errors)

    def test_wrong_field_type(self):
        """Wrong types should produce clear error messages."""
        entry = {
            "description": "Test project",
            "aliases": "not-a-list",  # Should be list
            "cluster": "test-cluster",
            "namespace": "test-ns",
            "repo_path": "/test/path",
            "argocd_app": "test-app",
            "intent_support": ["status"],
        }

        errors = _validate_project_entry("test-project", entry)
        assert len(errors) == 1
        assert "aliases" in errors[0]
        assert "list" in errors[0]

    def test_unknown_intent_type(self):
        """Unknown intent types should be flagged."""
        entry = {
            "description": "Test project",
            "aliases": ["test"],
            "cluster": "test-cluster",
            "namespace": "test-ns",
            "repo_path": "/test/path",
            "argocd_app": "test-app",
            "intent_support": ["status", "fake-intent"],  # fake-intent is unknown
        }

        errors = _validate_project_entry("test-project", entry)
        assert len(errors) == 1
        assert "fake-intent" in errors[0]
        assert "intent_support" in errors[0]

    def test_invalid_sla_hours(self):
        """Invalid sla_hours values should be flagged."""
        entry = {
            "description": "Test project",
            "aliases": ["test"],
            "cluster": "test-cluster",
            "namespace": "test-ns",
            "repo_path": "/test/path",
            "argocd_app": "test-app",
            "intent_support": ["status"],
            "sla_hours": "not-a-number",  # Should be number or null
        }

        errors = _validate_project_entry("test-project", entry)
        assert len(errors) == 1
        assert "sla_hours" in errors[0]

    def test_negative_sla_hours(self):
        """Negative sla_hours should be flagged."""
        entry = {
            "description": "Test project",
            "aliases": ["test"],
            "cluster": "test-cluster",
            "namespace": "test-ns",
            "repo_path": "/test/path",
            "argocd_app": "test-app",
            "intent_support": ["status"],
            "sla_hours": -5,  # Should be positive
        }

        errors = _validate_project_entry("test-project", entry)
        assert len(errors) == 1
        assert "sla_hours" in errors[0]
        assert "positive" in errors[0]

    def test_null_allowed_for_optional_fields(self):
        """null should be allowed for cluster, namespace, repo_path."""
        entry = {
            "description": "Local-only project",
            "aliases": ["local"],
            "cluster": None,
            "namespace": None,
            "repo_path": None,
            "argocd_app": "local-app",
            "intent_support": ["status"],
        }

        errors = _validate_project_entry("local-project", entry)
        assert errors == []

    def test_full_registry_validation(self):
        """Test full registry validation with multiple errors."""
        registry = {
            "projects": {
                "good-project": {
                    "description": "Valid project",
                    "aliases": ["good"],
                    "cluster": "test-cluster",
                    "namespace": "test-ns",
                    "repo_path": "/test/path",
                    "argocd_app": "good-app",
                    "intent_support": ["status"],
                },
                "bad-project": {
                    "description": "Invalid project",
                    # Missing many required fields
                },
            }
        }

        with pytest.raises(RegistryValidationError) as exc_info:
            _validate_registry(registry)

        errors = exc_info.value.errors
        assert len(errors) > 0
        assert any("bad-project" in e for e in errors)

    def test_empty_aliases_list(self):
        """Empty aliases in list should be flagged."""
        entry = {
            "description": "Test project",
            "aliases": ["test", "", "  ", "demo"],  # Empty strings
            "cluster": "test-cluster",
            "namespace": "test-ns",
            "repo_path": "/test/path",
            "argocd_app": "test-app",
            "intent_support": ["status"],
        }

        errors = _validate_project_entry("test-project", entry)
        assert len(errors) == 2  # Two empty aliases


class TestDemoProjectEntries:
    """Verify that demo projects carry all required fields."""

    def test_whisper_stt_entry_complete(self):
        """whisper-stt entry should have all fields needed for demo step 5."""
        # Load the actual registry
        registry = _build_registry()
        whisper = registry["projects"].get("whisper-stt")

        assert whisper is not None, "whisper-stt must exist in registry"

        # Check all required fields
        assert "description" in whisper
        assert "aliases" in whisper
        assert "cluster" in whisper
        assert "namespace" in whisper
        assert "repo_path" in whisper
        assert "argocd_app" in whisper
        assert "intent_support" in whisper

        # Demo step 5 requires task-profile support
        assert "task-profile" in whisper["intent_support"], \
            "whisper-stt must support task-profile for demo step 5"

        # Verify required demo intents
        for intent in ["status", "brainstorm", "lookup"]:
            assert intent in whisper["intent_support"], \
                f"whisper-stt must support {intent} for demo"

        # Check cluster is set (for ArgoCD resolution)
        assert whisper["cluster"] is not None, \
            "whisper-stt must have cluster set for ArgoCD resolution"

    def test_pbx_web_entry_complete(self):
        """pbx-web entry should have all fields needed for demo steps."""
        registry = _build_registry()
        pbx = registry["projects"].get("pbx-web")

        assert pbx is not None, "pbx-web must exist in registry"

        # Check all required fields
        assert "description" in pbx
        assert "aliases" in pbx
        assert "cluster" in pbx
        assert "namespace" in pbx
        assert "repo_path" in pbx
        assert "argocd_app" in pbx
        assert "intent_support" in pbx

        # Demo step 5 requires task-profile support
        assert "task-profile" in pbx["intent_support"], \
            "pbx-web must support task-profile for demo step 5"

        # Verify required demo intents
        for intent in ["status", "brainstorm", "lookup"]:
            assert intent in pbx["intent_support"], \
                f"pbx-web must support {intent} for demo"

        # Check cluster is set (for ArgoCD resolution)
        assert pbx["cluster"] is not None, \
            "pbx-web must have cluster set for ArgoCD resolution"

    def test_both_demo_projects_use_ardenone_cluster(self):
        """Both demo projects should be on ardenone-cluster for ArgoCD resolution."""
        registry = _build_registry()

        whisper = registry["projects"].get("whisper-stt")
        pbx = registry["projects"].get("pbx-web")

        # Both should use ardenone-cluster (per HUMAN decision bead adc-359d)
        assert whisper["cluster"] == "ardenone-cluster"
        assert pbx["cluster"] == "ardenone-cluster"


class TestRegistryFileValidation:
    """Test that the actual registry file validates successfully."""

    def test_actual_registry_validates(self):
        """The actual config/registry.yaml should pass validation."""
        # This should not raise any errors
        registry = _build_registry()
        assert registry is not None
        assert "projects" in registry
        assert len(registry["projects"]) > 0
