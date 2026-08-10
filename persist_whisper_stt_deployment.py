#!/usr/bin/env python3
"""
whisper-stt Deployment Data Persistence Module

This module provides functions to persist whisper-stt deployment data to JSON files
matching the pbx-web format structure.

Version: 1.0
Date: 2026-08-06
Bead ID: adc-5krd6

Usage:
    from persist_whisper_stt_deployment import (
        persist_deployment_data,
        load_deployment_data,
        validate_and_persist
    )

    # Save deployment data
    persist_deployment_data(deployment_dict, "whisper-stt-deployments-30d.json")

    # Load deployment data
    data = load_deployment_data("whisper-stt-deployments-30d.json")

    # Validate and persist with error handling
    success = validate_and_persist(deployment_dict)
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.utils.atomic_write import atomic_write

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Constants
# ============================================================================

DEFAULT_FILE_PATH = "whisper-stt-deployments-30d.json"
BACKUP_DIR = ".backups"
MAX_BACKUPS = 5


# ============================================================================
# Custom JSON Encoder for Complex Types
# ============================================================================

class DeploymentDataEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for deployment data that handles:
    - datetime objects (ISO 8601 format)
    - Enum types (converted to string values)
    - Path objects (converted to strings)
    - Complex nested objects
    """

    def default(self, obj: Any) -> Any:
        """
        Convert complex types to JSON-serializable formats.

        Args:
            obj: Object to serialize

        Returns:
            JSON-serializable representation of the object
        """
        # Handle datetime objects
        if isinstance(obj, datetime):
            return obj.isoformat() + 'Z' if obj.tzinfo else obj.isoformat()

        # Handle Enum types
        if hasattr(obj, 'value'):
            return obj.value

        # Handle Path objects
        if isinstance(obj, Path):
            return str(obj)

        # Handle objects with to_dict() method
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()

        # Handle dataclasses
        if hasattr(obj, '__dataclass_fields__'):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}

        # Fallback to string representation
        try:
            return str(obj)
        except Exception:
            return f"<unserializable {type(obj).__name__}>"


# ============================================================================
# File Management Utilities
# ============================================================================

def ensure_directory_exists(file_path: Union[str, Path]) -> None:
    """
    Ensure the directory for the file path exists.

    Args:
        file_path: Path to file (directory will be created if missing)

    Raises:
        OSError: If directory creation fails
    """
    path = Path(file_path)
    directory = path.parent

    if directory and not directory.exists():
        try:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {directory}")
        except OSError as e:
            logger.error(f"Failed to create directory {directory}: {e}")
            raise


def create_backup(file_path: Union[str, Path]) -> Optional[Path]:
    """
    Create a backup of existing file before overwriting.

    Args:
        file_path: Path to file to backup

    Returns:
        Path to backup file, or None if backup failed
    """
    source = Path(file_path)

    if not source.exists():
        logger.debug(f"No backup needed - file does not exist: {file_path}")
        return None

    try:
        # Create backup directory
        backup_dir = Path(BACKUP_DIR)
        backup_dir.mkdir(exist_ok=True)

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{source.stem}_backup_{timestamp}{source.suffix}"
        backup_path = backup_dir / backup_name

        # Stage the backup in the same directory, then publish it atomically so
        # readers never observe a partially copied backup file.
        import shutil
        temp_backup_path = backup_dir / f".{backup_name}.{uuid.uuid4()}.tmp"
        try:
            shutil.copy2(source, temp_backup_path)
            temp_backup_path.replace(backup_path)
        except BaseException:
            temp_backup_path.unlink(missing_ok=True)
            raise

        logger.info(f"Created backup: {backup_path}")

        # Clean up old backups (keep only MAX_BACKUPS)
        cleanup_old_backups(backup_dir, source.stem, MAX_BACKUPS)

        return backup_path

    except Exception as e:
        logger.error(f"Failed to create backup of {file_path}: {e}")
        return None


def cleanup_old_backups(backup_dir: Path, file_stem: str, keep_count: int) -> None:
    """
    Remove old backup files, keeping only the most recent ones.

    Uses atomic file operations with unique temp file handling and rollback.

    Args:
        backup_dir: Directory containing backups
        file_stem: Base name of files to consider for cleanup
        keep_count: Number of backups to keep

    Raises:
        OSError: If cleanup operations fail critically
    """
    try:
        # Find all backup files for this specific file
        pattern = f"{file_stem}_backup_*"
        backup_files = sorted(
            backup_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # Remove excess backups using an atomic claim followed by deletion.
        # The claim makes the original name disappear in one operation, so a
        # concurrent writer cannot replace a file after it was selected.
        failed_deletions = []
        for old_backup in backup_files[keep_count:]:
            temp_deletion_path = old_backup.parent / (
                f".deleting_{old_backup.name}.{uuid.uuid4()}.tmp"
            )
            claimed = False
            try:
                # Rename is the commit/claim point.  Only the owner of the
                # unique quarantine name may delete the claimed backup.
                old_backup.replace(temp_deletion_path)
                claimed = True

                # Deleting the quarantined path cannot affect a newly-created
                # backup at the original name.
                temp_deletion_path.unlink()

                logger.debug(f"Atomically removed old backup: {old_backup}")

            except FileNotFoundError:
                # Another owner may have won either the claim or deletion race.
                logger.debug(f"Backup already deleted: {old_backup}")
                continue
            except Exception as e:
                if claimed:
                    try:
                        # If deletion failed, restore the claimed backup so a
                        # cleanup error does not turn into silent data loss or
                        # leave a hidden .deleting temporary file behind.
                        temp_deletion_path.replace(old_backup)
                    except FileNotFoundError:
                        # A concurrent cleanup owner completed the deletion.
                        logger.debug(f"Backup already removed: {old_backup}")
                    except OSError as restore_error:
                        logger.error(
                            f"Failed to restore quarantined backup {old_backup}: "
                            f"{restore_error}"
                        )
                # Track failures but continue with other files
                failed_deletions.append((old_backup, str(e)))
                logger.warning(f"Failed to delete backup {old_backup}: {e}")

        # If any deletions failed, log summary but don't fail the operation
        if failed_deletions:
            logger.warning(
                f"Completed backup cleanup with {len(failed_deletions)} failures "
                f"out of {len(backup_files[keep_count:])} attempted deletions"
            )
        else:
            logger.debug(f"Successfully cleaned up {len(backup_files[keep_count:])} old backups")

    except Exception as e:
        logger.error(f"Critical failure during backup cleanup: {e}")
        raise OSError(f"Backup cleanup operation failed: {e}") from e


# ============================================================================
# Data Serialization Functions
# ============================================================================

def serialize_deployment_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure all data is properly serializable to JSON.

    Args:
        data: Raw deployment data dictionary

    Returns:
        Sanitized dictionary with all values JSON-serializable

    Raises:
        ValueError: If data structure is invalid
        TypeError: If data contains non-serializable types
    """
    try:
        # Create a deep copy to avoid mutating original
        serialized = json.loads(json.dumps(data, cls=DeploymentDataEncoder))

        # Validate required top-level structure
        required_keys = ['metadata', 'summary']
        for key in required_keys:
            if key not in serialized:
                raise ValueError(f"Missing required top-level key: {key}")

        # Validate metadata structure
        metadata = serialized.get('metadata', {})
        required_metadata_keys = ['generated_at', 'data_period_start', 'data_period_end']
        for key in required_metadata_keys:
            if key not in metadata:
                raise ValueError(f"Missing required metadata key: {key}")

        # Validate timestamp formats
        for ts_key in ['generated_at', 'data_period_start', 'data_period_end']:
            ts_str = metadata.get(ts_key)
            if ts_str:
                try:
                    # Validate ISO 8601 format
                    if ts_str.endswith('Z'):
                        datetime.fromisoformat(ts_str[:-1] + '+00:00')
                    else:
                        datetime.fromisoformat(ts_str)
                except ValueError as e:
                    raise ValueError(f"Invalid timestamp format for {ts_key}: {ts_str}") from e

        return serialized

    except json.JSONDecodeError as e:
        raise TypeError(f"Data contains non-JSON-serializable values: {e}") from e
    except Exception as e:
        raise ValueError(f"Data serialization failed: {e}") from e


# ============================================================================
# Main Persistence Functions
# ============================================================================

def persist_deployment_data(
    data: Dict[str, Any],
    file_path: Union[str, Path] = DEFAULT_FILE_PATH,
    backup_enabled: bool = True,
    pretty_print: bool = True,
    validate_before_write: bool = True
) -> bool:
    """
    Persist deployment data to JSON file.

    Args:
        data: Deployment data dictionary matching the schema
        file_path: Target file path (default: whisper-stt-deployments-30d.json)
        backup_enabled: Whether to create backup of existing file (default: True)
        pretty_print: Whether to format JSON with indentation (default: True)
        validate_before_write: Whether to validate data structure (default: True)

    Returns:
        True if persistence succeeded, False otherwise

    Raises:
        ValueError: If data validation fails (when validate_before_write=True)
        OSError: If file operations fail
        TypeError: If data contains non-serializable types
    """
    try:
        logger.info(f"Persisting deployment data to {file_path}")

        # Validate and serialize data
        if validate_before_write:
            serialized_data = serialize_deployment_data(data)
            logger.info("✓ Data validation passed")
        else:
            serialized_data = data

        # Ensure target directory exists
        ensure_directory_exists(file_path)

        # Create backup of existing file
        if backup_enabled:
            backup_path = create_backup(file_path)
            if backup_path:
                logger.info(f"✓ Backup created: {backup_path}")

        # Prepare JSON dump parameters
        json_params = {
            'cls': DeploymentDataEncoder,
            'ensure_ascii': False
        }

        if pretty_print:
            json_params['indent'] = 2
        else:
            json_params['separators'] = (',', ':')

        # Publish the complete serialized snapshot atomically. Readers see the
        # previous file or the complete replacement, never a partial JSON file.
        target_path = Path(file_path)
        atomic_write(target_path, json.dumps(serialized_data, **json_params))

        # Verify write was successful
        if target_path.exists() and target_path.stat().st_size > 0:
            logger.info(f"✓ Successfully persisted {target_path.stat().st_size} bytes to {file_path}")
            return True
        else:
            logger.error(f"File write verification failed for {file_path}")
            return False

    except ValueError as e:
        logger.error(f"Data validation failed: {e}")
        raise
    except OSError as e:
        logger.error(f"File operation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during persistence: {e}")
        return False


def load_deployment_data(
    file_path: Union[str, Path] = DEFAULT_FILE_PATH,
    validate_on_load: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Load deployment data from JSON file.

    Args:
        file_path: Path to JSON file (default: whisper-stt-deployments-30d.json)
        validate_on_load: Whether to validate data structure (default: True)

    Returns:
        Deployment data dictionary, or None if loading failed

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file contains invalid JSON
        ValueError: If data validation fails (when validate_on_load=True)
    """
    try:
        logger.info(f"Loading deployment data from {file_path}")

        target_path = Path(file_path)

        if not target_path.exists():
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"Deployment data file not found: {file_path}")

        # Read and parse JSON
        with target_path.open('r', encoding='utf-8') as f:
            data = json.load(f)

        logger.info(f"✓ Loaded {target_path.stat().st_size} bytes from {file_path}")

        # Validate data structure
        if validate_on_load:
            # Use serialization to validate structure
            serialized = serialize_deployment_data(data)
            logger.info("✓ Data validation passed")
            return serialized
        else:
            return data

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        raise
    except ValueError as e:
        logger.error(f"Data validation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during loading: {e}")
        return None


def validate_and_persist(
    data: Dict[str, Any],
    file_path: Union[str, Path] = DEFAULT_FILE_PATH
) -> bool:
    """
    Validate and persist deployment data with comprehensive error handling.

    This is a convenience function that combines validation, backup creation,
    and persistence with proper error handling.

    Args:
        data: Deployment data dictionary
        file_path: Target file path (default: whisper-stt-deployments-30d.json)

    Returns:
        True if both validation and persistence succeeded, False otherwise
    """
    try:
        # Validate data structure
        serialized = serialize_deployment_data(data)
        logger.info("✓ Data validation passed")

        # Persist with backup
        success = persist_deployment_data(
            serialized,
            file_path=file_path,
            create_backup=True,
            pretty_print=True,
            validate_before_write=False  # Already validated
        )

        return success

    except Exception as e:
        logger.error(f"validate_and_persist failed: {e}")
        return False


# ============================================================================
# Data Transformation Utilities
# ============================================================================

def transform_raw_data_to_schema(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform raw deployment data into the standard schema format.

    This function can be used to convert data from various sources
    (kubectl output, API responses, etc.) into the standard schema format.

    Args:
        raw_data: Raw deployment data from any source

    Returns:
        Data dictionary matching the standard schema structure

    Raises:
        ValueError: If transformation fails due to invalid input data
    """
    try:
        # This is a placeholder for transformation logic
        # In practice, you'd implement specific transformations based on
        # the data source format

        # Example transformation:
        schema_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat() + 'Z',
                "data_period_start": raw_data.get("time_range_start", datetime.now().isoformat() + 'Z'),
                "data_period_end": raw_data.get("time_range_end", datetime.now().isoformat() + 'Z'),
                "services": raw_data.get("services", ["whisper-stt"]),
                "clusters": raw_data.get("clusters", ["ardenone-cluster"]),
                "data_sources": raw_data.get("data_sources", ["kubernetes"])
            },
            "argo_workflows": raw_data.get("argo_workflows", {}),
            "argo_cd": raw_data.get("argo_cd", {}),
            "cluster_deployments": raw_data.get("cluster_deployments", {}),
            "summary": raw_data.get("summary", {}),
            "notes": raw_data.get("notes", [])
        }

        return schema_data

    except Exception as e:
        raise ValueError(f"Data transformation failed: {e}") from e


def merge_deployment_data(
    base_data: Dict[str, Any],
    update_data: Dict[str, Any],
    merge_strategy: str = "update"
) -> Dict[str, Any]:
    """
    Merge two deployment data dictionaries.

    Args:
        base_data: Base deployment data
        update_data: New deployment data to merge
        merge_strategy: "update" (update fields), "replace" (replace sections),
                       or "append" (merge lists)

    Returns:
        Merged deployment data dictionary

    Raises:
        ValueError: If merge strategy is invalid
    """
    try:
        if merge_strategy == "replace":
            return update_data

        elif merge_strategy == "update":
            merged = base_data.copy()
            for key, value in update_data.items():
                if isinstance(value, dict) and key in merged:
                    merged[key].update(value)
                else:
                    merged[key] = value
            return merged

        elif merge_strategy == "append":
            merged = base_data.copy()
            for key, value in update_data.items():
                if isinstance(value, list) and key in merged and isinstance(merged[key], list):
                    merged[key].extend(value)
                elif isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
            return merged

        else:
            raise ValueError(f"Invalid merge strategy: {merge_strategy}")

    except Exception as e:
        raise ValueError(f"Data merge failed: {e}") from e


# ============================================================================
# Testing and Utilities
# ============================================================================

def verify_json_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Verify that a JSON file is valid and contains deployment data.

    Args:
        file_path: Path to JSON file

    Returns:
        Dictionary with verification results:
        {
            "valid": bool,
            "readable": bool,
            "size_bytes": int,
            "error": Optional[str],
            "structure_ok": bool,
            "missing_keys": List[str]
        }
    """
    result = {
        "valid": False,
        "readable": False,
        "size_bytes": 0,
        "error": None,
        "structure_ok": False,
        "missing_keys": []
    }

    try:
        path = Path(file_path)

        # Check file exists and get size
        if not path.exists():
            result["error"] = "File does not exist"
            return result

        result["size_bytes"] = path.stat().st_size

        # Try to read and parse JSON
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)

        result["readable"] = True

        # Check basic structure
        required_keys = ['metadata', 'summary']
        missing = [k for k in required_keys if k not in data]
        result["missing_keys"] = missing

        if not missing:
            result["structure_ok"] = True
            result["valid"] = True

    except json.JSONDecodeError as e:
        result["error"] = f"Invalid JSON: {e}"
    except Exception as e:
        result["error"] = f"Verification error: {e}"

    return result


# ============================================================================
# Main Function for Testing
# ============================================================================

def main():
    """Main function for testing and demonstration."""
    print("=" * 70)
    print("WHISPER-STT DEPLOYMENT DATA PERSISTENCE")
    print("=" * 70)

    # Create test data matching the schema
    test_data = {
        "metadata": {
            "generated_at": "2026-08-06T12:00:00Z",
            "data_period_start": "2026-07-07T00:00:00Z",
            "data_period_end": "2026-08-06T12:00:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes_replicasets", "argo_workflows"]
        },
        "argo_workflows": {
            "whisper_stt_build": {
                "template_name": "whisper-stt-build",
                "template_created": "2026-05-27T02:26:47Z",
                "workflow_runs_last_30_days": 0,
                "workflow_runs": []
            }
        },
        "argo_cd": {
            "whisper-stt": {
                "application_found": False,
                "applications": []
            }
        },
        "cluster_deployments": {
            "whisper-stt": {
                "namespace": "whisper-stt",
                "deployment_name": "whisper-stt",
                "created_at": "2026-05-01T17:26:49Z",
                "current_image": "ronaldraygun/whisper-stt:1.8.6",
                "current_replicas": 1,
                "last_updated": "2026-07-12T16:54:57Z",
                "replica_history": [],
                "deployments_last_30_days": 1,
                "successful_deployments": 1,
                "failed_deployments": 0,
                "deployment_versions": ["1.8.6"],
                "all_versions_in_history": ["1.8.6"]
            }
        },
        "summary": {
            "total_deployments_last_30_days": 1,
            "whisper_stt_deployments": 1,
            "successful_deployments": 1,
            "failed_or_scaled_down": 0,
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        },
        "notes": ["Test data for persistence module"]
    }

    # Test persistence
    test_file = "test_whisper_stt_deployments.json"
    print(f"\nTesting persistence to {test_file}...")

    try:
        # Persist test data
        success = persist_deployment_data(test_data, test_file)

        if success:
            print(f"✓ Successfully persisted to {test_file}")

            # Verify file
            verification = verify_json_file(test_file)
            print("\nFile Verification:")
            print(f"  Valid: {verification['valid']}")
            print(f"  Size: {verification['size_bytes']} bytes")
            print(f"  Structure OK: {verification['structure_ok']}")

            # Load and verify
            loaded_data = load_deployment_data(test_file)
            if loaded_data:
                print(f"✓ Successfully loaded data from {test_file}")
                print(f"  - Metadata period: {loaded_data['metadata']['data_period_start']} to {loaded_data['metadata']['data_period_end']}")
                print(f"  - Services: {', '.join(loaded_data['metadata']['services'])}")

            # Cleanup test file
            Path(test_file).unlink()
            print("\n✓ Cleaned up test file")

            return 0
        else:
            print("✗ Persistence failed")
            return 1

    except Exception as e:
        print(f"✗ Error: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
