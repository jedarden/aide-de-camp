"""
Tests for manifest template reading and substitution.

These tests verify that the manifest template engine:
- Reads manifests from declarative-config
- Applies template_vars substitution correctly
- Validates that only whitelisted fields are modified
- Raises ValidationError for non-templated field changes
- Returns modified manifest as string for git commit
- Handles file not found errors gracefully
"""

import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from src.action.manifest_template import (
    ManifestTemplateEngine,
    ManifestResult,
    TemplateField,
    ValidationError,
    read_manifest_with_templates,
)


# Fixtures
@pytest.fixture
def temp_declarative_config():
    """Create a temporary declarative-config directory structure."""
    temp_dir = tempfile.mkdtemp()
    config_path = Path(temp_dir) / "declarative-config"
    config_path.mkdir()

    # Create k8s directory structure
    k8s_path = config_path / "k8s"
    k8s_path.mkdir()

    # Create a test cluster directory
    cluster_path = k8s_path / "test-cluster"
    cluster_path.mkdir()

    # Create a test namespace directory
    namespace_path = cluster_path / "test-ns"
    namespace_path.mkdir()

    # Create a sample deployment manifest
    deployment_data = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "test-deployment",
            "namespace": "test-ns",
        },
        "spec": {
            "replicas": 3,
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {
                    "maxSurge": 1,
                    "maxUnavailable": 0,
                },
            },
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "image": "nginx:1.18",
                            "resources": {
                                "limits": {
                                    "memory": "512Mi",
                                    "cpu": "500m",
                                },
                                "requests": {
                                    "memory": "256Mi",
                                    "cpu": "250m",
                                },
                            },
                        },
                        {
                            "name": "sidecar",
                            "image": "busybox:1.32",
                        },
                    ],
                },
            },
        },
    }

    deployment_path = namespace_path / "deployment.yaml"
    with open(deployment_path, "w") as f:
        yaml.dump(deployment_data, f)

    yield config_path, deployment_path

    # Cleanup
    shutil.rmtree(temp_dir)


# Test TemplateField validation
def test_template_field_valid_path():
    """Test that valid field paths are accepted."""
    field = TemplateField(path="/spec/template/spec/containers/0/image", value="nginx:1.19")
    field.validate()  # Should not raise


def test_template_field_invalid_path_no_slash():
    """Test that paths not starting with / are rejected."""
    field = TemplateField(path="spec/replicas", value=5)
    with pytest.raises(ValidationError, match="must start with /"):
        field.validate()


def test_template_field_invalid_path_suspicious_patterns():
    """Test that suspicious patterns in paths are rejected."""
    suspicious_paths = [
        ("/spec/*/image", "*"),
        ("/spec/../image", ".."),
        ("/spec//image", "//"),
        ("/spec/\n/image", "\n"),
        ("/spec/\r/image", "\r"),
    ]

    for path, pattern in suspicious_paths:
        field = TemplateField(path=path, value="test")
        with pytest.raises(ValidationError, match=f"contains forbidden pattern '{pattern}'"):
            field.validate()


def test_template_field_invalid_path_special_chars():
    """Test that special characters in path components are rejected."""
    invalid_paths = [
        "/spec/$!/image",
        "/spec/test@path/image",
        "/spec/test#path/image",
    ]

    for path in invalid_paths:
        field = TemplateField(path=path, value="test")
        with pytest.raises(ValidationError, match="Invalid field path component"):
            field.validate()


def test_template_field_valid_alphanumeric_path():
    """Test that alphanumeric paths with - and _ are accepted."""
    valid_paths = [
        "/spec/template/spec/containers/0/image",
        "/spec/template/spec/containers/0/env/0/value",
        "/spec/replica-count",
        "/spec/template_spec/image_name",
    ]

    for path in valid_paths:
        field = TemplateField(path=path, value="test")
        field.validate()  # Should not raise


def test_template_field_numeric_array_indices():
    """Test that numeric array indices are accepted."""
    field = TemplateField(path="/spec/template/spec/containers/0/image", value="nginx:1.19")
    field.validate()  # Should not raise


# Test ManifestTemplateEngine
class TestManifestTemplateEngine:
    """Tests for ManifestTemplateEngine."""

    def test_read_and_apply_templates_success(self, temp_declarative_config):
        """Test successful manifest reading and template application."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        template_vars = {
            "/spec/template/spec/containers/0/image": "nginx:1.19",
            "/spec/replicas": 5,
        }

        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars=template_vars,
        )

        assert result.success is True
        assert result.manifest_content is not None
        assert result.changes_summary is not None
        assert len(result.changes_summary) == 2

        # Verify the changes were applied
        modified_data = yaml.safe_load(result.manifest_content)
        assert modified_data["spec"]["replicas"] == 5
        assert modified_data["spec"]["template"]["spec"]["containers"][0]["image"] == "nginx:1.19"

    def test_read_and_apply_templates_no_changes(self, temp_declarative_config):
        """Test template application when no changes are needed."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={},
        )

        assert result.success is True
        assert result.manifest_content is None  # No changes, so None
        assert result.changes_summary == []

    def test_read_and_apply_templates_file_not_found(self, temp_declarative_config):
        """Test handling of non-existent manifest files."""
        config_path, _ = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        result = engine.read_and_apply_templates(
            manifest_path="k8s/nonexistent/file.yaml",
            template_vars={"/spec/replicas": 5},
        )

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_read_and_apply_templates_invalid_path_traversal(self, temp_declarative_config):
        """Test rejection of path traversal attempts."""
        config_path, _ = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Attempt path traversal
        result = engine.read_and_apply_templates(
            manifest_path="../../../etc/passwd",
            template_vars={"/spec/replicas": 5},
        )

        assert result.success is False
        assert "path traversal" in result.error.lower() or "not found" in result.error.lower()

    def test_apply_substitutions_forbidden_path_metadata_name(self, temp_declarative_config):
        """Test that metadata.name modifications are forbidden."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Attempt to modify metadata.name (forbidden)
        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/metadata/name": "hacked-name"},
        )

        assert result.success is False
        assert result.error is not None
        assert "forbidden" in result.error.lower()

    def test_apply_substitutions_forbidden_path_metadata_namespace(self, temp_declarative_config):
        """Test that metadata.namespace modifications are forbidden."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Attempt to modify metadata.namespace (forbidden)
        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/metadata/namespace": "hacked-namespace"},
        )

        assert result.success is False
        assert result.error is not None
        assert "forbidden" in result.error.lower()

    def test_apply_substitutions_forbidden_path_kind(self, temp_declarative_config):
        """Test that kind modifications are forbidden."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Attempt to modify kind (forbidden)
        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/kind": "StatefulSet"},
        )

        assert result.success is False
        assert result.error is not None
        assert "forbidden" in result.error.lower()

    def test_apply_substitutions_forbidden_path_apiVersion(self, temp_declarative_config):
        """Test that apiVersion modifications are forbidden."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Attempt to modify apiVersion (forbidden)
        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/apiVersion": "v2"},
        )

        assert result.success is False
        assert result.error is not None
        assert "forbidden" in result.error.lower()

    def test_apply_substitutions_non_whitelisted_path_strict(self, temp_declarative_config):
        """Test that non-whitelisted paths are rejected in strict mode."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Attempt to modify a non-whitelisted path
        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/spec/strategy/rollingUpdate/maxSurge": 2},
        )

        assert result.success is False
        assert result.error is not None
        assert "not in allowed prefixes" in result.error.lower()

    def test_apply_substitutions_non_whitelisted_path_non_strict(self, temp_declarative_config):
        """Test that non-whitelisted paths are allowed in non-strict mode."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=False,
        )

        # Attempt to modify a non-whitelisted path (should succeed in non-strict mode)
        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/spec/strategy/rollingUpdate/maxSurge": 2},
        )

        assert result.success is True
        assert result.manifest_content is not None

    def test_apply_substitutions_container_image(self, temp_declarative_config):
        """Test container image substitution."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/spec/template/spec/containers/0/image": "nginx:1.19"},
        )

        assert result.success is True
        modified_data = yaml.safe_load(result.manifest_content)
        assert modified_data["spec"]["template"]["spec"]["containers"][0]["image"] == "nginx:1.19"

    def test_apply_substitutions_container_resources(self, temp_declarative_config):
        """Test container resource limit substitution."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={
                "/spec/template/spec/containers/0/resources/limits/memory": "1Gi",
                "/spec/template/spec/containers/0/resources/limits/cpu": "1000m",
            },
        )

        assert result.success is True
        modified_data = yaml.safe_load(result.manifest_content)
        assert modified_data["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "1Gi"
        assert modified_data["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["cpu"] == "1000m"

    def test_apply_substitutions_replica_count(self, temp_declarative_config):
        """Test replica count substitution."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={"/spec/replicas": 10},
        )

        assert result.success is True
        modified_data = yaml.safe_load(result.manifest_content)
        assert modified_data["spec"]["replicas"] == 10

    def test_apply_substitutions_multiple_containers(self, temp_declarative_config):
        """Test substitution in multiple containers."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={
                "/spec/template/spec/containers/0/image": "nginx:1.19",
                "/spec/template/spec/containers/1/image": "busybox:1.33",
            },
        )

        assert result.success is True
        modified_data = yaml.safe_load(result.manifest_content)
        assert modified_data["spec"]["template"]["spec"]["containers"][0]["image"] == "nginx:1.19"
        assert modified_data["spec"]["template"]["spec"]["containers"][1]["image"] == "busybox:1.33"

    def test_get_field_value_invalid_path(self, temp_declarative_config):
        """Test that invalid paths raise ValidationError."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Read the manifest
        manifest_data, _ = engine._read_manifest(deployment_path)

        # Try to get a non-existent field
        with pytest.raises(ValidationError, match="not found"):
            engine._get_field_value(manifest_data, "/spec/nonexistent/field")

    def test_get_field_value_invalid_array_index(self, temp_declarative_config):
        """Test that invalid array indices raise ValidationError."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Read the manifest
        manifest_data, _ = engine._read_manifest(deployment_path)

        # Try to access out-of-range array index
        with pytest.raises(ValidationError, match="out of range"):
            engine._get_field_value(manifest_data, "/spec/template/spec/containers/99/image")

    def test_changes_summary_tracks_modifications(self, temp_declarative_config):
        """Test that changes summary correctly tracks modifications."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path)),
            template_vars={
                "/spec/replicas": 10,
                "/spec/template/spec/containers/0/image": "nginx:1.19",
            },
        )

        assert result.success is True
        assert len(result.changes_summary) == 2

        # Check change summaries
        changes_str = " ".join(result.changes_summary)
        assert "/spec/replicas" in changes_str
        assert "/spec/template/spec/containers/0/image" in changes_str
        assert "10" in changes_str
        assert "nginx:1.19" in changes_str

    def test_cluster_prefix_in_manifest_path(self, temp_declarative_config):
        """Test manifest path resolution with cluster prefix."""
        config_path, deployment_path = temp_declarative_config

        engine = ManifestTemplateEngine(
            declarative_config_path=str(config_path),
            strict_validation=True,
        )

        # Use cluster parameter instead of prefixing in path
        result = engine.read_and_apply_templates(
            manifest_path=str(deployment_path.relative_to(config_path / "k8s" / "test-cluster")),
            template_vars={"/spec/replicas": 7},
            cluster="test-cluster",
        )

        assert result.success is True
        modified_data = yaml.safe_load(result.manifest_content)
        assert modified_data["spec"]["replicas"] == 7


# Test convenience function
def test_read_manifest_with_templates_convenience(temp_declarative_config):
    """Test the convenience function for manifest reading."""
    config_path, deployment_path = temp_declarative_config

    result = read_manifest_with_templates(
        manifest_path=str(deployment_path.relative_to(config_path)),
        template_vars={"/spec/replicas": 8},
        declarative_config_path=str(config_path),
        strict_validation=True,
    )

    assert result.success is True
    modified_data = yaml.safe_load(result.manifest_content)
    assert modified_data["spec"]["replicas"] == 8


# Test YAML output format
def test_yaml_output_format(temp_declarative_config):
    """Test that output YAML is well-formatted."""
    config_path, deployment_path = temp_declarative_config

    engine = ManifestTemplateEngine(
        declarative_config_path=str(config_path),
        strict_validation=True,
    )

    result = engine.read_and_apply_templates(
        manifest_path=str(deployment_path.relative_to(config_path)),
        template_vars={"/spec/replicas": 5},
    )

    assert result.success is True

    # Verify output is valid YAML
    yaml_data = yaml.safe_load(result.manifest_content)
    assert yaml_data is not None
    assert isinstance(yaml_data, dict)

    # Verify it can be parsed back
    reparsed = yaml.safe_load(result.manifest_content)
    assert reparsed["spec"]["replicas"] == 5


# Test error cases
def test_empty_manifest_path():
    """Test that empty manifest path is rejected."""
    engine = ManifestTemplateEngine(
        declarative_config_path="/tmp/config",
        strict_validation=True,
    )

    result = engine.read_and_apply_templates(
        manifest_path="",
        template_vars={"/spec/replicas": 5},
    )

    assert result.success is False
    assert "required" in result.error.lower()


def test_invalid_template_field_spec(temp_declarative_config):
    """Test that invalid template field specifications are rejected."""
    config_path, _ = temp_declarative_config

    engine = ManifestTemplateEngine(
        declarative_config_path=str(config_path),
        strict_validation=True,
    )

    # Create a test deployment file
    deployment_path = config_path / "k8s" / "test-cluster" / "test-ns" / "deployment.yaml"
    deployment_path.parent.mkdir(parents=True, exist_ok=True)
    with open(deployment_path, "w") as f:
        yaml.dump({"apiVersion": "apps/v1", "kind": "Deployment"}, f)

    # Use invalid path
    result = engine.read_and_apply_templates(
        manifest_path=str(deployment_path.relative_to(config_path)),
        template_vars={"invalid path": 5},  # Invalid path (no / prefix)
    )

    assert result.success is False
    assert "Invalid template variables" in result.error or "Invalid field path" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])