"""
Validation module for aide-de-camp.

This module provides validation functions for various data structures
used throughout the application.
"""

from src.validation.deployment_data import (
    validate_deployment_data,
    validate_deployment_data_simple,
    validate_deployment_record,
    validate_timestamp,
    validate_required_fields,
    validate_data_types,
)

from src.validation.completeness import (
    validate_json_wellformedness,
    validate_json_file_wellformedness,
    validate_30day_completeness,
    validate_json_completeness,
    validate_json_file_completeness,
)

from src.validation.runner import validate_deployment_file

from src.validation.integration import validate_all

from src.validation.comparison import (
    FieldDiff,
    ComparisonResult,
    ComparisonReport,
)

__all__ = [
    "validate_deployment_data",
    "validate_deployment_data_simple",
    "validate_deployment_record",
    "validate_timestamp",
    "validate_required_fields",
    "validate_data_types",
    "validate_json_wellformedness",
    "validate_json_file_wellformedness",
    "validate_30day_completeness",
    "validate_json_completeness",
    "validate_json_file_completeness",
    "validate_deployment_file",
    "validate_all",
    "FieldDiff",
    "ComparisonResult",
    "ComparisonReport",
]
