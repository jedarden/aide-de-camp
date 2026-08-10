"""
Deployment Data Persistence Module

Handles reading and writing deployment data to JSON files with proper
serialization, error handling, and validation.

Matches pbx-web deployment data structure for comparative analysis.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pydantic import ValidationError

from src.schemas.whisper_stt_deployment import WhisperSTTDeploymentData, validate_deployment_data
from src.utils.atomic_write import atomic_write

logger = logging.getLogger(__name__)


class DeploymentPersistenceError(Exception):
    """Custom exception for deployment persistence operations"""

    def __init__(self, message: str, filepath: Optional[str] = None,
                 original_error: Optional[Exception] = None):
        self.message = message
        self.filepath = filepath
        self.original_error = original_error
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        base = f"DeploymentPersistenceError: {self.message}"
        if self.filepath:
            base += f" (file: {self.filepath})"
        if self.original_error:
            base += f" | Caused by: {type(self.original_error).__name__}: {self.original_error}"
        return base


def get_default_path(service_name: str = "whisper-stt", days: int = 30) -> str:
    """
    Get the default file path for deployment data

    Args:
        service_name: Service name (default: "whisper-stt")
        days: Analysis period in days (default: 30)

    Returns:
        str: Default file path for deployment data JSON
    """
    filename = f"{service_name}-deployments-{days}d.json"
    # Use the project root directory
    project_root = Path(__file__).parent.parent.parent
    return str(project_root / filename)


def ensure_directory_exists(filepath: Union[str, Path]) -> None:
    """
    Ensure the directory for a file path exists

    Args:
        filepath: Path to file (directory will be created if needed)

    Raises:
        DeploymentPersistenceError: If directory creation fails
    """
    try:
        path = Path(filepath)
        directory = path.parent
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise DeploymentPersistenceError(
            f"Failed to create directory for {filepath}",
            filepath=str(filepath),
            original_error=e
        )


def serialize_datetime(obj: Any) -> Any:
    """
    JSON serializer for datetime objects and other non-serializable types

    Args:
        obj: Object to serialize

    Returns:
        JSON-serializable representation
    """
    if isinstance(obj, datetime):
        return obj.isoformat() + 'Z'
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    return str(obj)


def persist_deployment_data(
    data: Union[WhisperSTTDeploymentData, Dict[str, Any]],
    filepath: Optional[str] = None,
    service_name: str = "whisper-stt",
    days: int = 30,
    indent: int = 2,
    create_backup: bool = True
) -> str:
    """
    Persist deployment data to JSON file

    Args:
        data: Deployment data (Pydantic model or dict)
        filepath: Target file path (optional, uses default if None)
        service_name: Service name for default path (default: "whisper-stt")
        days: Analysis period in days for default path (default: 30)
        indent: JSON indentation spaces (default: 2)
        create_backup: Create .backup file before writing (default: True)

    Returns:
        str: Path to written file

    Raises:
        DeploymentPersistenceError: If persistence fails
        ValidationError: If data doesn't match schema
    """
    # Use default path if not provided
    if filepath is None:
        filepath = get_default_path(service_name, days)

    try:
        # Ensure directory exists
        ensure_directory_exists(filepath)

        # Validate and convert data
        if isinstance(data, WhisperSTTDeploymentData):
            # Use Pydantic's model_dump for proper serialization
            data_dict = data.model_dump()
        elif isinstance(data, dict):
            # Validate dict against schema
            validate_deployment_data(data)
            data_dict = data
        else:
            raise DeploymentPersistenceError(
                f"Unsupported data type: {type(data)}. "
                "Expected WhisperSTTDeploymentData or dict",
                filepath=filepath
            )

        # Create backup if requested and file exists
        if create_backup and Path(filepath).exists():
            backup_path = Path(f"{filepath}.backup")
            try:
                import shutil
                # Use atomic temp file + rename for backup creation
                temp_backup_path = Path(f"{filepath}.{uuid.uuid4()}.tmp_backup")
                shutil.copy2(filepath, temp_backup_path)
                # Atomic rename to final backup location
                temp_backup_path.replace(backup_path)
                logger.debug(f"Created backup: {backup_path}")
            except (OSError, IOError) as e:
                logger.warning(f"Failed to create backup for {filepath}: {e}")
                # Clean up temp backup if it exists - use idempotent cleanup
                if 'temp_backup_path' in locals():
                    try:
                        # Use missing_ok=True for idempotent cleanup (safe if
                        # another owner already removed the staging path).
                        # Avoid an exists() check, which is racy.
                        temp_backup_path.unlink(missing_ok=True)
                        logger.debug(f"Cleaned up temp backup file: {temp_backup_path}")
                    except OSError as cleanup_error:
                        # Preserve the backup failure while making cleanup
                        # failure observable for a later recovery sweep.
                        logger.error(
                            f"Failed to cleanup temp backup {temp_backup_path}: "
                            f"{cleanup_error}"
                        )

        # Write to file with atomic operations using atomic_write utility
        # Uses temp file + atomic rename pattern with unique naming (UUID4)
        try:
            atomic_write(
                filepath,
                json.dumps(
                    data_dict,
                    indent=indent,
                    ensure_ascii=False,
                    default=serialize_datetime
                )
            )
            logger.debug(f"Atomic write successful for {filepath}")
        except (OSError, PermissionError) as e:
            # Handle atomic write failures with context-specific error message
            error_msg = f"Atomic write failed for {filepath}: {type(e).__name__}: {e}"
            logger.error(error_msg)
            raise DeploymentPersistenceError(
                f"Atomic write operation failed: {e}",
                filepath=filepath,
                original_error=e
            ) from e
        except (TypeError, ValueError) as e:
            # Handle content validation errors
            error_msg = f"Content validation failed for atomic write to {filepath}: {e}"
            logger.error(error_msg)
            raise DeploymentPersistenceError(
                f"Content validation failed: {e}",
                filepath=filepath,
                original_error=e
            ) from e

        logger.info(f"Successfully persisted deployment data to: {filepath}")

        # Verify file was written correctly
        if not Path(filepath).exists():
            raise DeploymentPersistenceError(
                f"File not found after write: {filepath}",
                filepath=filepath
            )

        # Check file size is reasonable
        file_size = Path(filepath).stat().st_size
        if file_size == 0:
            raise DeploymentPersistenceError(
                f"Written file is empty: {filepath}",
                filepath=filepath
            )

        logger.debug(f"File size: {file_size} bytes")

        return filepath

    except ValidationError as e:
        raise DeploymentPersistenceError(
            f"Schema validation failed: {e}",
            filepath=filepath,
            original_error=e
        )
    except (IOError, OSError) as e:
        raise DeploymentPersistenceError(
            f"File I/O error: {e}",
            filepath=filepath,
            original_error=e
        )
    except Exception as e:
        raise DeploymentPersistenceError(
            f"Unexpected error during persistence: {e}",
            filepath=filepath,
            original_error=e
        )


def load_deployment_data(
    filepath: Optional[str] = None,
    service_name: str = "whisper-stt",
    days: int = 30,
    validate: bool = True
) -> WhisperSTTDeploymentData:
    """
    Load deployment data from JSON file

    Args:
        filepath: Source file path (optional, uses default if None)
        service_name: Service name for default path (default: "whisper-stt")
        days: Analysis period in days for default path (default: 30)
        validate: Validate data against schema (default: True)

    Returns:
        WhisperSTTDeploymentData: Loaded and validated deployment data

    Raises:
        DeploymentPersistenceError: If loading fails
        ValidationError: If validation fails and validate=True
    """
    # Use default path if not provided
    if filepath is None:
        filepath = get_default_path(service_name, days)

    try:
        # Check file exists
        path = Path(filepath)
        if not path.exists():
            raise DeploymentPersistenceError(
                f"File not found: {filepath}",
                filepath=filepath
            )

        # Check file is readable
        if not path.is_file():
            raise DeploymentPersistenceError(
                f"Path is not a file: {filepath}",
                filepath=filepath
            )

        # Check file size
        file_size = path.stat().st_size
        if file_size == 0:
            raise DeploymentPersistenceError(
                f"File is empty: {filepath}",
                filepath=filepath
            )

        logger.debug(f"Loading deployment data from: {filepath} ({file_size} bytes)")

        # Read and parse JSON
        with open(filepath, 'r', encoding='utf-8') as f:
            data_dict = json.load(f)

        if not isinstance(data_dict, dict):
            raise DeploymentPersistenceError(
                f"JSON root is not an object: {type(data_dict)}",
                filepath=filepath
            )

        # Validate if requested
        if validate:
            try:
                validated_data = WhisperSTTDeploymentData(**data_dict)
                logger.info(f"Successfully loaded and validated deployment data from: {filepath}")
                return validated_data
            except ValidationError as e:
                raise DeploymentPersistenceError(
                    f"Schema validation failed for loaded data: {e}",
                    filepath=filepath,
                    original_error=e
                )
        else:
            # Return raw dict
            logger.info(f"Successfully loaded deployment data from: {filepath} (validation skipped)")
            return data_dict

    except json.JSONDecodeError as e:
        raise DeploymentPersistenceError(
            f"Invalid JSON format: {e}",
            filepath=filepath,
            original_error=e
        )
    except (IOError, OSError) as e:
        raise DeploymentPersistenceError(
            f"File I/O error: {e}",
            filepath=filepath,
            original_error=e
        )
    except Exception as e:
        raise DeploymentPersistenceError(
            f"Unexpected error during loading: {e}",
            filepath=filepath,
            original_error=e
        )


def verify_persistence(
    data: Union[WhisperSTTDeploymentData, Dict[str, Any]],
    filepath: Optional[str] = None,
    service_name: str = "whisper-stt",
    days: int = 30
) -> bool:
    """
    Verify data was persisted correctly by writing and reading back

    Args:
        data: Original deployment data
        filepath: File path to verify (optional, uses default if None)
        service_name: Service name for default path (default: "whisper-stt")
        days: Analysis period in days (default: 30)

    Returns:
        bool: True if verification passes

    Raises:
        DeploymentPersistenceError: If verification fails
    """
    if filepath is None:
        filepath = get_default_path(service_name, days)

    try:
        # Load the persisted data
        loaded_data = load_deployment_data(filepath, service_name, days, validate=True)

        # Compare with original
        if isinstance(data, WhisperSTTDeploymentData):
            original_dict = data.model_dump()
        else:
            original_dict = data

        loaded_dict = loaded_data.model_dump()

        # Compare key fields
        if original_dict.get('metadata') != loaded_dict.get('metadata'):
            logger.warning("Metadata mismatch during verification")
            return False

        if original_dict.get('summary') != loaded_dict.get('summary'):
            logger.warning("Summary mismatch during verification")
            return False

        logger.info(f"Verification successful for: {filepath}")
        return True

    except Exception as e:
        raise DeploymentPersistenceError(
            f"Verification failed: {e}",
            filepath=filepath,
            original_error=e
        )


def list_deployment_files(
    directory: Optional[str] = None,
    pattern: str = "*-deployments-*.json"
) -> list[str]:
    """
    List deployment data files in directory

    Args:
        directory: Directory to search (default: project root)
        pattern: Glob pattern for matching files (default: "*-deployments-*.json")

    Returns:
        list[str]: List of file paths matching pattern
    """
    if directory is None:
        directory = str(Path(__file__).parent.parent.parent)

    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning(f"Directory does not exist: {directory}")
            return []

        matching_files = list(dir_path.glob(pattern))
        return [str(f) for f in matching_files]
    except Exception as e:
        logger.error(f"Error listing deployment files: {e}")
        return []


# Export functions and classes
__all__ = [
    "persist_deployment_data",
    "load_deployment_data",
    "verify_persistence",
    "list_deployment_files",
    "get_default_path",
    "DeploymentPersistenceError",
    "ensure_directory_exists",
    "serialize_datetime",
]
