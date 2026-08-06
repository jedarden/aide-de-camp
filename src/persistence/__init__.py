"""
Persistence module for aide-de-camp

Handles data persistence to JSON files with proper error handling,
serialization, and file management.
"""

from .deployment_persistence import (
    persist_deployment_data,
    load_deployment_data,
    verify_persistence,
    list_deployment_files,
    DeploymentPersistenceError,
    get_default_path
)

__all__ = [
    "persist_deployment_data",
    "load_deployment_data",
    "verify_persistence",
    "list_deployment_files",
    "DeploymentPersistenceError",
    "get_default_path",
]
