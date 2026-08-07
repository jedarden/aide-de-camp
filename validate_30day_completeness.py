#!/usr/bin/env python3
"""
30-Day Deployment Data Completeness Validation

Implements comprehensive validation for 30-day deployment data completeness
based on the specification in docs/deployment-data-30day-completeness-validation-rules.md

Version: 1.0
Date: 2026-08-07
Bead ID: adc-hmgsc
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# Validation Status Enum
# ============================================================================

class ValidationStatus(Enum):
    """Validation status levels."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class Severity(Enum):
    """Error severity levels."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


# ============================================================================
# Data Classes for Validation Results
# ============================================================================

@dataclass
class ValidationError:
    """Single validation error or warning."""
    rule_id: str
    severity: Severity
    message: str
    field_path: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationMetrics:
    """Metrics calculated during validation."""
    days_covered: int = 0
    distinct_deployment_days: int = 0
    total_deployments: int = 0
    successful_deployments: int = 0
    failed_deployments: int = 0
    gaps_detected: List[Dict[str, Any]] = field(default_factory=list)
    coverage_percentage: float = 0.0
    largest_gap_days: int = 0


@dataclass
class ValidationResult:
    """Complete validation result."""
    status: ValidationStatus
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    metrics: ValidationMetrics = field(default_factory=ValidationMetrics)
    validation_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Validator Implementation
# ============================================================================

class ThirtyDayCompletenessValidator:
    """
    Comprehensive validator for 30-day deployment data completeness.

    Implements all validation rules from the specification:
    - Structural Validation (SV-001, SV-002, SV-003)
    - Temporal Validation (TV-001, TV-002, TV-003)
    - Data Quality Validation (DQ-001, DQ-002, DQ-003)
    - Completeness Validation (CV-001, CV-002, CV-003, CV-004)
    - Cross-Service Validation (CSV-001, CSV-002)
    """

    def __init__(self, service_name: str = "whisper-stt", strict_mode: bool = False):
        """
        Initialize the validator.

        Args:
            service_name: Primary service to validate
            strict_mode: If True, treat warnings as failures
        """
        self.service_name = service_name
        self.strict_mode = strict_mode

    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """
        Run complete validation on deployment data.

        Args:
            data: Deployment data dictionary matching WhisperSTTDeploymentSchema

        Returns:
            ValidationResult with complete validation status and details
        """
        result = ValidationResult(status=ValidationStatus.PASS)

        try:
            # Step 1: Structural Validation
            self._validate_structural_rules(data, result)
            if result.status == ValidationStatus.FAIL:
                return result  # Fail fast on structural errors

            # Step 2: Temporal Validation
            self._validate_temporal_rules(data, result)
            # Note: Continue validation even if temporal fails to detect gaps

            # Step 3: Data Quality Validation
            self._validate_data_quality_rules(data, result)

            # Step 4: Completeness Validation
            self._validate_completeness_rules(data, result)

            # Step 5: Cross-Service Validation (if applicable)
            self._validate_cross_service_rules(data, result)

            # Determine final status
            self._determine_final_status(result)

        except Exception as e:
            result.status = ValidationStatus.FAIL
            result.errors.append(ValidationError(
                rule_id="SYSTEM",
                severity=Severity.CRITICAL,
                message=f"Validation system error: {str(e)}"
            ))

        return result

    def _validate_structural_rules(self, data: Dict[str, Any], result: ValidationResult):
        """Apply structural validation rules (SV-001, SV-002, SV-003)."""

        # Rule SV-001: Top-Level Structure
        required_keys = {'metadata', 'cluster_deployments', 'summary'}
        missing_keys = required_keys - set(data.keys())
        if missing_keys:
            result.errors.append(ValidationError(
                rule_id="SV-001",
                severity=Severity.CRITICAL,
                message=f"Missing required top-level structure: {', '.join(missing_keys)}. Deployment data is incomplete.",
                details={
                    "missing_keys": list(missing_keys),
                    "required_keys": list(required_keys),
                    "actual_keys": list(data.keys()),
                    "actionable_guidance": f"Deployment data must include all required top-level keys: {', '.join(required_keys)}. Missing: {', '.join(missing_keys)}. Add the missing sections to ensure complete data structure validation."
                }
            ))
            result.status = ValidationStatus.FAIL
            return

        # Rule SV-002: Metadata Structure
        metadata = data.get('metadata', {})
        required_metadata_fields = {
            'generated_at': str,
            'data_period_start': str,
            'data_period_end': str,
            'services': list,
            'clusters': list,
            'data_sources': list
        }

        for field_name, expected_type in required_metadata_fields.items():
            if field_name not in metadata:
                result.errors.append(ValidationError(
                    rule_id="SV-002",
                    severity=Severity.CRITICAL,
                    message=f"Missing required metadata field: {field_name}. Metadata structure is incomplete.",
                    field_path=f"metadata.{field_name}",
                    details={
                        "missing_field": field_name,
                        "required_fields": list(required_metadata_fields.keys()),
                        "actionable_guidance": f"Add missing metadata.{field_name} field. Required format: {expected_type.__name__}. Example: {field_name} = {self._get_field_example(field_name, expected_type)}"
                    }
                ))
                result.status = ValidationStatus.FAIL
                continue

            if not isinstance(metadata[field_name], expected_type):
                result.errors.append(ValidationError(
                    rule_id="SV-002",
                    severity=Severity.CRITICAL,
                    message=f"Invalid type for metadata.{field_name}: expected {expected_type.__name__}, got {type(metadata[field_name]).__name__}. Type mismatch prevents validation.",
                    field_path=f"metadata.{field_name}",
                    details={
                        "expected_type": expected_type.__name__,
                        "actual_type": type(metadata[field_name]).__name__,
                        "actionable_guidance": f"Convert metadata.{field_name} to {expected_type.__name__} type. Current value: {metadata[field_name]}"
                    }
                ))
                result.status = ValidationStatus.FAIL
                continue

            if expected_type == list and len(metadata[field_name]) == 0:
                result.errors.append(ValidationError(
                    rule_id="SV-002",
                    severity=Severity.CRITICAL,
                    message=f"Empty array for metadata.{field_name}. Required field must contain at least one element.",
                    field_path=f"metadata.{field_name}",
                    details={
                        "empty_field": field_name,
                        "actionable_guidance": f"Add at least one element to metadata.{field_name}. For services: include '{self.service_name}'. For clusters: include cluster names. For data_sources: include sources like 'kubernetes_replicasets'."
                    }
                ))
                result.status = ValidationStatus.FAIL

        # Rule SV-003: Service-Specific Structure
        cluster_deployments = data.get('cluster_deployments', {})
        if self.service_name not in cluster_deployments:
            result.errors.append(ValidationError(
                rule_id="SV-003",
                severity=Severity.CRITICAL,
                message=f"Missing deployment data for service: {self.service_name}",
                details={"required_service": self.service_name, "available_services": list(cluster_deployments.keys())}
            ))
            result.status = ValidationStatus.FAIL
            return

        service_data = cluster_deployments[self.service_name]
        required_service_fields = [
            'namespace', 'deployment_name', 'created_at', 'current_image',
            'current_replicas', 'replica_history', 'deployments_last_30_days',
            'successful_deployments', 'failed_deployments', 'deployment_versions',
            'all_versions_in_history'
        ]

        for field_name in required_service_fields:
            if field_name not in service_data:
                result.errors.append(ValidationError(
                    rule_id="SV-003",
                    severity=Severity.CRITICAL,
                    message=f"Missing service field: {field_name}",
                    field_path=f"cluster_deployments.{self.service_name}.{field_name}"
                ))
                result.status = ValidationStatus.FAIL

        # Check replica_history is not empty
        replica_history = service_data.get('replica_history', [])
        if not replica_history:
            result.errors.append(ValidationError(
                rule_id="CV-003",
                severity=Severity.CRITICAL,
                message="Empty replica_history - no deployment records found. At least 5 distinct deployment days required for 30-day completeness validation.",
                field_path=f"cluster_deployments.{self.service_name}.replica_history",
                details={
                    "actionable_guidance": "Check if replica_history is properly populated from ReplicaSet data. Verify kubectl queries are returning replica sets for the 30-day period.",
                    "required_minimum": "5 distinct deployment days",
                    "actual_count": "0 records found",
                    "validation_period": f"{data.get('metadata', {}).get('data_period_start')} to {data.get('metadata', {}).get('data_period_end')}"
                }
            ))
            result.status = ValidationStatus.FAIL

    def _validate_temporal_rules(self, data: Dict[str, Any], result: ValidationResult):
        """Apply temporal validation rules (TV-001, TV-002, TV-003)."""

        metadata = data.get('metadata', {})
        service_data = data.get('cluster_deployments', {}).get(self.service_name, {})
        replica_history = service_data.get('replica_history', [])

        # Rule TV-002: Timestamp Validity
        timestamp_fields = [
            ('metadata.generated_at', metadata.get('generated_at')),
            ('metadata.data_period_start', metadata.get('data_period_start')),
            ('metadata.data_period_end', metadata.get('data_period_end')),
        ]

        for field_path, timestamp_str in timestamp_fields:
            try:
                self._validate_timestamp_format(timestamp_str, field_path)
            except ValueError as e:
                result.errors.append(ValidationError(
                    rule_id="TV-002",
                    severity=Severity.CRITICAL,
                    message=f"Invalid timestamp format for {field_path}: {str(e)}",
                    field_path=field_path,
                    details={"timestamp": timestamp_str, "error": str(e)}
                ))
                result.status = ValidationStatus.FAIL

        # Rule TV-003: Timestamp Consistency
        try:
            start_ts = self._parse_timestamp(metadata.get('data_period_start'))
            end_ts = self._parse_timestamp(metadata.get('data_period_end'))
            generated_ts = self._parse_timestamp(metadata.get('generated_at'))

            if start_ts >= end_ts:
                result.errors.append(ValidationError(
                    rule_id="TV-003",
                    severity=Severity.CRITICAL,
                    message="data_period_start must be before data_period_end",
                    field_path="metadata",
                    details={
                        "data_period_start": metadata.get('data_period_start'),
                        "data_period_end": metadata.get('data_period_end')
                    }
                ))
                result.status = ValidationStatus.FAIL

            if end_ts > generated_ts:
                result.errors.append(ValidationError(
                    rule_id="TV-003",
                    severity=Severity.CRITICAL,
                    message="data_period_end must be before or equal to generated_at",
                    field_path="metadata"
                ))
                result.status = ValidationStatus.FAIL

        except ValueError as e:
            # Already caught by TV-002
            pass

        # Rule TV-001: 30-Day Coverage
        timestamps = []
        for entry in replica_history:
            try:
                ts = self._parse_timestamp(entry.get('created_at'))
                timestamps.append(ts)
            except (ValueError, KeyError):
                continue

        if timestamps:
            timestamps.sort()
            oldest = timestamps[0]
            newest = timestamps[-1]
            days_covered = (newest - oldest).days
            result.metrics.days_covered = days_covered

            if days_covered < 28:
                # Enhanced error message with specific missing day information
                missing_day_count = 28 - days_covered

                # Calculate specific missing days if possible
                date_range_start = oldest
                date_range_end = newest

                # Generate detailed missing day list with day numbers
                all_days_in_range = []
                current = date_range_start
                day_counter = 1
                days_with_numbers = {}  # Map date to day number

                while current <= date_range_end:
                    date_str = current.date().isoformat()
                    all_days_in_range.append(date_str)
                    days_with_numbers[date_str] = day_counter
                    current += timedelta(days=1)
                    day_counter += 1

                # Determine which specific days are missing from replica_history
                replica_dates = set()
                for entry in replica_history:
                    try:
                        ts = self._parse_timestamp(entry.get('created_at'))
                        replica_dates.add(ts.date().isoformat())
                    except (ValueError, KeyError):
                        continue

                # Find missing days with their day numbers
                missing_days_with_numbers = [
                    {"date": day, "day_number": days_with_numbers.get(day, 0)}
                    for day in all_days_in_range if day not in replica_dates
                ]

                # Build comprehensive guidance message
                guidance_parts = [
                    f"Expected range: days 1-30 (28 minimum required)",
                    f"Actual coverage: {days_covered} days ({(days_covered/30)*100:.1f}%)",
                    f"Missing: {missing_day_count} days from expected range"
                ]

                if missing_days_with_numbers:
                    if len(missing_days_with_numbers) <= 5:
                        missing_descriptions = [f"day {info['day_number']} ({info['date']})" for info in missing_days_with_numbers]
                        guidance_parts.append(f"Specific missing days: {', '.join(missing_descriptions)}")
                    else:
                        missing_descriptions = [f"day {info['day_number']} ({info['date']})" for info in missing_days_with_numbers[:3]]
                        guidance_parts.append(f"Missing days include: {', '.join(missing_descriptions)}... and {len(missing_days_with_numbers)-3} more")

                guidance_parts.extend([
                    f"Action required: Add deployment data for {missing_day_count} missing days",
                    f"Check: ReplicaSet history for records between {oldest.date().isoformat()} and {newest.date().isoformat()}",
                    f"Verify: Data collection covers full 30-day period from {metadata.get('data_period_start')}"
                ])

                # Build comprehensive error message
                if missing_days_with_numbers:
                    if len(missing_days_with_numbers) <= 3:
                        missing_summary = ", ".join([f"day {info['day_number']}" for info in missing_days_with_numbers])
                    else:
                        missing_summary = ", ".join([f"day {info['day_number']}" for info in missing_days_with_numbers[:2]]) + f"... and {len(missing_days_with_numbers)-2} more"
                else:
                    missing_summary = f"{missing_day_count} days"

                result.errors.append(ValidationError(
                    rule_id="TV-001",
                    severity=Severity.CRITICAL,
                    message=f"Insufficient 30-day coverage: {days_covered} days covered (< 28 required). Deployment data does not span the minimum required period. Expected days 1-30, missing {missing_summary}: {missing_days_with_numbers[0]['date'] if missing_days_with_numbers else 'various dates'}{'...' if len(missing_days_with_numbers) > 1 else ''}.",
                    details={
                        "days_covered": days_covered,
                        "required_minimum": 28,
                        "recommended_minimum": 30,
                        "expected_day_range": "days 1-30 (30-day analysis period)",
                        "coverage_gap_days": 28 - days_covered,
                        "oldest_deployment": oldest.isoformat(),
                        "newest_deployment": newest.isoformat(),
                        "missing_day_list": missing_days_with_numbers,
                        "missing_day_count": len(missing_days_with_numbers),
                        "coverage_percentage": f"{(days_covered/30)*100:.1f}%",
                        "actionable_guidance": " | ".join(guidance_parts)
                    }
                ))
                result.status = ValidationStatus.FAIL
            elif days_covered < 30:
                # Enhanced warning message with specific missing day information and day numbers
                missing_day_count = 30 - days_covered

                # Calculate specific missing days with day numbers
                all_days_in_range = []
                current = oldest
                day_counter = 1
                days_with_numbers = {}  # Map date to day number

                while current <= newest:
                    date_str = current.date().isoformat()
                    all_days_in_range.append(date_str)
                    days_with_numbers[date_str] = day_counter
                    current += timedelta(days=1)
                    day_counter += 1

                replica_dates = set()
                for entry in replica_history:
                    try:
                        ts = self._parse_timestamp(entry.get('created_at'))
                        replica_dates.add(ts.date().isoformat())
                    except (ValueError, KeyError):
                        continue

                # Find missing days with their day numbers
                missing_days_with_numbers = [
                    {"date": day, "day_number": days_with_numbers.get(day, 0)}
                    for day in all_days_in_range if day not in replica_dates
                ]

                # Build comprehensive guidance message
                guidance_parts = [
                    f"Expected range: days 1-30 (recommended)",
                    f"Actual coverage: {days_covered} days ({(days_covered/30)*100:.1f}%)",
                    f"Missing: {missing_day_count} days for complete 30-day coverage"
                ]

                if missing_days_with_numbers:
                    if len(missing_days_with_numbers) <= 3:
                        missing_descriptions = [f"day {info['day_number']} ({info['date']})" for info in missing_days_with_numbers]
                        guidance_parts.append(f"Specific missing days: {', '.join(missing_descriptions)}")
                    else:
                        missing_descriptions = [f"day {info['day_number']} ({info['date']})" for info in missing_days_with_numbers[:2]]
                        guidance_parts.append(f"Missing days include: {', '.join(missing_descriptions)}... and {len(missing_days_with_numbers)-2} more")

                guidance_parts.extend([
                    f"Action recommended: Add deployment data for {missing_day_count} missing days",
                    f"Verify: Data collection covers full 30-day period from {metadata.get('data_period_start')}"
                ])

                # Build comprehensive warning message
                if missing_days_with_numbers:
                    if len(missing_days_with_numbers) <= 2:
                        missing_summary = ", ".join([f"day {info['day_number']}" for info in missing_days_with_numbers])
                    else:
                        missing_summary = ", ".join([f"day {info['day_number']}" for info in missing_days_with_numbers[:2]]) + f"... and {len(missing_days_with_numbers)-2} more"
                else:
                    missing_summary = f"{missing_day_count} days"

                result.warnings.append(ValidationError(
                    rule_id="TV-001",
                    severity=Severity.WARNING,
                    message=f"Borderline coverage: {days_covered} days covered (< 30 recommended). Expected days 1-30, missing {missing_summary} for complete coverage: {missing_days_with_numbers[0]['date'] if missing_days_with_numbers else 'various dates'}{'...' if len(missing_days_with_numbers) > 1 else ''}.",
                    details={
                        "days_covered": days_covered,
                        "required_minimum": 28,
                        "recommended_minimum": 30,
                        "expected_day_range": "days 1-30 (recommended for complete analysis)",
                        "coverage_gap_days": 30 - days_covered,
                        "oldest_deployment": oldest.isoformat(),
                        "newest_deployment": newest.isoformat(),
                        "missing_day_list": missing_days_with_numbers,
                        "missing_day_count": len(missing_days_with_numbers),
                        "coverage_percentage": f"{(days_covered/30)*100:.1f}%",
                        "actionable_guidance": " | ".join(guidance_parts)
                    }
                ))

    def _validate_data_quality_rules(self, data: Dict[str, Any], result: ValidationResult):
        """Apply data quality validation rules (DQ-001, DQ-002, DQ-003)."""

        service_data = data.get('cluster_deployments', {}).get(self.service_name, {})

        # Rule DQ-001: Required Fields Presence
        critical_fields = {
            'namespace': service_data.get('namespace'),
            'deployment_name': service_data.get('deployment_name'),
            'current_image': service_data.get('current_image'),
            'replica_history': service_data.get('replica_history')
        }

        for field_name, value in critical_fields.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                result.errors.append(ValidationError(
                    rule_id="DQ-001",
                    severity=Severity.CRITICAL,
                    message=f"Missing or null critical field: {field_name}",
                    field_path=f"cluster_deployments.{self.service_name}.{field_name}"
                ))
                result.status = ValidationStatus.FAIL

        # Rule DQ-002: Numeric Field Ranges
        numeric_fields = {
            'current_replicas': service_data.get('current_replicas'),
            'deployments_last_30_days': service_data.get('deployments_last_30_days'),
            'successful_deployments': service_data.get('successful_deployments'),
            'failed_deployments': service_data.get('failed_deployments')
        }

        for field_name, value in numeric_fields.items():
            if value is not None and value < 0:
                result.errors.append(ValidationError(
                    rule_id="DQ-002",
                    severity=Severity.CRITICAL,
                    message=f"Negative value for {field_name}: {value}",
                    field_path=f"cluster_deployments.{self.service_name}.{field_name}",
                    details={"field_value": value}
                ))
                result.status = ValidationStatus.FAIL

        # Check aggregate consistency
        total = service_data.get('deployments_last_30_days', 0)
        successful = service_data.get('successful_deployments', 0)
        failed = service_data.get('failed_deployments', 0)

        if successful + failed > total:
            result.errors.append(ValidationError(
                rule_id="DQ-002",
                severity=Severity.CRITICAL,
                message=f"successful + failed ({successful + failed}) > total deployments ({total})",
                field_path=f"cluster_deployments.{self.service_name}",
                details={"successful": successful, "failed": failed, "total": total}
            ))
            result.status = ValidationStatus.FAIL

        # Rule DQ-003: Enum Field Validity
        valid_statuses = {"successful", "rolled_over", "scaled_down_or_failed"}
        for entry in service_data.get('replica_history', []):
            status = entry.get('status')
            if status and status not in valid_statuses:
                result.warnings.append(ValidationError(
                    rule_id="DQ-003",
                    severity=Severity.WARNING,
                    message=f"Invalid replica status '{status}'",
                    field_path=f"cluster_deployments.{self.service_name}.replica_history",
                    details={"invalid_status": status, "valid_statuses": list(valid_statuses)}
                ))

    def _validate_completeness_rules(self, data: Dict[str, Any], result: ValidationResult):
        """Apply completeness validation rules (CV-001, CV-002, CV-003, CV-004)."""

        service_data = data.get('cluster_deployments', {}).get(self.service_name, {})
        replica_history = service_data.get('replica_history', [])
        summary = data.get('summary', {})

        # Rule CV-001: Minimum Deployment Days
        distinct_days = self._count_distinct_deployment_days(replica_history)
        result.metrics.distinct_deployment_days = distinct_days

        if distinct_days < 5:
            result.errors.append(ValidationError(
                rule_id="CV-001",
                severity=Severity.CRITICAL,
                message=f"Insufficient deployment activity: {distinct_days} distinct deployment days (< 5 required). Service appears to have minimal deployment history.",
                details={
                    "distinct_days": distinct_days,
                    "required_minimum": 5,
                    "recommended_minimum": 10,
                    "shortage": 5 - distinct_days,
                    "total_replica_records": len(replica_history),
                    "actionable_guidance": f"Deployment data only shows activity on {distinct_days} days. Minimum 5 distinct days required. Check if: (1) Service is actively deployed, (2) ReplicaSet history includes all records, (3) Time period covers actual deployment activity. Add {5 - distinct_days} more deployment days or extend data collection window."
                }
            ))
            result.status = ValidationStatus.FAIL
        elif distinct_days < 10:
            result.warnings.append(ValidationError(
                rule_id="CV-001",
                severity=Severity.WARNING,
                message=f"Limited deployment activity: {distinct_days} distinct deployment days (< 10 recommended). Service deployment history is sparse.",
                details={
                    "distinct_days": distinct_days,
                    "required_minimum": 5,
                    "recommended_minimum": 10,
                    "shortage": 10 - distinct_days,
                    "total_replica_records": len(replica_history),
                    "actionable_guidance": f"Service shows limited deployment activity. Only {distinct_days} days with deployments in 30-day period. This may indicate: (1) Stable service with infrequent updates, (2) Missing deployment records, (3) Narrow data collection window. Consider extending data collection to capture more deployment events."
                }
            ))

        # Rule CV-002: Gap Detection
        gaps = self._detect_deployment_gaps(replica_history)
        result.metrics.gaps_detected = gaps
        result.metrics.total_deployments = len(replica_history)
        result.metrics.successful_deployments = service_data.get('successful_deployments', 0)
        result.metrics.failed_deployments = service_data.get('failed_deployments', 0)

        if gaps:
            critical_gaps = [g for g in gaps if g['severity'] == 'CRITICAL']
            warning_gaps = [g for g in gaps if g['severity'] == 'WARNING']

            if critical_gaps:
                # Format gap details with enhanced descriptions including day numbers
                gap_descriptions = []
                gap_details_list = []

                for gap in critical_gaps:
                    # Use the enhanced gap description if available
                    gap_description = gap.get('gap_description',
                        f"{gap.get('gap_days', 0)} days from {gap.get('gap_start_date', 'Unknown')} to {gap.get('gap_end_date', 'Unknown')}")

                    gap_descriptions.append(gap_description)

                    gap_details_list.append({
                        "gap_duration_days": gap.get('gap_days', 0),
                        "gap_start_date": gap.get('gap_start_date', 'Unknown'),
                        "gap_end_date": gap.get('gap_end_date', 'Unknown'),
                        "day_start": gap.get('day_start', 0),
                        "day_end": gap.get('day_end', 0),
                        "gap_description": gap_description,
                        "missing_days": gap.get('missing_days', []),
                        "missing_days_count": gap.get('missing_days_count', 0),
                        "impact_assessment": gap.get('impact_assessment', ''),
                        "actionable_guidance": gap.get('actionable_guidance', '')
                    })

                # Build comprehensive guidance
                guidance_parts = [
                    f"Expected: continuous coverage across days 1-30 (30-day analysis period)",
                    f"Found: {len(critical_gaps)} critical gaps ≥ 14 days each",
                    f"Total missing days: {sum(g['gap_days'] for g in critical_gaps)} days ({round((sum(g['gap_days'] for g in critical_gaps)/30)*100)}% of analysis period)"
                ]

                for i, gap_info in enumerate(gap_details_list, 1):
                    if gap_info.get('day_start', 0) > 0 and gap_info.get('day_end', 0) > 0:
                        guidance_parts.append(f"Gap {i}: {gap_info['gap_description']}. Impact: {gap_info.get('impact_assessment', 'Assessment unavailable')}")
                    else:
                        guidance_parts.append(f"Gap {i}: {gap_info['gap_description']}")

                guidance_parts.extend([
                    f"Action: Fill missing deployment data or document legitimate deployment inactivity",
                    f"Check: ReplicaSet history queries, data collection logs, service deployment records for the gap periods listed above"
                ])

                # Create primary error message with first gap details
                first_gap = critical_gaps[0]
                primary_gap_msg = f"{len(critical_gaps)} critical coverage gaps detected (≥ 14 days each). Expected continuous days 1-30 coverage, found {len(critical_gaps)} gaps totaling {sum(g['gap_days'] for g in critical_gaps)} missing days."

                if first_gap.get('day_start', 0) > 0 and first_gap.get('day_end', 0) > 0:
                    primary_gap_msg += f" Largest gap: {first_gap['gap_days']} days from day {first_gap['day_start']} to day {first_gap['day_end']} ({first_gap.get('gap_start_date', 'Unknown')} to {first_gap.get('gap_end_date', 'Unknown')})."
                else:
                    primary_gap_msg += f" Largest gap: {first_gap['gap_days']} days ({first_gap.get('gap_start_date', 'Unknown')} to {first_gap.get('gap_end_date', 'Unknown')})."

                result.errors.append(ValidationError(
                    rule_id="CV-002",
                    severity=Severity.CRITICAL,
                    message=primary_gap_msg,
                    details={
                        "critical_gaps": critical_gaps,
                        "total_gaps": len(gaps),
                        "critical_gap_count": len(critical_gaps),
                        "total_missing_days": sum(g['gap_days'] for g in critical_gaps),
                        "missing_data_percentage": round((sum(g['gap_days'] for g in critical_gaps)/30)*100),
                        "expected_coverage": "days 1-30 (continuous, 30-day analysis period)",
                        "gap_descriptions": gap_descriptions,
                        "gap_details": gap_details_list,
                        "largest_gap_days": max(g['gap_days'] for g in critical_gaps) if critical_gaps else 0,
                        "actionable_guidance": " | ".join(guidance_parts)
                    }
                ))
                result.status = ValidationStatus.FAIL
            elif warning_gaps:
                # Format gap details with enhanced descriptions including day numbers
                gap_descriptions = []
                gap_details_list = []

                for gap in warning_gaps:
                    # Use the enhanced gap description if available
                    gap_description = gap.get('gap_description',
                        f"{gap.get('gap_days', 0)} days from {gap.get('gap_start_date', 'Unknown')} to {gap.get('gap_end_date', 'Unknown')}")

                    gap_descriptions.append(gap_description)

                    gap_details_list.append({
                        "gap_duration_days": gap.get('gap_days', 0),
                        "gap_start_date": gap.get('gap_start_date', 'Unknown'),
                        "gap_end_date": gap.get('gap_end_date', 'Unknown'),
                        "day_start": gap.get('day_start', 0),
                        "day_end": gap.get('day_end', 0),
                        "gap_description": gap_description,
                        "missing_days": gap.get('missing_days', []),
                        "missing_days_count": gap.get('missing_days_count', 0),
                        "impact_assessment": gap.get('impact_assessment', ''),
                        "actionable_guidance": gap.get('actionable_guidance', '')
                    })

                # Build comprehensive guidance
                guidance_parts = [
                    f"Expected: near-continuous coverage across days 1-30 (30-day analysis period)",
                    f"Found: {len(warning_gaps)} moderate gaps ≥ 7 days each",
                    f"Total missing days: {sum(g['gap_days'] for g in warning_gaps)} days ({round((sum(g['gap_days'] for g in warning_gaps)/30)*100)}% of analysis period)"
                ]

                for i, gap_info in enumerate(gap_details_list, 1):
                    if gap_info.get('day_start', 0) > 0 and gap_info.get('day_end', 0) > 0:
                        guidance_parts.append(f"Gap {i}: {gap_info['gap_description']}. Impact: {gap_info.get('impact_assessment', 'Assessment unavailable')}")
                    else:
                        guidance_parts.append(f"Gap {i}: {gap_info['gap_description']}")

                guidance_parts.extend([
                    f"Action: Review ReplicaSet history, verify data collection, document if deployment was legitimately inactive",
                    f"Check: Data pipeline logs, service deployment records for periods listed above"
                ])

                # Create primary warning message with first gap details
                first_gap = warning_gaps[0]
                primary_warning_msg = f"{len(warning_gaps)} coverage gaps detected (≥ 7 days each). Expected near-continuous days 1-30 coverage, found {len(warning_gaps)} gaps totaling {sum(g['gap_days'] for g in warning_gaps)} missing days."

                if first_gap.get('day_start', 0) > 0 and first_gap.get('day_end', 0) > 0:
                    primary_warning_msg += f" Largest gap: {first_gap['gap_days']} days from day {first_gap['day_start']} to day {first_gap['day_end']} ({first_gap.get('gap_start_date', 'Unknown')} to {first_gap.get('gap_end_date', 'Unknown')})."
                else:
                    primary_warning_msg += f" Largest gap: {first_gap['gap_days']} days ({first_gap.get('gap_start_date', 'Unknown')} to {first_gap.get('gap_end_date', 'Unknown')})."

                result.warnings.append(ValidationError(
                    rule_id="CV-002",
                    severity=Severity.WARNING,
                    message=primary_warning_msg,
                    details={
                        "warning_gaps": warning_gaps,
                        "total_gaps": len(gaps),
                        "warning_gap_count": len(warning_gaps),
                        "total_missing_days": sum(g['gap_days'] for g in warning_gaps),
                        "missing_data_percentage": round((sum(g['gap_days'] for g in warning_gaps)/30)*100),
                        "expected_coverage": "days 1-30 (near-continuous, 30-day analysis period)",
                        "gap_descriptions": gap_descriptions,
                        "gap_details": gap_details_list,
                        "largest_gap_days": max(g['gap_days'] for g in warning_gaps) if warning_gaps else 0,
                        "actionable_guidance": " | ".join(guidance_parts)
                    }
                ))

        # Calculate coverage percentage
        if result.metrics.days_covered > 0:
            result.metrics.coverage_percentage = (min(result.metrics.days_covered, 30) / 30) * 100

        # Rule CV-004: Summary Metrics Consistency
        actual_total_deployments = service_data.get('deployments_last_30_days', 0)
        reported_total = summary.get('total_deployments_last_30_days', 0)

        if actual_total_deployments != reported_total:
            result.warnings.append(ValidationError(
                rule_id="CV-004",
                severity=Severity.WARNING,
                message=f"Summary metrics inconsistency: total_deployments_last_30_days reported as {reported_total} but cluster_deployments shows {actual_total_deployments}.",
                details={
                    "reported": reported_total,
                    "actual": actual_total_deployments,
                    "discrepancy": abs(reported_total - actual_total_deployments),
                    "field_path": "summary.total_deployments_last_30_days",
                    "actionable_guidance": f"Summary field ({reported_total}) does not match cluster deployment data ({actual_total_deployments}). Update summary.total_deployments_last_30_days to match cluster_deployments.{self.service_name}.deployments_last_30_days. Difference: {abs(reported_total - actual_total_deployments)} deployments."
                }
            ))

        # Check gap detection consistency
        gaps_reported = summary.get('gaps_detected', False)
        actual_gaps = len(gaps) > 0
        if gaps_reported != actual_gaps:
            result.warnings.append(ValidationError(
                rule_id="CV-004",
                severity=Severity.WARNING,
                message=f"Summary metrics inconsistency: gaps_detected reported as {gaps_reported} but analysis found {len(gaps)} gaps ({actual_gaps}).",
                details={
                    "reported": gaps_reported,
                    "actual_gaps_exist": actual_gaps,
                    "actual_gap_count": len(gaps),
                    "field_path": "summary.gaps_detected",
                    "gap_details": gaps[:3] if len(gaps) > 3 else gaps,  # Show first 3 gaps
                    "actionable_guidance": f"Summary.gaps_detected ({gaps_reported}) does not match gap analysis results ({actual_gaps}). Update summary.gaps_detected to {actual_gaps} and summary.largest_gap_days to {max(g['gap_days'] for g in gaps) if gaps else 0}."
                }
            ))

    def _validate_cross_service_rules(self, data: Dict[str, Any], result: ValidationResult):
        """Apply cross-service validation rules (CSV-001, CSV-002)."""

        cluster_deployments = data.get('cluster_deployments', {})

        # Only apply if multiple services
        if len(cluster_deployments) <= 1:
            return

        # Rule CSV-001: Data Period Alignment
        # All services should use the same global period
        metadata = data.get('metadata', {})
        global_start = metadata.get('data_period_start')
        global_end = metadata.get('data_period_end')

        if not global_start or not global_end:
            result.warnings.append(ValidationError(
                rule_id="CSV-001",
                severity=Severity.WARNING,
                message="No global data period defined for multi-service comparison",
                details={"service_count": len(cluster_deployments)}
            ))

    def _determine_final_status(self, result: ValidationResult):
        """Determine final validation status based on errors and warnings."""

        if result.errors:
            result.status = ValidationStatus.FAIL
        elif result.warnings and self.strict_mode:
            result.status = ValidationStatus.FAIL
        elif result.warnings:
            result.status = ValidationStatus.WARN
        else:
            result.status = ValidationStatus.PASS

        # Add info messages
        if result.status == ValidationStatus.PASS:
            result.info.append("✅ Validation passed: All checks successful")
        result.info.append(f"Coverage: {result.metrics.days_covered} days, {result.metrics.total_deployments} deployments")

        if result.metrics.gaps_detected:
            result.info.append(f"Gap analysis: {len(result.metrics.gaps_detected)} gaps, largest: {max(g['gap_days'] for g in result.metrics.gaps_detected)} days")

    # ============================================================================
    # Helper Methods
    # ============================================================================

    def _get_field_example(self, field_name: str, expected_type: type) -> str:
        """Get example values for metadata fields."""
        examples = {
            'generated_at': '"2026-08-06T09:30:00Z"',
            'data_period_start': '"2026-07-06T00:00:00Z"',
            'data_period_end': '"2026-08-06T09:30:00Z"',
            'services': '["whisper-stt"]',
            'clusters': '["ardenone-cluster"]',
            'data_sources': '["kubernetes_replicasets", "argo_workflows"]'
        }
        return examples.get(field_name, f"<{expected_type.__name__} value>")

    def _validate_timestamp_format(self, timestamp_str: str, field_name: str = "timestamp"):
        """Validate ISO8601 timestamp format and value."""
        if not timestamp_str or not isinstance(timestamp_str, str):
            raise ValueError(f"{field_name}: empty or not a string")

        try:
            ts = timestamp_str
            if ts.endswith('Z'):
                ts = ts[:-1] + '+00:00'
            dt = datetime.fromisoformat(ts.replace('+00:00', ''))

            # Check for future timestamps (allow 2 days for clock skew)
            if dt > datetime.now() + timedelta(days=2):
                raise ValueError(f"{field_name}: timestamp is in the future")

            # Check for unreasonably old timestamps
            if dt < datetime(2020, 1, 1):
                raise ValueError(f"{field_name}: timestamp is unreasonably old")

            return dt
        except ValueError as e:
            raise ValueError(f"{field_name}: {str(e)}")

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO8601 timestamp string to datetime object."""
        if not timestamp_str:
            raise ValueError("Empty timestamp string")

        ts = timestamp_str
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        return datetime.fromisoformat(ts.replace('+00:00', ''))

    def _count_distinct_deployment_days(self, replica_history: List[Dict[str, Any]]) -> int:
        """Count distinct days with deployment activity."""
        distinct_days = set()

        for entry in replica_history:
            if 'created_at' in entry:
                try:
                    ts = self._parse_timestamp(entry['created_at'])
                    distinct_days.add(ts.date())
                except (ValueError, KeyError):
                    continue

        return len(distinct_days)

    def _detect_deployment_gaps(self, replica_history: List[Dict[str, Any]],
                               critical_threshold: int = 14,
                               warning_threshold: int = 7) -> List[Dict[str, Any]]:
        """Detect significant gaps in deployment data with enhanced error messages."""
        gaps = []

        # Sort timestamps
        timestamps = []
        for entry in replica_history:
            if 'created_at' in entry:
                try:
                    ts = self._parse_timestamp(entry['created_at'])
                    timestamps.append(ts)
                except (ValueError, KeyError):
                    continue

        timestamps.sort()

        # Find earliest timestamp for day number calculation
        earliest_timestamp = timestamps[0] if timestamps else None

        # Calculate gaps between consecutive deployments with enhanced details
        for i in range(1, len(timestamps)):
            gap_days = (timestamps[i] - timestamps[i-1]).days

            if gap_days >= warning_threshold:
                gap_start_date = timestamps[i-1].date().isoformat()
                gap_end_date = timestamps[i].date().isoformat()

                # Calculate day numbers relative to the 30-day period
                day_start = (timestamps[i-1].date() - earliest_timestamp.date()).days + 1 if earliest_timestamp else 0
                day_end = (timestamps[i].date() - earliest_timestamp.date()).days + 1 if earliest_timestamp else 0

                # Generate specific missing days list
                missing_days = []
                current = timestamps[i-1].date() + timedelta(days=1)
                while current < timestamps[i].date():
                    missing_days.append(current.isoformat())
                    current += timedelta(days=1)

                # Create comprehensive gap description
                if day_start > 0 and day_end > 0:
                    gap_description = f"{gap_days}-day gap from day {day_start} to day {day_end} ({gap_start_date} to {gap_end_date})"
                else:
                    gap_description = f"{gap_days}-day gap from {gap_start_date} to {gap_end_date}"

                gaps.append({
                    'gap_start': timestamps[i-1].isoformat(),
                    'gap_end': timestamps[i].isoformat(),
                    'gap_start_date': gap_start_date,
                    'gap_end_date': gap_end_date,
                    'gap_days': gap_days,
                    'day_start': day_start,
                    'day_end': day_end,
                    'severity': 'CRITICAL' if gap_days >= critical_threshold else 'WARNING',
                    'gap_description': gap_description,
                    'missing_days': missing_days,
                    'missing_days_count': len(missing_days),
                    'impact_assessment': self._assess_gap_impact(gap_days, day_start, day_end),
                    'actionable_guidance': self._generate_gap_actionable_guidance(gap_days, day_start, day_end, missing_days)
                })

        return gaps

    def _assess_gap_impact(self, gap_days: int, day_start: int, day_end: int) -> str:
        """Assess the impact of a gap based on its size and position."""
        if gap_days >= 21:
            return f"CRITICAL: {gap_days}-day gap represents {round((gap_days/30)*100)}% of the 30-day analysis period. Severely impacts data completeness and statistical validity."
        elif gap_days >= 14:
            return f"HIGH: {gap_days}-day gap represents {round((gap_days/30)*100)}% of the 30-day period. Significantly reduces confidence in deployment trends."
        elif gap_days >= 7:
            return f"MODERATE: {gap_days}-day gap represents {round((gap_days/30)*100)}% of the 30-day period. May affect detection of deployment patterns."
        else:
            return f"LOW: {gap_days}-day gap has minimal impact on overall 30-day analysis."

    def _generate_gap_actionable_guidance(self, gap_days: int, day_start: int, day_end: int, missing_days: List[str]) -> str:
        """Generate actionable guidance for addressing specific gaps."""
        guidance_parts = []

        if day_start > 0 and day_end > 0:
            guidance_parts.append(f"Gap spans day {day_start} to day {day_end} of the 30-day analysis period.")
        else:
            guidance_parts.append(f"Gap spans {gap_days} consecutive days in the analysis period.")

        if len(missing_days) <= 5:
            guidance_parts.append(f"Specific missing days: {', '.join(missing_days)}")
        else:
            guidance_parts.append(f"Missing {len(missing_days)} days, including: {', '.join(missing_days[:3])}... and {len(missing_days)-3} more")

        guidance_parts.extend([
            f"Action: Check ReplicaSet history for deployments between day {day_start} and day {day_end}",
            f"Verify: Data collection pipeline was operational during this period",
            f"Review: Service deployment logs and change management records"
        ])

        return " | ".join(guidance_parts)


# ============================================================================
# Main Validation Function
# ============================================================================

def validate_30day_completeness(
    data: Dict[str, Any],
    service_name: str = "whisper-stt",
    strict_mode: bool = False
) -> Dict[str, Any]:
    """
    Validate 30-day deployment data completeness.

    Args:
        data: Deployment data dictionary matching WhisperSTTDeploymentSchema
        service_name: Primary service to validate (default: "whisper-stt")
        strict_mode: If True, treat warnings as failures (default: False)

    Returns:
        Dictionary with validation results:
        {
            "status": "PASS" | "WARN" | "FAIL",
            "errors": List[Dict],
            "warnings": List[Dict],
            "info": List[str],
            "metrics": Dict,
            "validation_timestamp": str (ISO8601)
        }
    """
    validator = ThirtyDayCompletenessValidator(service_name=service_name, strict_mode=strict_mode)
    result = validator.validate(data)

    # Convert to dict for JSON serialization
    return {
        "status": result.status.value,
        "errors": [
            {
                "rule_id": error.rule_id,
                "severity": error.severity.value,
                "message": error.message,
                "field_path": error.field_path,
                "details": error.details
            }
            for error in result.errors
        ],
        "warnings": [
            {
                "rule_id": warning.rule_id,
                "severity": warning.severity.value,
                "message": warning.message,
                "field_path": warning.field_path,
                "details": warning.details
            }
            for warning in result.warnings
        ],
        "info": result.info,
        "metrics": {
            "days_covered": result.metrics.days_covered,
            "distinct_deployment_days": result.metrics.distinct_deployment_days,
            "total_deployments": result.metrics.total_deployments,
            "successful_deployments": result.metrics.successful_deployments,
            "failed_deployments": result.metrics.failed_deployments,
            "gaps_detected": result.metrics.gaps_detected,
            "coverage_percentage": result.metrics.coverage_percentage,
            "largest_gap_days": result.metrics.largest_gap_days
        },
        "validation_timestamp": result.validation_timestamp
    }


def validate_json_file(file_path: str, service_name: str = "whisper-stt") -> Dict[str, Any]:
    """
    Validate deployment data from a JSON file.

    Args:
        file_path: Path to JSON file containing deployment data
        service_name: Service name to validate (default: "whisper-stt")

    Returns:
        Dictionary with validation results
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return validate_30day_completeness(data, service_name=service_name)
    except FileNotFoundError:
        return {
            "status": "FAIL",
            "errors": [{"rule_id": "FILE", "severity": "CRITICAL", "message": f"File not found: {file_path}"}],
            "warnings": [],
            "info": [],
            "metrics": {},
            "validation_timestamp": datetime.now().isoformat()
        }
    except json.JSONDecodeError as e:
        return {
            "status": "FAIL",
            "errors": [{"rule_id": "JSON", "severity": "CRITICAL", "message": f"Invalid JSON: {e}"}],
            "warnings": [],
            "info": [],
            "metrics": {},
            "validation_timestamp": datetime.now().isoformat()
        }


# ============================================================================
# Main Function for Testing
# ============================================================================

def main():
    """Main function for testing and demonstration."""
    print("=" * 70)
    print("30-DAY DEPLOYMENT DATA COMPLETENESS VALIDATION")
    print("=" * 70)

    # Test with example data from the schema
    import whisper_stt_deployment_schema

    example_data = whisper_stt_deployment_schema.schema_example()

    print(f"\nValidating example data for service: whisper-stt")
    print(f"Data period: {example_data['metadata']['data_period_start']} to {example_data['metadata']['data_period_end']}")

    result = validate_30day_completeness(example_data, service_name="whisper-stt")

    print(f"\nValidation Status: {result['status']}")
    print(f"Days Covered: {result['metrics']['days_covered']}")
    print(f"Distinct Deployment Days: {result['metrics']['distinct_deployment_days']}")
    print(f"Total Deployments: {result['metrics']['total_deployments']}")
    print(f"Coverage Percentage: {result['metrics']['coverage_percentage']:.1f}%")

    if result['errors']:
        print(f"\n❌ ERRORS ({len(result['errors'])}):")
        for error in result['errors']:
            print(f"  • [{error['rule_id']}] {error['message']}")

    if result['warnings']:
        print(f"\n⚠️  WARNINGS ({len(result['warnings'])}):")
        for warning in result['warnings']:
            print(f"  • [{warning['rule_id']}] {warning['message']}")

    if result['info']:
        print(f"\nℹ️  INFO:")
        for info in result['info']:
            print(f"  • {info}")

    return 0 if result['status'] == "PASS" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())