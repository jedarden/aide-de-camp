"""
Test infrastructure and mocking utilities for hot-reload edge case testing.

This module provides reusable utilities for testing hot-reload behavior under
various edge conditions including file system errors, concurrent access, and
race conditions.

Usage:
    from tests.helpers.hot_reload_test_infrastructure import (
        HotReloadTestBase,
        MockFileSystem,
        EdgeCaseScenario,
        create_test_registry,
        create_test_prompt_file,
    )

    class TestMyHotReload(HotReloadTestBase):
        async def test_permission_error(self):
            scenario = EdgeCaseScenario.permission_error()
            async with scenario.apply(self.reload_mgr):
                # Test permission error handling
                pass
"""

import os
import sys
import tempfile
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, ContextManager
from contextlib import contextmanager
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock
import yaml
import asyncio

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.components.hot_reload import HotReloadManager, Artifact


class HotReloadTestBase:
    """
    Base class for hot-reload edge case testing.

    Provides common setup/teardown, test utilities, and assertion helpers
    for testing hot-reload behavior under various edge conditions.

    Example:
        class MyHotReloadTests(HotReloadTestBase):
            async def test_my_scenario(self):
                async with self.temp_file_context() as temp_file:
                    self.reload_mgr.register_prompt('test', str(temp_file))
                    # Test logic here
    """

    def __init__(self):
        """Initialize the test base with a fresh hot-reload manager."""
        self.reload_mgr = HotReloadManager()
        self._temp_files: List[Path] = []
        self._temp_dirs: List[Path] = []
        self._original_permissions: Dict[Path, int] = {}
        self._lock = threading.Lock()

    def setup_method(self):
        """Setup method called before each test."""
        self.reload_mgr = HotReloadManager()
        self._temp_files = []
        self._temp_dirs = []
        self._original_permissions = {}

    def teardown_method(self):
        """
        Teardown method called after each test.

        Cleans up all temporary files and restores original permissions.
        """
        # Restore all original permissions
        for path, perms in self._original_permissions.items():
            try:
                if path.exists():
                    os.chmod(path, perms)
            except Exception:
                pass

        # Clean up temporary files
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    os.chmod(temp_file, 0o644)  # Ensure writable before deletion
                    temp_file.unlink()
            except Exception:
                pass

        # Clean up temporary directories
        for temp_dir in self._temp_dirs:
            try:
                if temp_dir.exists():
                    # Recursively make everything writable
                    for root, dirs, files in os.walk(temp_dir):
                        for d in dirs:
                            os.chmod(Path(root) / d, 0o755)
                        for f in files:
                            os.chmod(Path(root) / f, 0o644)
                    temp_dir.rmdir()
            except Exception:
                pass

    @contextmanager
    def temp_file_context(self, suffix: str = '.md', content: str = 'test content'):
        """
        Create a temporary file that is automatically cleaned up.

        Args:
            suffix: File extension (e.g., '.md', '.yaml')
            content: Initial content to write to the file

        Returns:
            Path to the temporary file
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            temp_path = Path(f.name)
            f.write(content)

        with self._lock:
            self._temp_files.append(temp_path)

        try:
            yield temp_path
        finally:
            # File will be cleaned up in teardown_method
            pass

    @contextmanager
    def temp_dir_context(self):
        """
        Create a temporary directory that is automatically cleaned up.

        Returns:
            Path to the temporary directory
        """
        temp_dir = Path(tempfile.mkdtemp())

        with self._lock:
            self._temp_dirs.append(temp_dir)

        try:
            yield temp_dir
        finally:
            # Directory will be cleaned up in teardown_method
            pass

    def set_readonly(self, path: Path):
        """
        Make a file read-only and remember original permissions.

        Args:
            path: Path to the file to make read-only
        """
        if path.exists():
            original_perms = os.stat(path).st_mode
            with self._lock:
                self._original_permissions[path] = original_perms
            os.chmod(path, 0o444)

    def set_unreadable(self, path: Path):
        """
        Make a file unreadable (no permissions) and remember original permissions.

        Args:
            path: Path to the file to make unreadable
        """
        if path.exists():
            original_perms = os.stat(path).st_mode
            with self._lock:
                self._original_permissions[path] = original_perms
            os.chmod(path, 0o000)

    def restore_permissions(self, path: Path):
        """
        Restore original permissions for a file.

        Args:
            path: Path to the file
        """
        if path in self._original_permissions:
            os.chmod(path, self._original_permissions[path])

    def assert_artifact_loaded(self, name: str):
        """
        Assert that an artifact was successfully loaded.

        Args:
            name: Artifact name

        Raises:
            AssertionError: If artifact not found or has load errors
        """
        assert name in self.reload_mgr._artifacts, f"Artifact '{name}' not registered"
        artifact = self.reload_mgr._artifacts[name]
        assert artifact.load_error is None, f"Artifact '{name}' has load error: {artifact.load_error}"

    def assert_artifact_error(self, name: str, error_type: type = Exception):
        """
        Assert that an artifact has a load error.

        Args:
            name: Artifact name
            error_type: Expected error type

        Raises:
            AssertionError: If artifact doesn't have expected error
        """
        assert name in self.reload_mgr._artifacts, f"Artifact '{name}' not registered"
        artifact = self.reload_mgr._artifacts[name]
        assert artifact.load_error is not None, f"Artifact '{name}' has no load error"
        assert isinstance(artifact.load_error, error_type), \
            f"Expected {error_type}, got {type(artifact.load_error)}"


@dataclass
class EdgeCaseScenario:
    """
    Represents a specific edge case scenario for testing.

    Scenarios can be applied to a HotReloadManager to test behavior under
    various error conditions.

    Example:
        scenario = EdgeCaseScenario.permission_error('/test/file.md')
        async with scenario.apply(reload_mgr):
            # Test behavior when file has permission errors
            content = reload_mgr.get_prompt('test')
    """

    name: str
    description: str
    setup_func: Callable[[HotReloadManager], None]
    cleanup_func: Callable[[HotReloadManager], None] = field(default=lambda mgr: None)
    expected_error: Optional[type] = None

    @contextmanager
    def apply(self, reload_mgr: HotReloadManager):
        """
        Apply this scenario to a hot-reload manager.

        Args:
            reload_mgr: The HotReloadManager to apply the scenario to

        Yields:
            The modified HotReloadManager
        """
        self.setup_func(reload_mgr)
        try:
            yield reload_mgr
        finally:
            self.cleanup_func(reload_mgr)

    @staticmethod
    def permission_error(file_path: Optional[Path] = None) -> 'EdgeCaseScenario':
        """
        Create a scenario where a file has permission errors.

        Args:
            file_path: Path to the file (creates temp file if None)

        Returns:
            EdgeCaseScenario configured for permission errors
        """
        temp_file = None
        original_perms = None

        def setup(reload_mgr: HotReloadManager):
            nonlocal temp_file, original_perms
            if file_path:
                temp_file = file_path
            else:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                    temp_file = Path(f.name)
                    f.write("test content")

            if temp_file.exists():
                original_perms = os.stat(temp_file).st_mode
                os.chmod(temp_file, 0o000)

        def cleanup(reload_mgr: HotReloadManager):
            if temp_file and original_perms and temp_file.exists():
                os.chmod(temp_file, original_perms)
            if not file_path and temp_file and temp_file.exists():
                temp_file.unlink()

        return EdgeCaseScenario(
            name="permission_error",
            description="File becomes unreadable due to permission changes",
            setup_func=setup,
            cleanup_func=cleanup,
            expected_error=(PermissionError, OSError)
        )

    @staticmethod
    def missing_file(file_path: Optional[Path] = None) -> 'EdgeCaseScenario':
        """
        Create a scenario where a file doesn't exist.

        Args:
            file_path: Path to the non-existent file

        Returns:
            EdgeCaseScenario configured for missing file
        """
        target_path = file_path or Path("/tmp/does_not_exist_test_xyz123.md")

        def setup(reload_mgr: HotReloadManager):
            # Ensure file doesn't exist
            if target_path.exists():
                target_path.unlink()

        def cleanup(reload_mgr: HotReloadManager):
            # No cleanup needed
            pass

        return EdgeCaseScenario(
            name="missing_file",
            description="File doesn't exist at registration time",
            setup_func=setup,
            cleanup_func=cleanup,
            expected_error=FileNotFoundError
        )

    @staticmethod
    def malformed_yaml(file_path: Optional[Path] = None) -> 'EdgeCaseScenario':
        """
        Create a scenario with malformed YAML content.

        Args:
            file_path: Path to the file (creates temp file if None)

        Returns:
            EdgeCaseScenario configured for malformed YAML
        """
        temp_file = None

        def setup(reload_mgr: HotReloadManager):
            nonlocal temp_file
            if file_path:
                temp_file = file_path
            else:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                    temp_file = Path(f.name)
                    # Write malformed YAML
                    f.write("""
invalid_yaml:
  - item1
    item2  # Bad indentation
  - key: value
    bad_bracket: [unclosed
""")

        def cleanup(reload_mgr: HotReloadManager):
            if temp_file and temp_file.exists():
                temp_file.unlink()

        return EdgeCaseScenario(
            name="malformed_yaml",
            description="YAML file has invalid syntax",
            setup_func=setup,
            cleanup_func=cleanup,
            expected_error=(yaml.YAMLError, ValueError)
        )

    @staticmethod
    def race_condition(file_path: Optional[Path] = None) -> 'EdgeCaseScenario':
        """
        Create a scenario with concurrent file modifications.

        Args:
            file_path: Path to the file (creates temp file if None)

        Returns:
            EdgeCaseScenario configured for race conditions
        """
        temp_file = None
        stop_modification = False
        modifier_thread = None

        def setup(reload_mgr: HotReloadManager):
            nonlocal temp_file, stop_modification, modifier_thread
            if file_path:
                temp_file = file_path
            else:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                    temp_file = Path(f.name)
                    f.write("Initial content")

            # Start background thread that modifies the file rapidly
            def rapid_modifier():
                nonlocal stop_modification
                for i in range(100):
                    if stop_modification:
                        break
                    try:
                        with open(temp_file, 'w') as f:
                            f.write(f"Modified {i}")
                        time.sleep(0.001)
                    except Exception:
                        pass

            modifier_thread = threading.Thread(target=rapid_modifier, daemon=True)
            modifier_thread.start()

        def cleanup(reload_mgr: HotReloadManager):
            nonlocal stop_modification
            stop_modification = True
            if modifier_thread:
                modifier_thread.join(timeout=2.0)
            if not file_path and temp_file and temp_file.exists():
                temp_file.unlink()

        return EdgeCaseScenario(
            name="race_condition",
            description="File is modified concurrently during access",
            setup_func=setup,
            cleanup_func=cleanup,
            expected_error=None  # May or may not error
        )

    @staticmethod
    def empty_file(file_path: Optional[Path] = None, file_type: str = 'md') -> 'EdgeCaseScenario':
        """
        Create a scenario with an empty file.

        Args:
            file_path: Path to the file (creates temp file if None)
            file_type: Type of file ('md' or 'yaml')

        Returns:
            EdgeCaseScenario configured for empty file
        """
        temp_file = None
        suffix = '.yaml' if file_type == 'yaml' else '.md'

        def setup(reload_mgr: HotReloadManager):
            nonlocal temp_file
            if file_path:
                temp_file = file_path
            else:
                with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
                    temp_file = Path(f.name)
                    # File is created empty

        def cleanup(reload_mgr: HotReloadManager):
            if not file_path and temp_file and temp_file.exists():
                temp_file.unlink()

        return EdgeCaseScenario(
            name="empty_file",
            description="File is completely empty",
            setup_func=setup,
            cleanup_func=cleanup,
            expected_error=None  # Empty files are valid
        )


class MockFileSystem:
    """
    Mock file system utilities for testing file operations.

    Provides controlled simulation of file system errors and conditions
    without actual file system manipulation.

    Example:
        mock_fs = MockFileSystem()
        mock_fs.add_file('/test/file.md', 'content')
        mock_fs.set_permission_error('/test/file.md')

        with patch('pathlib.Path.open', mock_fs.mock_open()):
            content = Path('/test/file.md').read_text()
    """

    def __init__(self):
        """Initialize an empty mock file system."""
        self._files: Dict[Path, str] = {}
        self._permissions: Dict[Path, int] = {}
        self._errors: Dict[Path, Exception] = {}

    def add_file(self, path: str, content: str = 'test content'):
        """
        Add a file to the mock file system.

        Args:
            path: Path to the file
            content: File content
        """
        self._files[Path(path)] = content
        self._permissions[Path(path)] = 0o644

    def set_permission_error(self, path: str):
        """
        Make a file raise PermissionError on access.

        Args:
            path: Path to the file
        """
        self._errors[Path(path)] = PermissionError(f"Permission denied: {path}")

    def set_not_found_error(self, path: str):
        """
        Make a file raise FileNotFoundError on access.

        Args:
            path: Path to the file
        """
        self._errors[Path(path)] = FileNotFoundError(f"No such file: {path}")

    def mock_open(self, path: Path, *args, **kwargs):
        """
        Mock implementation of file open.

        Args:
            path: Path to open

        Returns:
            Mock file object

        Raises:
            FileNotFoundError: If file not found or error is set
            PermissionError: If permission error is set
        """
        if path in self._errors:
            raise self._errors[path]

        if path not in self._files:
            raise FileNotFoundError(f"No such file: {path}")

        return StringIO(self._files[path])

    def mock_stat(self, path: Path):
        """
        Mock implementation of file stat.

        Args:
            path: Path to stat

        Returns:
            Mock stat object

        Raises:
            FileNotFoundError: If file not found or error is set
        """
        if path in self._errors:
            raise self._errors[path]

        if path not in self._files:
            raise FileNotFoundError(f"No such file: {path}")

        mock_stat = MagicMock()
        mock_stat.st_mtime = time.time()
        mock_stat.st_mode = self._permissions.get(path, 0o644)
        return mock_stat


class StringIO:
    """Simple StringIO implementation for mock file objects."""

    def __init__(self, content: str):
        """Initialize with content."""
        self._content = content
        self._pos = 0

    def read(self):
        """Read all content."""
        return self._content

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        pass


def create_test_registry(projects: Optional[Dict] = None, clusters: Optional[Dict] = None) -> Path:
    """
    Create a temporary test registry.yaml file.

    Args:
        projects: Projects section (uses default if None)
        clusters: Clusters section (uses default if None)

    Returns:
        Path to the temporary registry file

    Example:
        registry_path = create_test_registry()
        reload_mgr.register_config('test_registry', str(registry_path))
        # Registry will be cleaned up automatically
    """
    default_projects = {
        'test-project': {
            'slug': 'test-project',
            'name': 'Test Project',
            'aliases': ['test'],
            'repository': 'github.com/test/repo'
        }
    }

    default_clusters = {
        'test-cluster': {
            'context': 'test-cluster',
            'namespace': 'default'
        }
    }

    registry_content = {
        'projects': projects or default_projects,
        'clusters': clusters or default_clusters
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
        yaml.dump(registry_content, f)
        return temp_path


def create_test_prompt_file(name: str = 'test', content: Optional[str] = None) -> Path:
    """
    Create a temporary test prompt file.

    Args:
        name: Name for the prompt (used in content if content is None)
        content: Prompt content (generates default if None)

    Returns:
        Path to the temporary prompt file

    Example:
        prompt_path = create_test_prompt_file('router')
        reload_mgr.register_prompt('test_router', str(prompt_path))
        # File will be cleaned up automatically
    """
    if content is None:
        content = f"# {name.capitalize()} Prompt\n\nThis is a test prompt for {name}.\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        temp_path = Path(f.name)
        f.write(content)
        return temp_path


def create_test_config_file(name: str = 'test', config: Optional[Dict] = None) -> Path:
    """
    Create a temporary test config file.

    Args:
        name: Name for the config
        config: Configuration dictionary (generates default if None)

    Returns:
        Path to the temporary config file

    Example:
        config_path = create_test_config_file('monitoring')
        reload_mgr.register_config('test_monitoring', str(config_path))
        # File will be cleaned up automatically
    """
    if config is None:
        config = {
            'name': name,
            'version': '1.0.0',
            'settings': {
                'enabled': True,
                'timeout': 30
            }
        }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_path = Path(f.name)
        yaml.dump(config, f)
        return temp_path


def setup_permission_error_scenario(base_dir: Optional[Path] = None) -> tuple[Path, Callable]:
    """
    Setup a scenario with permission-related file errors.

    Args:
        base_dir: Base directory for test files (creates temp dir if None)

    Returns:
        Tuple of (base_dir, cleanup_function)

    Example:
        base_dir, cleanup = setup_permission_error_scenario()
        try:
            readonly_file = base_dir / 'readonly.md'
            reload_mgr.register_prompt('test', str(readonly_file))
        finally:
            cleanup()
    """
    if base_dir is None:
        base_dir = Path(tempfile.mkdtemp())

    # Create a test file
    test_file = base_dir / 'test.md'
    test_file.write_text('test content')

    # Make it read-only
    original_perms = os.stat(test_file).st_mode
    os.chmod(test_file, 0o444)

    def cleanup():
        """Restore permissions and clean up."""
        try:
            os.chmod(test_file, original_perms)
        except Exception:
            pass
        try:
            if base_dir.exists():
                test_file.unlink()
                base_dir.rmdir()
        except Exception:
            pass

    return base_dir, cleanup


def setup_missing_file_scenario(base_dir: Optional[Path] = None) -> tuple[Path, Callable]:
    """
    Setup a scenario with missing files.

    Args:
        base_dir: Base directory (creates temp dir if None)

    Returns:
        Tuple of (base_dir, cleanup_function)

    Example:
        base_dir, cleanup = setup_missing_file_scenario()
        missing_file = base_dir / 'does_not_exist.md'
        # Test with missing_file
        cleanup()
    """
    if base_dir is None:
        base_dir = Path(tempfile.mkdtemp())

    def cleanup():
        """Clean up temp directory."""
        try:
            if base_dir.exists():
                base_dir.rmdir()
        except Exception:
            pass

    return base_dir, cleanup


class ConcurrentAccessTracker:
    """
    Track concurrent access patterns during testing.

    Records all access attempts with timing and success/failure status
    to help identify race conditions and concurrency issues.

    Example:
        tracker = ConcurrentAccessTracker()
        async def access_artifact(name):
            try:
                with tracker.track_access('read', name):
                    content = reload_mgr.get_prompt(name)
            except Exception as e:
                tracker.record_error(name, e)
    """

    def __init__(self):
        """Initialize an empty tracker."""
        self._access_log: List[Dict] = []
        self._errors: List[Dict] = []
        self._lock = threading.Lock()

    @contextmanager
    def track_access(self, operation: str, artifact_name: str):
        """
        Track an access operation.

        Args:
            operation: Type of operation ('read', 'write', 'check_mtime')
            artifact_name: Name of the artifact being accessed

        Yields:
            None
        """
        start_time = time.time()
        access_id = len(self._access_log)

        with self._lock:
            self._access_log.append({
                'id': access_id,
                'operation': operation,
                'artifact': artifact_name,
                'start_time': start_time,
                'thread_id': threading.get_ident(),
                'success': False
            })

        try:
            yield
            end_time = time.time()

            with self._lock:
                self._access_log[access_id]['end_time'] = end_time
                self._access_log[access_id]['duration'] = end_time - start_time
                self._access_log[access_id]['success'] = True
        except Exception as e:
            end_time = time.time()
            with self._lock:
                self._access_log[access_id]['end_time'] = end_time
                self._access_log[access_id]['duration'] = end_time - start_time
                self._access_log[access_id]['success'] = False
                self._access_log[access_id]['error'] = str(e)
            raise

    def record_error(self, artifact_name: str, error: Exception):
        """
        Record an error during artifact access.

        Args:
            artifact_name: Name of the artifact
            error: The exception that occurred
        """
        with self._lock:
            self._errors.append({
                'artifact': artifact_name,
                'error_type': type(error).__name__,
                'error_message': str(error),
                'timestamp': time.time(),
                'thread_id': threading.get_ident()
            })

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about tracked accesses.

        Returns:
            Dictionary with access statistics
        """
        with self._lock:
            total_accesses = len(self._access_log)
            successful_accesses = sum(1 for a in self._access_log if a['success'])
            failed_accesses = total_accesses - successful_accesses

            durations = [a.get('duration', 0) for a in self._access_log if 'duration' in a]
            avg_duration = sum(durations) / len(durations) if durations else 0
            max_duration = max(durations) if durations else 0

            # Check for overlapping accesses (potential race conditions)
            overlapping = 0
            for i, access1 in enumerate(self._access_log):
                for access2 in self._access_log[i+1:]:
                    if self._accesses_overlap(access1, access2):
                        overlapping += 1

            return {
                'total_accesses': total_accesses,
                'successful_accesses': successful_accesses,
                'failed_accesses': failed_accesses,
                'error_count': len(self._errors),
                'avg_duration': avg_duration,
                'max_duration': max_duration,
                'overlapping_accesses': overlapping
            }

    @staticmethod
    def _accesses_overlap(access1: Dict, access2: Dict) -> bool:
        """Check if two accesses overlapped in time."""
        if 'start_time' not in access1 or 'end_time' not in access1:
            return False
        if 'start_time' not in access2 or 'end_time' not in access2:
            return False

        return not (access1['end_time'] <= access2['start_time'] or
                   access2['end_time'] <= access1['start_time'])

    def summary(self) -> str:
        """
        Generate a human-readable summary.

        Returns:
            Summary string
        """
        stats = self.get_statistics()
        lines = [
            "Concurrent Access Tracker Summary:",
            f"  Total accesses: {stats['total_accesses']}",
            f"  Successful: {stats['successful_accesses']}",
            f"  Failed: {stats['failed_accesses']}",
            f"  Errors: {stats['error_count']}",
            f"  Avg duration: {stats['avg_duration']:.4f}s",
            f"  Max duration: {stats['max_duration']:.4f}s",
            f"  Overlapping accesses: {stats['overlapping_accesses']}",
        ]
        return "\n".join(lines)


# Export key classes and functions
__all__ = [
    'HotReloadTestBase',
    'EdgeCaseScenario',
    'MockFileSystem',
    'create_test_registry',
    'create_test_prompt_file',
    'create_test_config_file',
    'setup_permission_error_scenario',
    'setup_missing_file_scenario',
    'ConcurrentAccessTracker',
]
