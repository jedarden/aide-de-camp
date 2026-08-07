"""
Test helpers package for aide-de-camp test infrastructure.

This package provides reusable utilities for common test patterns.
"""

from tests.helpers.registry_test_helpers import (
    backup_registry,
    restore_registry,
    cleanup_backup,
    RegistryModificationContext,
    get_registry_content,
    set_registry_content,
)

from tests.helpers.hot_reload_test_infrastructure import (
    HotReloadTestBase,
    EdgeCaseScenario,
    MockFileSystem,
    create_test_registry,
    create_test_prompt_file,
    create_test_config_file,
    setup_permission_error_scenario,
    setup_missing_file_scenario,
    ConcurrentAccessTracker,
)

__all__ = [
    # Registry helpers
    "backup_registry",
    "restore_registry",
    "cleanup_backup",
    "RegistryModificationContext",
    "get_registry_content",
    "set_registry_content",
    # Hot-reload test infrastructure
    "HotReloadTestBase",
    "EdgeCaseScenario",
    "MockFileSystem",
    "create_test_registry",
    "create_test_prompt_file",
    "create_test_config_file",
    "setup_permission_error_scenario",
    "setup_missing_file_scenario",
    "ConcurrentAccessTracker",
]
