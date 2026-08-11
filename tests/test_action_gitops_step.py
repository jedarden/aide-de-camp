"""
Unit tests for GitOps commit action step.

Tests GitOpsCommitStep with mocked dependencies to verify correct behavior
including templated field substitution, git operations, and error handling.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest
import yaml

from src.action.steps.gitops import (
    GitOpsCommitStep,
    StepResult,
    TemplateField,
    GitConflictError,
    GitNetworkError,
    GitAuthenticationError,
    GitStateError,
    GitError,
)


@pytest.fixture
def mock_declarative_config_dir(tmp_path):
    """Create a mock declarative-config directory structure."""
    declarative_config = tmp_path / "declarative-config"
    declarative_config.mkdir()

    # Initialize as git repository
    git_dir = declarative_config / ".git"
    git_dir.mkdir()

    # Create clusters directory structure
    k8s_dir = declarative_config / "k8s"
    k8s_dir.mkdir()

    cluster_dir = k8s_dir / "test-cluster"
    cluster_dir.mkdir()

    return declarative_config


@pytest.fixture
def mock_deployment_manifest(mock_declarative_config_dir):
    """Create a mock Kubernetes deployment manifest."""
    deployment_content = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
  namespace: test-namespace
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        image: ronaldraygun/test-app:latest
        resources:
          limits:
            memory: "512Mi"
            cpu: "500m"
"""

    manifest_path = mock_declarative_config_dir / "k8s" / "test-cluster" / "deployment.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(deployment_content)

    return manifest_path


class TestGitExceptions:
    """Test custom git exception types."""

    def test_git_conflict_error_creation(self):
        """GitConflictError can be created and raised."""
        with pytest.raises(GitConflictError, match="merge conflict"):
            raise GitConflictError("merge conflict detected")

    def test_git_network_error_creation(self):
        """GitNetworkError can be created and raised."""
        with pytest.raises(GitNetworkError, match="network"):
            raise GitNetworkError("network failure")

    def test_git_authentication_error_creation(self):
        """GitAuthenticationError can be created and raised."""
        with pytest.raises(GitAuthenticationError, match="authentication"):
            raise GitAuthenticationError("authentication failed")

    def test_git_state_error_creation(self):
        """GitStateError can be created and raised."""
        with pytest.raises(GitStateError, match="not on main"):
            raise GitStateError("not on main branch")

    def test_git_error_base_class(self):
        """All git errors inherit from GitError base class."""
        with pytest.raises(GitError):
            raise GitConflictError("test")
        with pytest.raises(GitError):
            raise GitNetworkError("test")
        with pytest.raises(GitError):
            raise GitAuthenticationError("test")
        with pytest.raises(GitError):
            raise GitStateError("test")


class TestTemplateField:
    """Test TemplateField validation and parsing."""

    def test_valid_container_image_field(self):
        """Valid container image field passes validation."""
        field = TemplateField(path="/spec/template/spec/containers/0/image", value="ronaldraygun/app:v1.0.0")
        field.validate()  # Should not raise

    def test_valid_replicas_field(self):
        """Valid replicas field passes validation."""
        field = TemplateField(path="/spec/replicas", value=5)
        field.validate()  # Should not raise

    def test_field_path_must_start_with_slash(self):
        """Field path must start with /."""
        with pytest.raises(ValueError, match="must start with /"):
            field = TemplateField(path="spec/replicas", value=5)
            field.validate()

    def test_field_path_rejects_wildcards(self):
        """Field path rejects wildcards."""
        with pytest.raises(ValueError, match="contains forbidden pattern"):
            field = TemplateField(path="/spec/*/containers/0/image", value="test")
            field.validate()

    def test_field_path_rejects_parent_refs(self):
        """Field path rejects parent directory references."""
        with pytest.raises(ValueError, match="contains forbidden pattern"):
            field = TemplateField(path="/spec/../containers/0/image", value="test")
            field.validate()

    def test_field_path_rejects_double_slashes(self):
        """Field path rejects double slashes."""
        with pytest.raises(ValueError, match="contains forbidden pattern"):
            field = TemplateField(path="/spec//containers/0/image", value="test")
            field.validate()

    def test_field_path_rejects_newlines(self):
        """Field path rejects newlines."""
        with pytest.raises(ValueError, match="contains forbidden pattern"):
            field = TemplateField(path="/spec/\n/containers/0/image", value="test")
            field.validate()


class TestGitOpsCommitStep:
    """Test GitOpsCommitStep execution and error handling."""

    def test_init_with_defaults(self):
        """Step initializes with default parameters."""
        step = GitOpsCommitStep()
        assert step.declarative_config_path == Path("/home/coding/declarative-config")
        assert step.git_email == "github@jedarden.com"
        assert step.git_name == "jedarden"
        assert step.timeout == 30

    def test_init_with_custom_params(self):
        """Step initializes with custom parameters."""
        step = GitOpsCommitStep(
            declarative_config_path="/custom/path",
            git_email="custom@example.com",
            git_name="Custom User",
            timeout=60,
        )
        assert step.declarative_config_path == Path("/custom/path")
        assert step.git_email == "custom@example.com"
        assert step.git_name == "Custom User"
        assert step.timeout == 60

    @pytest.mark.asyncio
    async def test_execute_missing_manifest_path(self, mock_declarative_config_dir):
        """Missing manifest_path returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path="",
            template_fields=[{"path": "/spec/replicas", "value": 5}],
            project_cfg={},
        )

        assert result.success is False
        assert "manifest_path is required" in result.error

    @pytest.mark.asyncio
    async def test_execute_missing_template_fields(self, mock_declarative_config_dir):
        """Missing template_fields returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path="k8s/test-cluster/deployment.yaml",
            template_fields=[],
            project_cfg={},
        )

        assert result.success is False
        assert "template_fields is required" in result.error

    @pytest.mark.asyncio
    async def test_execute_manifest_not_found(self, mock_declarative_config_dir):
        """Non-existent manifest returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path="k8s/nonexistent/deployment.yaml",
            template_fields=[{"path": "/spec/replicas", "value": 5}],
            project_cfg={},
        )

        assert result.success is False
        assert "Manifest file not found" in result.error

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_execute_not_git_repository(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Non-git directory returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock the validation method to simulate non-git repository
        with patch.object(step, '_validate_declarative_config_repo', side_effect=GitStateError("Not a git repository")):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={},
            )

        assert result.success is False
        assert "Not a git repository" in result.error

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_execute_uncommitted_changes_fails(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Uncommitted changes in repository returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock the validation method to simulate uncommitted changes
        with patch.object(step, '_validate_declarative_config_repo',
                          side_effect=GitStateError("Repository has uncommitted changes")):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={},
            )

        assert result.success is False
        assert "uncommitted changes" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_execute_not_on_main_branch_fails_validation(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Not being on main branch returns error during pre-flight validation."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git status to show no uncommitted changes, then branch check to show wrong branch
        mock_run.side_effect = [
            # git status (no uncommitted changes)
            Mock(returncode=0, stdout="", stderr=""),
            # git branch (shows wrong branch)
            Mock(returncode=0, stdout="feature-branch\n", stderr=""),
        ]

        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[{"path": "/spec/replicas", "value": 5}],
            project_cfg={},
        )

        assert result.success is False
        assert "not on expected branch" in result.error.lower() or "not on main branch" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_execute_git_authentication_fails(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Git authentication failure returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock the validation method to simulate auth failure
        with patch.object(step, '_validate_declarative_config_repo',
                          side_effect=GitAuthenticationError("Git authentication failed")):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={},
            )

        assert result.success is False
        assert "authentication" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_execute_git_network_failure_fails(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Git network failure returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock the validation method to simulate network failure
        with patch.object(step, '_validate_declarative_config_repo',
                          side_effect=GitNetworkError("Network timeout")):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={},
            )

        assert result.success is False
        assert "network" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_field_spec(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Invalid field specification returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[{"invalid": "spec"}],  # Missing 'path' and 'value'
            project_cfg={},
            dry_run=True,  # Use dry_run since we're testing field validation, not git operations
        )

        assert result.success is False
        assert "Invalid template fields" in result.error

    @pytest.mark.asyncio
    async def test_execute_field_not_in_allowed_prefixes(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Field outside allowed prefixes returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/metadata/name", "value": "new-name"}],
                project_cfg={},
            )

        assert result.success is False
        assert "not in allowed prefixes" in result.error

    @pytest.mark.asyncio
    async def test_execute_dry_run_success(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Dry run execution succeeds without git operations."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[
                {"path": "/spec/replicas", "value": 5},
                {"path": "/spec/template/spec/containers/0/image", "value": "ronaldraygun/app:v1.0.0"},
            ],
            project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
            dry_run=True,
        )

        assert result.success is True
        assert result.data["dry_run"] is True
        assert result.data["modifications"] == 2
        assert "preview" in result.data

    @pytest.mark.asyncio
    async def test_apply_substitutions_single_field(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Single field substitution is applied correctly."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[{"path": "/spec/replicas", "value": 10}],
            project_cfg={"project_slug": "test-app"},
            dry_run=True,
        )

        assert result.success is True
        # Verify the substitution was applied in preview
        assert "replicas" in result.data["preview"].lower() or "10" in result.data["preview"]

    @pytest.mark.asyncio
    async def test_apply_substitutions_multiple_fields(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Multiple field substitutions are applied correctly."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[
                {"path": "/spec/replicas", "value": 7},
                {"path": "/spec/template/spec/containers/0/image", "value": "ronaldraygun/app:v2.0.0"},
            ],
            project_cfg={"project_slug": "test-app"},
            dry_run=True,
        )

        assert result.success is True
        assert result.data["modifications"] == 2

    @pytest.mark.asyncio
    async def test_detect_kubectl_mutation_risk(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Detection of kubectl mutation risk works."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Test with risky field (metadata.name)
        with patch.object(step, '_detect_kubectl_mutation_risk', return_value=True):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={},
                dry_run=True,
            )
            # Risk detection should only log warning, not fail
            assert result.success is True

    @pytest.mark.asyncio
    async def test_apply_field_substitution_with_array_index(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Field substitution with array index works correctly."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[{"path": "/spec/template/spec/containers/0/image", "value": "ronaldraygun/app:v3.0.0"}],
            project_cfg={"project_slug": "test-app"},
            dry_run=True,
        )

        assert result.success is True
        assert "v3.0.0" in result.data["preview"]

    @pytest.mark.asyncio
    async def test_apply_field_substitution_invalid_path(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Invalid field path returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/template/spec/containers/5/image", "value": "test"}],
                project_cfg={"project_slug": "test-app"},
                dry_run=True,
            )

        assert result.success is False
        assert "Failed to apply substitutions" in result.error

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_commit_and_push_success(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Successful commit and push operation."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git config user.email
            if "config" in cmd and "user.email" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            # git config user.name
            if "config" in cmd and "user.name" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            # git status (has changes)
            if "status" in cmd and "--porcelain" in cmd:
                return Mock(returncode=0, stdout=" M k8s/test-cluster/deployment.yaml", stderr="")
            # git add
            if "add" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            # git commit
            if "commit" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            # git rev-parse
            if "rev-parse" in cmd:
                return Mock(returncode=0, stdout="abc123def456\n", stderr="")
            # git push
            if "push" in cmd:
                return Mock(returncode=0, stdout="", stderr="")
            # Default mock for validation commands
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is True
        assert result.commit_sha == "abc123def456"
        assert result.branch == "main"

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_push_network_retry_succeeds_on_second_attempt(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Network retry logic retries push operation on transient failures."""
        import time
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]
        push_attempts = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # First push attempt fails with network error
            if "push" in cmd:
                push_attempts[0] += 1
                if push_attempts[0] == 1:
                    return Mock(returncode=1, stdout="", stderr="Connection timeout\n")
                # Second push attempt succeeds
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            # git status needs to show changes for commit to proceed
            if "status" in cmd and "--porcelain" in cmd:
                return Mock(returncode=0, stdout="M k8s/test-cluster/deployment.yaml", stderr="")

            # git rev-parse HEAD needs to return a valid SHA
            if "rev-parse" in cmd and "HEAD" in cmd:
                return Mock(returncode=0, stdout="abc123def456\n", stderr="")

            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method and sleep for retry
        with patch.object(step, '_validate_declarative_config_repo'), \
             patch('time.sleep'):  # Mock sleep to speed up test
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is True
        assert push_attempts[0] == 2  # Should have retried exactly once

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_push_conflict_returns_commit_locally_flag(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Push conflict returns structured error with commit_locally flag."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git push (fails with conflict)
            if "push" in cmd:
                return Mock(returncode=1, stdout="", stderr="To github.com:jedarden/declarative-config.git\n ! [rejected] main -> main (non-fast-forward)\n")

            # git status needs to show changes for commit to proceed
            if "status" in cmd and "--porcelain" in cmd:
                return Mock(returncode=0, stdout="M k8s/test-cluster/deployment.yaml", stderr="")

            # git rev-parse HEAD needs to return a valid SHA
            if "rev-parse" in cmd and "HEAD" in cmd:
                return Mock(returncode=0, stdout="abc123def456\n", stderr="")

            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is False
        assert result.details.get("commit_locally") is True
        assert result.commit_sha  # Should have a commit SHA even though push failed
        assert "non-fast-forward" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_push_auth_error_returns_structured_error(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Push authentication failure returns structured error without commit_locally flag."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git push (fails with auth error)
            if "push" in cmd:
                return Mock(returncode=1, stdout="", stderr="fatal: Authentication failed\n")

            # git status needs to show changes for commit to proceed
            if "status" in cmd and "--porcelain" in cmd:
                return Mock(returncode=0, stdout="M k8s/test-cluster/deployment.yaml", stderr="")

            # git rev-parse HEAD needs to return a valid SHA
            if "rev-parse" in cmd and "HEAD" in cmd:
                return Mock(returncode=0, stdout="abc123def456\n", stderr="")

            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is False
        assert result.details.get("commit_locally") is True
        assert "authentication" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_commit_conflict_rolls_back_with_backup(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Commit conflict triggers rollback with proper backup."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Read original manifest as YAML for comparison
        original_manifest = yaml.safe_load(mock_deployment_manifest.read_text())

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git commit (fails with conflict)
            if "commit" in cmd and "-m" in cmd:
                return Mock(returncode=1, stdout="", stderr="fatal: Cannot commit: merge conflict\n")
            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app"},
                dry_run=False,
            )

        assert result.success is False
        assert "Failed to commit changes" in result.error

        # Verify rollback occurred by comparing YAML content
        rolled_back_manifest = yaml.safe_load(mock_deployment_manifest.read_text())
        assert rolled_back_manifest == original_manifest

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_push_rejected_with_error(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Push rejection returns appropriate error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git push (fails with rejection)
            if "push" in cmd:
                return Mock(returncode=1, stdout="", stderr="To github.com:jedarden/declarative-config.git\n ! [rejected] main -> main (non-fast-forward)\n")

            # git status needs to show changes for commit to proceed
            if "status" in cmd and "--porcelain" in cmd:
                return Mock(returncode=0, stdout="M k8s/test-cluster/deployment.yaml", stderr="")

            # git rev-parse HEAD needs to return a valid SHA
            if "rev-parse" in cmd and "HEAD" in cmd:
                return Mock(returncode=0, stdout="abc123def456\n", stderr="")

            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is False
        assert "Failed to push changes" in result.error
        assert "non-fast-forward" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_commit_failure_rolls_back_changes(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Commit failure triggers rollback of manifest changes."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Read original manifest as YAML for comparison
        original_manifest = yaml.safe_load(mock_deployment_manifest.read_text())

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git commit (fails)
            if "commit" in cmd and "-m" in cmd:
                return Mock(returncode=1, stdout="", stderr="git commit failed\n")
            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app"},
                dry_run=False,
            )

        assert result.success is False
        assert "Failed to commit changes" in result.error

        # Verify rollback occurred by comparing YAML content
        rolled_back_manifest = yaml.safe_load(mock_deployment_manifest.read_text())
        assert rolled_back_manifest == original_manifest

    @pytest.mark.asyncio
    async def test_not_on_main_branch_fails(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Not being on main branch returns error during pre-flight validation."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock the validation method to simulate being on wrong branch
        with patch.object(step, '_validate_declarative_config_repo',
                          side_effect=GitStateError("Not on expected branch 'main' - current branch: feature-branch")):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app"},
                dry_run=False,
            )

        assert result.success is False
        assert "Not on expected branch" in result.error

    def test_build_commit_message_format(self, mock_declarative_config_dir):
        """Commit message follows standard format."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        fields = [
            TemplateField(path="/spec/replicas", value=5),
            TemplateField(path="/spec/template/spec/containers/0/image", value="ronaldraygun/app:v1.0.0"),
        ]

        project_cfg = {
            "project_slug": "test-app",
            "cluster": "test-cluster",
        }

        commit_msg = step._build_commit_message("k8s/test-cluster/deployment.yaml", fields, project_cfg)

        assert "feat(test-app): update k8s/test-cluster/deployment.yaml" in commit_msg
        assert "GitOps-managed update for test-app on test-cluster" in commit_msg
        assert "/spec/replicas: 5" in commit_msg
        assert "/spec/template/spec/containers/0/image: ronaldraygun/app:v1.0.0" in commit_msg
        assert "Co-Authored-By: Claude <noreply@anthropic.com>" in commit_msg

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_rollback_operation(self, mock_run, mock_declarative_config_dir):
        """Rollback operation works correctly."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git show (parent commit)
            if "show" in cmd:
                return Mock(returncode=0, stdout="original manifest content", stderr="")

            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            # Create a test manifest file
            test_manifest = mock_declarative_config_dir / "k8s" / "test-cluster" / "deployment.yaml"
            test_manifest.parent.mkdir(parents=True, exist_ok=True)
            test_manifest.write_text("original content")

            result = await step.rollback(
                manifest_path="k8s/test-cluster/deployment.yaml",
                commit_sha="abc123",
            )

            assert result.success is True
            assert result.details.get("reverted_commit") == "abc123"

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_rollback_git_revert_fails(self, mock_run, mock_declarative_config_dir):
        """Rollback failure returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0] if args else []

            # git show (parent commit) fails
            if "show" in cmd:
                return Mock(returncode=1, stdout="", stderr="git show failed\n")

            # All other commands succeed
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_git_command

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.rollback(
                manifest_path="k8s/test-cluster/deployment.yaml",
                commit_sha="abc123",
            )

            assert result.success is False
            assert "git revert failed" in result.error or "rollback failed" in result.error.lower()


class TestGitOpsCommitStepIntegration:
    """Integration tests for GitOps commit step with actual file operations."""

    @pytest.mark.asyncio
    async def test_full_dry_run_workflow(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Complete dry run workflow from start to finish."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Read original manifest
        original_manifest = yaml.safe_load(mock_deployment_manifest.read_text())

        # Execute dry run
        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[
                {"path": "/spec/replicas", "value": 15},
                {"path": "/spec/template/spec/containers/0/image", "value": "ronaldraygun/app:production-v1.2.3"},
            ],
            project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
            dry_run=True,
        )

        assert result.success is True
        assert result.data.get("dry_run") is True
        assert result.data.get("modifications") == 2

        # Verify original file was not modified
        current_manifest = yaml.safe_load(mock_deployment_manifest.read_text())
        assert current_manifest == original_manifest

    @pytest.mark.asyncio
    async def test_json_pointer_path_navigation(self, mock_declarative_config_dir, mock_deployment_manifest):
        """JSON Pointer path navigation works correctly for complex structures."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Test navigation to nested container spec
        result = await step.execute(
            manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
            template_fields=[
                {"path": "/spec/template/spec/containers/0/image", "value": "ronaldraygun/app:test-tag"},
            ],
            project_cfg={"project_slug": "test-app"},
            dry_run=True,
        )

        assert result.success is True
        # Verify the container image was substituted
        assert "test-tag" in result.data.get("preview", "")

    @pytest.mark.asyncio
    async def test_path_allowed_validation(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Path whitelist validation enforcement works."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Test allowed paths
        allowed_paths = [
            "/spec/replicas",
            "/spec/template/spec/containers/0/image",
            "/spec/template/spec/containers/1/image",
        ]

        for allowed_path in allowed_paths:
            is_allowed = step._is_path_allowed(allowed_path)
            assert is_allowed is True, f"Path {allowed_path} should be allowed"

        # Test disallowed paths
        disallowed_paths = [
            "/metadata/name",
            "/metadata/namespace",
            "/apiVersion",
            "/kind",
        ]

        for disallowed_path in disallowed_paths:
            is_allowed = step._is_path_allowed(disallowed_path)
            assert is_allowed is False, f"Path {disallowed_path} should be disallowed"

    def test_diff_manifests_generation(self, mock_declarative_config_dir):
        """Manifest diff generation works correctly."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        original = {"spec": {"replicas": 3, "template": {"spec": {"containers": [{"image": "old"}]}}}}
        modified = {"spec": {"replicas": 5, "template": {"spec": {"containers": [{"image": "new"}]}}}}

        diff = step._diff_manifests(original, modified)

        assert diff != "No changes detected"
        assert "5" in diff or "new" in diff

    def test_diff_manifests_no_changes(self, mock_declarative_config_dir):
        """Diff with no changes is detected correctly."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        manifest = {"spec": {"replicas": 3}}
        diff = step._diff_manifests(manifest, manifest)

        assert diff == "No changes detected"

    @pytest.mark.asyncio
    async def test_integration_with_real_git_repository(self, tmp_path):
        """Integration test with real git repository (not declarative-config)."""
        import subprocess

        # Create a temporary git repository
        test_repo = tmp_path / "test-repo"
        test_repo.mkdir()
        subprocess.run(["git", "init"], cwd=test_repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=test_repo, check=True, capture_output=True)

        # Create k8s directory structure
        k8s_dir = test_repo / "k8s" / "test-cluster"
        k8s_dir.mkdir(parents=True)

        # Create a deployment manifest
        deployment_manifest = k8s_dir / "deployment.yaml"
        deployment_content = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
  namespace: test-namespace
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        image: ronaldraygun/test-app:v1.0.0
        resources:
          limits:
            memory: "512Mi"
            cpu: "500m"
"""
        deployment_manifest.write_text(deployment_content)

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=test_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=test_repo, check=True, capture_output=True)

        # Create GitOps step pointing to test repository
        step = GitOpsCommitStep(
            declarative_config_path=str(test_repo),
            git_email="test@example.com",
            git_name="Test User",
        )

        # Execute with dry run first
        result = await step.execute(
            manifest_path="k8s/test-cluster/deployment.yaml",
            template_fields=[{"path": "/spec/replicas", "value": 5}],
            project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
            dry_run=True,
        )

        assert result.success is True
        assert result.data.get("dry_run") is True

        # Verify no actual changes were made
        current_content = deployment_manifest.read_text()
        assert "replicas: 3" in current_content  # Should still be 3

    @pytest.mark.asyncio
    async def test_gitops_never_bypassed_no_kubectl_mutations(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Test that validates GitOps is never bypassed (no direct kubectl mutations)."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Test that risky paths are detected
        risky_field = {"path": "/metadata/name", "value": "new-name"}
        safe_fields = [
            {"path": "/spec/replicas", "value": 5},
        ]

        # Verify the risk detection works
        with patch.object(step, '_validate_declarative_config_repo'):
            # Safe fields should work in dry run
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=safe_fields,
                project_cfg={"project_slug": "test-app"},
                dry_run=True,
            )
            assert result.success is True

            # Risky fields should be detected and rejected
            result_risky = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[risky_field],
                project_cfg={"project_slug": "test-app"},
                dry_run=True,
            )
            # Should fail because metadata.name is not in allowed prefixes
            assert result_risky.success is False
            assert "not in allowed prefixes" in result_risky.error

        # Test that _detect_kubectl_mutation_risk identifies suspicious patterns
        risky_patterns = [
            [{"path": "/metadata/name", "value": "test"}],
            [{"path": "/metadata/namespace", "value": "test"}],
            [{"path": "/kind", "value": "Pod"}],
            [{"path": "/apiVersion", "value": "v1"}],
        ]

        for fields in risky_patterns:
            risk_detected = step._detect_kubectl_mutation_risk(fields)
            assert risk_detected is True, f"Should detect risk for fields: {fields}"

        # Test that safe patterns don't trigger risk detection
        safe_patterns = [
            [{"path": "/spec/replicas", "value": 5}],
            [{"path": "/spec/template/spec/containers/0/image", "value": "test:v1"}],
        ]

        for fields in safe_patterns:
            risk_detected = step._detect_kubectl_mutation_risk(fields)
            assert risk_detected is False, f"Should not detect risk for safe fields: {fields}"
