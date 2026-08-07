"""
Manifest reading and template substitution module.

This module provides functionality for reading Kubernetes manifests from
jedarden/declarative-config and applying templated field substitutions with
strict validation to ensure only whitelisted fields are modified.

Key security constraints:
- Only specific field paths may be modified (whitelist-based)
- No LLM-authored edits allowed beyond template substitution
- All modifications must be explicit and validated
- File not found errors are handled gracefully
"""

import logging
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import yaml


logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """
    Validation error for manifest operations.

    Raised when:
    - A non-whitelisted field would be modified
    - Template field path is invalid
    - Manifest structure is invalid
    - File not found or access error
    """
    pass


@dataclass
class TemplateField:
    """
    A template field that can be substituted in a YAML manifest.

    Fields are specified as JSON Pointer paths (RFC 6901) relative to the
    document root. For example:
    - "/spec/template/spec/containers/0/image" → first container's image
    - "/spec/replicas" → replica count
    - "/spec/template/spec/containers/0/resources/limits/memory" → resource limit
    """
    path: str
    value: Any

    def validate(self) -> None:
        """Validate that the field path is well-formed."""
        # Security: only allow specific path patterns
        if not self.path.startswith("/"):
            raise ValidationError(f"Invalid field path '{self.path}': must start with /")

        # Check for suspicious patterns that might indicate free-form editing
        suspicious_patterns = ["*", "..", "//", "\n", "\r", "\t"]
        for pattern in suspicious_patterns:
            if pattern in self.path:
                raise ValidationError(
                    f"Invalid field path '{self.path}': contains forbidden pattern '{pattern}'"
                )

        # Validate path components are alphanumeric or valid indices
        parts = [p for p in self.path.split("/") if p]
        for part in parts:
            # Allow array indices (digits) or dictionary keys (alphanumeric with -/_)
            if not (part.isdigit() or part.replace("-", "").replace("_", "").isalnum()):
                raise ValidationError(
                    f"Invalid field path component '{part}' in '{self.path}': "
                    f"must be alphanumeric or digits"
                )


@dataclass
class ManifestResult:
    """
    Result of manifest reading and template substitution.

    Attributes:
        success: Whether the operation completed successfully
        manifest_content: Modified manifest YAML as string (for git commit)
        error: Error message if operation failed
        changes_summary: Summary of changes made
        original_content: Original manifest content (for rollback)
    """
    success: bool
    manifest_content: Optional[str] = None
    error: Optional[str] = None
    changes_summary: Optional[List[str]] = None
    original_content: Optional[str] = None


class ManifestTemplateEngine:
    """
    Engine for reading manifests and applying template substitutions.

    This class provides secure manifest reading and template substitution
    with strict validation to ensure only whitelisted fields can be modified.
    All modifications are explicit and validated against a security whitelist.
    """

    # Security whitelist: only these path prefixes may be modified
    # This prevents arbitrary LLM-authored edits
    ALLOWED_PATH_PREFIXES = [
        "/spec/template/spec/containers/",  # container images, resources, env vars
        "/spec/replicas",                     # replica counts
        "/spec/template/spec/",              # other template spec fields
        "/spec/progressDeadlineSeconds",    # deployment timeout
    ]

    # Paths that are NEVER allowed (security-critical)
    FORBIDDEN_PATHS = [
        "/metadata/name",                    # changing resource name
        "/metadata/namespace",               # changing namespace
        "/kind",                             # changing resource kind
        "/apiVersion",                       # changing API version
        "/status",                           # modifying status (read-only)
    ]

    def __init__(
        self,
        declarative_config_path: str = "/home/coding/declarative-config",
        strict_validation: bool = True,
    ):
        """
        Initialize manifest template engine.

        Args:
            declarative_config_path: Path to declarative-config repository
            strict_validation: If True, reject any non-whitelisted field modifications
        """
        self.declarative_config_path = Path(declarative_config_path)
        self.strict_validation = strict_validation

    def read_and_apply_templates(
        self,
        manifest_path: str,
        template_vars: Dict[str, Any],
        cluster: Optional[str] = None,
    ) -> ManifestResult:
        """
        Read manifest from declarative-config and apply template substitutions.

        Args:
            manifest_path: Path to manifest within declarative-config
                          (e.g., "k8s/ardenone-cluster/botburrow/deployment.yaml")
            template_vars: Dictionary of template variable substitutions.
                          Keys are field paths (JSON Pointer format), values are new values.
                          Example: {"/spec/template/spec/containers/0/image": "nginx:1.19"}
            cluster: Optional cluster name for validation

        Returns:
            ManifestResult with modified manifest content or error details

        Raises:
            ValidationError: If validation fails (when strict_validation=True)
        """
        logger.info(f"Reading manifest '{manifest_path}' and applying {len(template_vars)} template vars")

        # Validate inputs
        if not manifest_path:
            return ManifestResult(
                success=False,
                error="manifest_path is required",
            )

        if not template_vars:
            return ManifestResult(
                success=True,
                manifest_content=None,
                changes_summary=[],
            )

        # Build full path
        try:
            full_path = self._resolve_manifest_path(manifest_path, cluster)
        except (FileNotFoundError, RuntimeError) as e:
            return ManifestResult(
                success=False,
                error=f"Manifest path resolution failed: {e}",
            )

        # Read manifest
        try:
            original_data, original_content = self._read_manifest(full_path)
        except FileNotFoundError as e:
            return ManifestResult(
                success=False,
                error=f"Manifest file not found: {full_path}",
            )
        except Exception as e:
            return ManifestResult(
                success=False,
                error=f"Failed to read manifest: {e}",
            )

        # Parse and validate template fields
        try:
            template_fields = self._parse_template_vars(template_vars)
        except ValidationError as e:
            return ManifestResult(
                success=False,
                error=f"Invalid template variables: {e}",
            )

        # Apply substitutions with validation
        try:
            modified_data, changes = self._apply_substitutions(
                original_data,
                template_fields,
            )
        except ValidationError as e:
            return ManifestResult(
                success=False,
                error=f"Template substitution failed: {e}",
            )

        # Convert back to YAML
        try:
            manifest_content = self._to_yaml(modified_data)
        except Exception as e:
            return ManifestResult(
                success=False,
                error=f"Failed to convert manifest to YAML: {e}",
            )

        logger.info(f"Successfully applied {len(changes)} template substitutions")

        return ManifestResult(
            success=True,
            manifest_content=manifest_content,
            changes_summary=changes,
            original_content=original_content,
        )

    def _resolve_manifest_path(
        self,
        manifest_path: str,
        cluster: Optional[str] = None,
    ) -> Path:
        """
        Resolve manifest path to full filesystem path.

        Args:
            manifest_path: Relative path within declarative-config
            cluster: Optional cluster name for validation

        Returns:
            Full path to manifest file

        Raises:
            FileNotFoundError: If manifest file doesn't exist
            RuntimeError: If path validation fails
        """
        # Build full path
        if cluster:
            # If cluster specified, prepend k8s/{cluster}/
            full_path = self.declarative_config_path / "k8s" / cluster / manifest_path
        else:
            # Otherwise, use manifest_path as-is
            full_path = self.declarative_config_path / manifest_path

        # Validate path exists
        if not full_path.exists():
            raise FileNotFoundError(f"Manifest file not found: {full_path}")

        # Security: validate we're in declarative-config
        try:
            full_path.resolve().relative_to(self.declarative_config_path.resolve())
        except ValueError:
            raise RuntimeError(
                f"Path traversal detected: {full_path} is outside declarative-config"
            )

        return full_path

    def _read_manifest(self, manifest_path: Path) -> Tuple[Any, str]:
        """
        Read and parse YAML manifest.

        Args:
            manifest_path: Path to manifest file

        Returns:
            Tuple of (parsed_data, raw_content)

        Raises:
            FileNotFoundError: If file doesn't exist
            Exception: If YAML parsing fails
        """
        with open(manifest_path, "r") as f:
            content = f.read()
            data = yaml.safe_load(content)

        return data, content

    def _parse_template_vars(self, template_vars: Dict[str, Any]) -> List[TemplateField]:
        """
        Parse template variables into TemplateField objects.

        Args:
            template_vars: Dictionary of path -> value mappings

        Returns:
            List of validated TemplateField objects

        Raises:
            ValidationError: If any field is invalid
        """
        fields = []

        for path, value in template_vars.items():
            field = TemplateField(path=str(path), value=value)
            field.validate()
            fields.append(field)

        return fields

    def _apply_substitutions(
        self,
        manifest_data: Any,
        template_fields: List[TemplateField],
    ) -> Tuple[Any, List[str]]:
        """
        Apply template field substitutions to manifest.

        Args:
            manifest_data: Parsed manifest data
            template_fields: List of validated template fields

        Returns:
            Tuple of (modified_data, change_summary)

        Raises:
            ValidationError: If any non-whitelisted field would be modified
        """
        # Work on a copy to avoid modifying original
        modified = copy.deepcopy(manifest_data)
        changes = []

        for field in template_fields:
            # Validate field path is allowed
            self._validate_field_allowed(field.path)

            # Apply substitution
            old_value = self._get_field_value(modified, field.path)
            self._set_field_value(modified, field.path, field.value)

            # Track change
            if old_value != field.value:
                changes.append(f"{field.path}: {old_value} → {field.value}")

        return modified, changes

    def _validate_field_allowed(self, path: str) -> None:
        """
        Validate that a field path is allowed for modification.

        Args:
            path: JSON Pointer path to field

        Raises:
            ValidationError: If path is not allowed
        """
        # Check forbidden paths first
        for forbidden in self.FORBIDDEN_PATHS:
            if path.startswith(forbidden):
                raise ValidationError(
                    f"Field path '{path}' is forbidden: '{forbidden}' paths cannot be modified"
                )

        # Check allowed prefixes (if strict validation enabled)
        if self.strict_validation:
            allowed = False
            for prefix in self.ALLOWED_PATH_PREFIXES:
                if path.startswith(prefix):
                    allowed = True
                    break

            if not allowed:
                raise ValidationError(
                    f"Field path '{path}' is not in allowed prefixes. "
                    f"Allowed prefixes: {self.ALLOWED_PATH_PREFIXES}. "
                    f"This prevents arbitrary LLM-authored edits."
                )

    def _get_field_value(self, data: Any, path: str) -> Any:
        """
        Get field value from manifest using JSON Pointer path.

        Args:
            data: Manifest data
            path: JSON Pointer path

        Returns:
            Current field value

        Raises:
            ValidationError: If path is invalid or not found
        """
        parts = [p for p in path.split("/") if p]
        current = data

        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    raise ValidationError(f"Path '{path}': key '{part}' not found")
                current = current[part]
            elif isinstance(current, list):
                if not part.isdigit():
                    raise ValidationError(f"Path '{path}': expected array index, got '{part}'")
                idx = int(part)
                if idx >= len(current):
                    raise ValidationError(f"Path '{path}': array index {idx} out of range")
                current = current[idx]
            else:
                raise ValidationError(f"Path '{path}': cannot traverse into scalar value")

        return current

    def _set_field_value(self, data: Any, path: str, value: Any) -> None:
        """
        Set field value in manifest using JSON Pointer path.

        Args:
            data: Manifest data (will be modified in place)
            path: JSON Pointer path
            value: New value to set

        Raises:
            ValidationError: If path is invalid or cannot be set
        """
        parts = [p for p in path.split("/") if p]

        if not parts:
            raise ValidationError(f"Invalid path: {path}")

        # Navigate to parent object
        current = data
        for part in parts[:-1]:
            if isinstance(current, dict):
                if part not in current:
                    raise ValidationError(f"Path '{path}': key '{part}' not found")
                current = current[part]
            elif isinstance(current, list):
                if not part.isdigit():
                    raise ValidationError(f"Path '{path}': expected array index, got '{part}'")
                idx = int(part)
                if idx >= len(current):
                    raise ValidationError(f"Path '{path}': array index {idx} out of range")
                current = current[idx]
            else:
                raise ValidationError(f"Path '{path}': cannot traverse into scalar value")

        # Set final value
        final_key = parts[-1]
        if isinstance(current, dict):
            current[final_key] = value
        elif isinstance(current, list):
            if not final_key.isdigit():
                raise ValidationError(f"Path '{path}': expected array index, got '{final_key}'")
            idx = int(final_key)
            if idx >= len(current):
                raise ValidationError(f"Path '{path}': array index {idx} out of range")
            current[idx] = value
        else:
            raise ValidationError(f"Path '{path}': cannot set field on scalar value")

    def _to_yaml(self, data: Any) -> str:
        """
        Convert manifest data to YAML string.

        Args:
            data: Manifest data

        Returns:
            YAML string
        """
        return yaml.dump(data, default_flow_style=False, sort_keys=False)


def read_manifest_with_templates(
    manifest_path: str,
    template_vars: Dict[str, Any],
    declarative_config_path: str = "/home/coding/declarative-config",
    cluster: Optional[str] = None,
    strict_validation: bool = True,
) -> ManifestResult:
    """
    Convenience function for reading manifest and applying template substitutions.

    Args:
        manifest_path: Path to manifest within declarative-config
        template_vars: Dictionary of template variable substitutions
        declarative_config_path: Path to declarative-config repository
        cluster: Optional cluster name
        strict_validation: Whether to enforce strict validation

    Returns:
        ManifestResult with modified manifest content

    Example:
        result = read_manifest_with_templates(
            "k8s/ardenone-cluster/botburrow/deployment.yaml",
            {"/spec/template/spec/containers/0/image": "nginx:1.19"}
        )
        if result.success:
            manifest_yaml = result.manifest_content
        else:
            print(f"Error: {result.error}")
    """
    engine = ManifestTemplateEngine(
        declarative_config_path=declarative_config_path,
        strict_validation=strict_validation,
    )

    return engine.read_and_apply_templates(
        manifest_path=manifest_path,
        template_vars=template_vars,
        cluster=cluster,
    )