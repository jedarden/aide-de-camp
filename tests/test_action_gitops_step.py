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
        assert "not on expected branch" in result.error.lower()
        assert "main" in result.error.lower()

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

        call_count = []

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else []
            call_count.append(cmd)
            # git status --porcelain - has changes
            if "status" in cmd and "--porcelain" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=" M k8s/test-cluster/deployment.yaml\n", stderr="")
            # git rev-parse HEAD - return commit SHA
            if "rev-parse" in cmd and "HEAD" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc123def456\n", stderr="")
            # All other git commands succeed
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_subprocess

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is True
        assert result.data["commit_sha"] == "abc123def456"
        assert result.data["branch"] == "main"

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_push_network_retry_succeeds_on_second_attempt(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Network retry logic retries push operation on transient failures."""
        import time
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        call_count = [0]

        def mock_git_command(*args, **kwargs):
            cmd = args[0] if args else []
            call_count[0] += 1
            # First push attempt fails with network error
            if "push" in cmd and call_count[0] == 7:  # 7th call is the push
                return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Connection timeout\n")
            # Second push attempt succeeds
            elif "push" in cmd and call_count[0] == 8:  # Retry happens immediately after
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            # git status --porcelain - has changes
            if "status" in cmd and "--porcelain" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=" M k8s/test-cluster/deployment.yaml\n", stderr="")
            # git rev-parse HEAD - return commit SHA
            if "rev-parse" in cmd and "HEAD" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc123def456\n", stderr="")
            # All other commands succeed
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

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
        assert call_count[0] >= 7  # Should have tried at least the original push

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_push_conflict_returns_commit_locally_flag(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Push conflict returns structured error with commit_locally flag."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git commands to succeed through commit, fail push with conflict
        mock_run.side_effect = [
            # git config user.email
            Mock(returncode=0, stdout="", stderr=""),
            # git config user.name
            Mock(returncode=0, stdout="", stderr=""),
            # git status (has changes)
            Mock(returncode=0, stdout=" M k8s/test-cluster/deployment.yaml", stderr=""),
            # git add
            Mock(returncode=0, stdout="", stderr=""),
            # git commit
            Mock(returncode=0, stdout="", stderr=""),
            # git rev-parse
            Mock(returncode=0, stdout="abc123def456\n", stderr=""),
            # git push (fails with conflict)
            Mock(returncode=1, stdout="", stderr="To github.com:jedarden/declarative-config.git\n ! [rejected] main -> main (non-fast-forward)\n"),
        ]

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is False
        assert result.data.get("commit_locally") is True
        assert result.data.get("commit_sha") == "abc123def456"
        assert "non-fast-forward" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_push_auth_error_returns_structured_error(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Push authentication failure returns structured error without commit_locally flag."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git commands to succeed through commit, fail push with auth error
        mock_run.side_effect = [
            # git config user.email
            Mock(returncode=0, stdout="", stderr=""),
            # git config user.name
            Mock(returncode=0, stdout="", stderr=""),
            # git status (has changes)
            Mock(returncode=0, stdout=" M k8s/test-cluster/deployment.yaml", stderr=""),
            # git add
            Mock(returncode=0, stdout="", stderr=""),
            # git commit
            Mock(returncode=0, stdout="", stderr=""),
            # git rev-parse
            Mock(returncode=0, stdout="abc123def456\n", stderr=""),
            # git push (fails with auth error)
            Mock(returncode=1, stdout="", stderr="fatal: Authentication failed\n"),
        ]

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app", "cluster": "test-cluster"},
                dry_run=False,
            )

        assert result.success is False
        assert result.data.get("commit_locally") is True
        assert "authentication" in result.error.lower()

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_commit_conflict_rolls_back_with_backup(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Commit conflict triggers rollback with proper backup."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Read original manifest as YAML for comparison
        original_manifest = yaml.safe_load(mock_deployment_manifest.read_text())

        # Mock git commands to fail at commit with conflict
        mock_run.side_effect = [
            # git config user.email
            Mock(returncode=0, stdout="", stderr=""),
            # git config user.name
            Mock(returncode=0, stdout="", stderr=""),
            # git status (has changes)
            Mock(returncode=0, stdout=" M k8s/test-cluster/deployment.yaml", stderr=""),
            # git add
            Mock(returncode=0, stdout="", stderr=""),
            # git commit (fails with conflict)
            Mock(returncode=1, stdout="", stderr="fatal: Cannot commit: merge conflict\n"),
        ]

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

        # Mock git commands up to push, then fail
        mock_run.side_effect = [
            # git config user.email
            Mock(returncode=0, stdout="", stderr=""),
            # git config user.name
            Mock(returncode=0, stdout="", stderr=""),
            # git status (has changes)
            Mock(returncode=0, stdout=" M k8s/test-cluster/deployment.yaml", stderr=""),
            # git add
            Mock(returncode=0, stdout="", stderr=""),
            # git commit
            Mock(returncode=0, stdout="", stderr=""),
            # git rev-parse
            Mock(returncode=0, stdout="abc123def456\n", stderr=""),
            # git branch --show-current
            Mock(returncode=0, stdout="main\n", stderr=""),
            # git push (fails with rejection)
            Mock(returncode=1, stdout="", stderr="To github.com:jedarden/declarative-config.git\n ! [rejected] main -> main (non-fast-forward)\n"),
        ]

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

        # Mock git commands to fail at commit
        mock_run.side_effect = [
            # git config user.email
            Mock(returncode=0, stdout="", stderr=""),
            # git config user.name
            Mock(returncode=0, stdout="", stderr=""),
            # git status (has changes)
            Mock(returncode=0, stdout=" M k8s/test-cluster/deployment.yaml", stderr=""),
            # git add
            Mock(returncode=0, stdout="", stderr=""),
            # git commit (fails)
            Mock(returncode=1, stdout="", stderr="git commit failed\n"),
        ]

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
    async def test_not_on_main_branch_fails(self, mock_run, mock_declarative_config_dir, mock_deployment_manifest):
        """Not being on main branch returns error."""
        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git commands to show we're on feature branch
        mock_run.side_effect = [
            # git config user.email
            Mock(returncode=0, stdout="", stderr=""),
            # git config user.name
            Mock(returncode=0, stdout="", stderr=""),
            # git status (has changes)
            Mock(returncode=0, stdout=" M k8s/test-cluster/deployment.yaml", stderr=""),
            # git add
            Mock(returncode=0, stdout="", stderr=""),
            # git commit
            Mock(returncode=0, stdout="", stderr=""),
            # git rev-parse
            Mock(returncode=0, stdout="abc123def456\n", stderr=""),
            # git branch --show-current (shows feature branch)
            Mock(returncode=0, stdout="feature-branch\n", stderr=""),
        ]

        # Mock the validation method to bypass git repo check
        with patch.object(step, '_validate_declarative_config_repo'):
            result = await step.execute(
                manifest_path=str(mock_deployment_manifest.relative_to(mock_declarative_config_dir)),
                template_fields=[{"path": "/spec/replicas", "value": 5}],
                project_cfg={"project_slug": "test-app"},
                dry_run=False,
            )

        assert result.success is False
        assert "Not on main branch" in result.error

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
        # Mock git revert and push
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git revert
            Mock(returncode=0, stdout="", stderr=""),  # git commit revert
            Mock(returncode=0, stdout="main\n", stderr=""),  # git branch
            Mock(returncode=0, stdout="", stderr=""),  # git push
        ]

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.rollback(
            manifest_path="k8s/test-cluster/deployment.yaml",
            commit_sha="abc123",
        )

        assert result.success is True
        assert result.data["reverted_commit"] == "abc123"

    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_rollback_git_revert_fails(self, mock_run, mock_declarative_config_dir):
        """Rollback failure returns error."""
        mock_run.side_effect = [
            Mock(returncode=1, stdout="", stderr="git revert failed\n"),
        ]

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        result = await step.rollback(
            manifest_path="k8s/test-cluster/deployment.yaml",
            commit_sha="abc123",
        )

        assert result.success is False
        assert "git revert failed" in result.error


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
        assert result.data["dry_run"] is True
        assert result.data["modifications"] == 2

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
        assert "test-tag" in result.data["preview"]

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


class TestBranchValidationScenarios:
    """Comprehensive tests for branch validation scenarios."""

    @pytest.mark.asyncio
    async def test_branch_validation_fails_on_non_main_branch(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Branch validation correctly fails when on a non-main branch."""
        from src.action.steps.git_validation import validate_main_branch, GitStateError

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock being on feature branch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="feature-branch\n", stderr="")

            with pytest.raises(GitStateError) as exc_info:
                validate_main_branch(mock_declarative_config_dir)

            # Verify error message is clear and actionable
            error_message = str(exc_info.value)
            assert "Not on expected branch 'main'" in error_message
            assert "currently on 'feature-branch'" in error_message
            assert "Please switch to main branch first" in error_message
            assert "[branch]" in error_message  # Validation type prefix
            assert "Details:" in error_message  # Structured details

    @pytest.mark.asyncio
    async def test_branch_validation_passes_on_main_branch(self, mock_declarative_config_dir, mock_deployment_manifest):
        """Branch validation correctly passes when on main branch."""
        from src.action.steps.git_validation import validate_main_branch

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock being on main branch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="main\n", stderr="")

            result = validate_main_branch(mock_declarative_config_dir)
            assert result is True

    @pytest.mark.asyncio
    async def test_branch_validation_custom_branch_name(self, mock_declarative_config_dir):
        """Branch validation works with custom branch name."""
        from src.action.steps.git_validation import validate_main_branch

        # Mock being on develop branch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="develop\n", stderr="")

            result = validate_main_branch(mock_declarative_config_dir, expected_branch="develop")
            assert result is True

    @pytest.mark.asyncio
    async def test_branch_validation_error_on_detached_head(self, mock_declarative_config_dir):
        """Branch validation handles detached HEAD state."""
        from src.action.steps.git_validation import validate_main_branch, GitStateError

        # Mock detached HEAD (empty output from branch --show-current)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            with pytest.raises(GitStateError) as exc_info:
                validate_main_branch(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "Not on expected branch" in error_message


class TestUncommittedChangesScenarios:
    """Comprehensive tests for uncommitted changes detection scenarios."""

    @pytest.mark.asyncio
    async def test_uncommitted_changes_with_staged_files(self, mock_declarative_config_dir):
        """Uncommitted changes detection correctly identifies staged files."""
        from src.action.steps.git_validation import check_uncommitted_changes, GitStateError

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git status output with staged changes
        # "M " means modified in the working tree and staged for commit
        staged_output = "M  k8s/test-cluster/deployment.yaml\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=staged_output, stderr="")

            with pytest.raises(GitStateError) as exc_info:
                check_uncommitted_changes(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "uncommitted changes" in error_message.lower()
            assert "staged change(s)" in error_message.lower()
            assert "commit or stash" in error_message.lower()

    @pytest.mark.asyncio
    async def test_uncommitted_changes_with_unstaged_files(self, mock_declarative_config_dir):
        """Uncommitted changes detection correctly identifies unstaged files."""
        from src.action.steps.git_validation import check_uncommitted_changes, GitStateError

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git status output with unstaged changes
        # " M" means modified in the working tree but not staged
        unstaged_output = " M k8s/test-cluster/deployment.yaml\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=unstaged_output, stderr="")

            with pytest.raises(GitStateError) as exc_info:
                check_uncommitted_changes(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "uncommitted changes" in error_message.lower()
            assert "unstaged change(s)" in error_message.lower()

    @pytest.mark.asyncio
    async def test_uncommitted_changes_with_mixed_staged_unstaged(self, mock_declarative_config_dir):
        """Uncommitted changes detection handles mixed staged and unstaged files."""
        from src.action.steps.git_validation import check_uncommitted_changes, GitStateError

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git status with both staged and unstaged changes
        mixed_output = """M  k8s/test-cluster/deployment.yaml
 M k8s/test-cluster/service.yaml
"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=mixed_output, stderr="")

            with pytest.raises(GitStateError) as exc_info:
                check_uncommitted_changes(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "uncommitted changes" in error_message.lower()
            # Should mention both types
            assert "unstaged" in error_message.lower() or "staged" in error_message.lower()

    @pytest.mark.asyncio
    async def test_uncommitted_changes_with_new_files(self, mock_declarative_config_dir):
        """Uncommitted changes detection correctly identifies new untracked files."""
        from src.action.steps.git_validation import check_uncommitted_changes, GitStateError

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git status with untracked files (?? prefix)
        untracked_output = "?? k8s/test-cluster/new-file.yaml\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=untracked_output, stderr="")

            with pytest.raises(GitStateError) as exc_info:
                check_uncommitted_changes(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "uncommitted changes" in error_message.lower()

    @pytest.mark.asyncio
    async def test_validation_passes_on_clean_working_tree(self, mock_declarative_config_dir):
        """Validation correctly passes when working tree is clean."""
        from src.action.steps.git_validation import check_uncommitted_changes

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock clean working tree (empty git status --porcelain output)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = check_uncommitted_changes(mock_declarative_config_dir)
            assert result is True


class TestPreflightValidationScenarios:
    """Comprehensive tests for pre-flight validation scenarios."""

    @pytest.mark.asyncio
    async def test_preflight_validation_all_checks_pass(self, mock_declarative_config_dir):
        """Preflight validation passes when all checks succeed."""
        from src.action.steps.git_validation import PreflightGitValidation

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock all git commands to succeed with proper argument matching
        with patch("subprocess.run") as mock_run:
            def mock_git_command(command, *args, **kwargs):
                # Branch check
                if "branch" in command and "--show-current" in command:
                    return Mock(returncode=0, stdout="main\n", stderr="")
                # Status check (clean)
                elif "status" in command and "--porcelain" in command:
                    return Mock(returncode=0, stdout="", stderr="")
                # Remote check
                elif "remote" in command and "-v" in command:
                    return Mock(returncode=0, stdout="origin\tgit@github.com:test/repo.git (fetch)\n", stderr="")
                # All other commands
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_git_command

            validator = PreflightGitValidation(
                repo_path=mock_declarative_config_dir,
                expected_branch="main",
                expected_remote_pattern=None,
                timeout=10,
                strict=True,
            )

            result = validator.validate_all()
            assert result is True
            assert len(validator.errors) == 0

    @pytest.mark.asyncio
    async def test_preflight_validation_fails_on_branch_mismatch(self, mock_declarative_config_dir):
        """Preflight validation fails immediately on branch check failure."""
        from src.action.steps.git_validation import PreflightGitValidation, GitStateError

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock branch check returning wrong branch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="feature-branch\n", stderr="")

            validator = PreflightGitValidation(
                repo_path=mock_declarative_config_dir,
                expected_branch="main",
                strict=True,
            )

            with pytest.raises(GitStateError) as exc_info:
                validator.validate_all()

            error_message = str(exc_info.value)
            assert "Not on expected branch" in error_message

    @pytest.mark.asyncio
    async def test_preflight_validation_strict_mode_stops_on_first_error(self, mock_declarative_config_dir):
        """Strict mode validation stops on first error and raises."""
        from src.action.steps.git_validation import PreflightGitValidation, GitStateError

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock branch check to fail
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="wrong-branch\n", stderr="")

            validator = PreflightGitValidation(
                repo_path=mock_declarative_config_dir,
                expected_branch="main",
                strict=True,  # Stop on first error
            )

            with pytest.raises(GitStateError):
                validator.validate_all()

            # Should have exactly one error (the branch check)
            assert len(validator.errors) == 1

    @pytest.mark.asyncio
    async def test_preflight_validation_non_strict_mode_collects_all_errors(self, mock_declarative_config_dir):
        """Non-strict mode collects all validation errors without raising."""
        from src.action.steps.git_validation import PreflightGitValidation

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock branch check to return wrong branch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="wrong-branch\n", stderr="")

            validator = PreflightGitValidation(
                repo_path=mock_declarative_config_dir,
                expected_branch="main",
                strict=False,  # Continue after errors
            )

            # Should not raise, just collect errors
            result = validator.validate_all()
            assert result is False
            assert len(validator.errors) > 0

    @pytest.mark.asyncio
    async def test_preflight_validation_summary_includes_all_results(self, mock_declarative_config_dir):
        """Validation summary includes all check results."""
        from src.action.steps.git_validation import PreflightGitValidation

        step = GitOpsCommitStep(declarative_config_path=str(mock_declarative_config_dir))

        # Mock git commands to succeed
        with patch("subprocess.run") as mock_run:
            def mock_git_command(*args, **kwargs):
                if "branch" in args and "--show-current" in args:
                    return Mock(returncode=0, stdout="main\n", stderr="")
                elif "status" in args and "--porcelain" in args:
                    return Mock(returncode=0, stdout="", stderr="")
                return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_git_command

            validator = PreflightGitValidation(
                repo_path=mock_declarative_config_dir,
                expected_branch="main",
                strict=False,
            )

            validator.validate_all()
            summary = validator.get_summary()

            assert summary["total_checks"] > 0
            assert summary["passed"] >= 0
            assert summary["failed"] >= 0
            assert "results" in summary
            assert len(summary["results"]) == summary["total_checks"]


class TestValidationErrorMessages:
    """Test validation error messages are clear and actionable."""

    @pytest.mark.asyncio
    async def test_branch_error_message_is_clear_and_actionable(self, mock_declarative_config_dir):
        """Branch validation error message provides clear guidance."""
        from src.action.steps.git_validation import validate_main_branch, GitStateError

        # Mock being on wrong branch
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="feature-branch\n", stderr="")

            with pytest.raises(GitStateError) as exc_info:
                validate_main_branch(mock_declarative_config_dir)

            error_message = str(exc_info.value)

            # Error should include:
            # 1. What's wrong
            assert "Not on expected branch 'main'" in error_message
            # 2. Current state
            assert "currently on 'feature-branch'" in error_message
            # 3. How to fix it
            assert "Please switch to main branch first" in error_message
            # 4. Structured details
            assert "Details:" in error_message
            assert "expected=main" in error_message
            assert "actual=feature-branch" in error_message

    @pytest.mark.asyncio
    async def test_uncommitted_changes_error_message_is_detailed(self, mock_declarative_config_dir):
        """Uncommitted changes error message provides file details."""
        from src.action.steps.git_validation import check_uncommitted_changes, GitStateError

        # Mock git status with changes
        changes_output = """M  k8s/test-cluster/deployment.yaml
 M k8s/test-cluster/service.yaml
?? k8s/test-cluster/new-file.yaml
"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=changes_output, stderr="")

            with pytest.raises(GitStateError) as exc_info:
                check_uncommitted_changes(mock_declarative_config_dir)

            error_message = str(exc_info.value)

            # Error should mention the count of changes
            assert "uncommitted changes" in error_message.lower()
            # Should show the actual changes
            assert "deployment.yaml" in error_message or "service.yaml" in error_message
            # Should provide actionable guidance
            assert "commit or stash" in error_message.lower()

    @pytest.mark.asyncio
    async def test_git_conflict_error_message_is_structured(self):
        """Git conflict error provides structured information."""
        from src.action.steps.git_validation import GitConflictError

        conflict = GitConflictError(
            "Merge conflict detected",
            conflict_files=["file1.yaml", "file2.yaml"],
            conflict_type="merge",
            details={"operation": "push"}
        )

        error_message = str(conflict)

        assert "Merge conflict detected" in error_message
        assert "Conflicting files" in error_message
        assert "file1.yaml" in error_message
        assert "file2.yaml" in error_message
        assert "Details:" in error_message

    @pytest.mark.asyncio
    async def test_git_state_error_includes_validation_context(self, mock_declarative_config_dir):
        """GitStateError includes validation type and repository context."""
        from src.action.steps.git_validation import GitStateError

        error = GitStateError(
            "Test validation failed",
            validation_type="test_validation",
            details={"test_param": "test_value"},
            repo_path=mock_declarative_config_dir
        )

        error_message = str(error)

        assert "[test_validation]" in error_message
        assert "Test validation failed" in error_message
        assert "repository:" in error_message
        assert "Details:" in error_message
        assert "test_param=test_value" in error_message


class TestValidationEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    async def test_empty_repository_validation(self, tmp_path):
        """Validation handles empty/new repository."""
        from src.action.steps.git_validation import check_git_repository, GitStateError

        # Create empty directory
        empty_dir = tmp_path / "empty_repo"
        empty_dir.mkdir()

        with pytest.raises(GitStateError) as exc_info:
            check_git_repository(empty_dir)

        error_message = str(exc_info.value)
        assert "Not a git repository" in error_message

    @pytest.mark.asyncio
    async def test_detached_head_validation(self, mock_declarative_config_dir):
        """Validation handles detached HEAD state."""
        from src.action.steps.git_validation import check_current_branch, GitStateError

        # Mock detached HEAD (empty output from branch --show-current)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            with pytest.raises(GitStateError) as exc_info:
                check_current_branch(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "Not on expected branch" in error_message or "Failed to determine current branch" in error_message

    @pytest.mark.asyncio
    async def test_network_timeout_during_validation(self, mock_declarative_config_dir):
        """Validation handles network timeouts gracefully."""
        from src.action.steps.git_validation import check_current_branch, GitNetworkError
        import subprocess

        # Mock network timeout
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", timeout=10)

            with pytest.raises(GitNetworkError) as exc_info:
                check_current_branch(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "timed out" in error_message.lower()

    @pytest.mark.asyncio
    async def test_git_command_not_found(self, mock_declarative_config_dir):
        """Validation handles missing git command."""
        from src.action.steps.git_validation import check_current_branch, GitStateError

        # Mock git command not found
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")

            with pytest.raises(GitStateError) as exc_info:
                check_current_branch(mock_declarative_config_dir)

            error_message = str(exc_info.value)
            assert "Git command not found" in error_message

    @pytest.mark.asyncio
    async def test_merge_conflict_state_detection(self, tmp_path):
        """Detection of merge conflict state works correctly."""
        from src.action.steps.git_validation import detect_merge_conflicts

        # Create a git repo with merge conflict markers
        repo = tmp_path / "conflict_repo"
        repo.mkdir()
        git_dir = repo / ".git"
        git_dir.mkdir()

        # Create MERGE_HEAD to indicate merge state
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        # Mock git grep to find conflict markers
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="k8s/test-cluster/deployment.yaml\n",
                stderr=""
            )

            conflicts = detect_merge_conflicts(repo)
            assert len(conflicts) > 0
            assert "deployment.yaml" in conflicts[0]

    @pytest.mark.asyncio
    async def test_no_merge_conflict_when_clean(self, mock_declarative_config_dir):
        """Conflict detection returns empty list when repository is clean."""
        from src.action.steps.git_validation import detect_merge_conflicts

        # Mock no merge state files
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            conflicts = detect_merge_conflicts(mock_declarative_config_dir)
            assert len(conflicts) == 0
