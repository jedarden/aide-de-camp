#!/usr/bin/env python3
"""
Gap Validation Schema

Pydantic models for deployment gap validation data structures.
Defines the schema for gap detection, coverage analysis, and validation results.

Schema Version: 1.0
Last Updated: 2026-08-11
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class GapSeverity(str, Enum):
    """Severity levels for coverage gaps"""
    CRITICAL = "critical"  # > 7 days or coverage < 80%
    HIGH = "high"          # > 7 days or coverage < 90%
    WARNING = "warning"    # > 3 days or coverage < 95%
    INFO = "info"          # <= 3 days or coverage >= 95%
    NONE = "none"          # No gaps


class GapPeriod(BaseModel):
    """Represents a single gap period with calculated metadata"""
    date: str = Field(..., description="ISO format date string (YYYY-MM-DD)")
    start_day: str = Field(..., description="Start date of this gap period")
    end_day: str = Field(..., description="End date of this gap period")
    size_days: int = Field(..., description="Size of the gap in days")
    is_consecutive: bool = Field(default=False, description="Whether this gap is part of a consecutive sequence")
    sequence_id: Optional[int] = Field(None, description="ID of the consecutive sequence (None if isolated)")

    @field_validator('size_days')
    @classmethod
    def validate_size(cls, v: int) -> int:
        """Ensure gap size is at least 1 day"""
        if v < 1:
            raise ValueError("Gap size must be at least 1 day")
        return v


class DeploymentInterval(BaseModel):
    """Deployment interval statistics and metadata"""
    first_deployment: str = Field(..., description="First deployment date (ISO format)")
    last_deployment: str = Field(..., description="Last deployment date (ISO format)")
    total_deployments: int = Field(..., description="Total number of deployments")
    average_interval_days: float = Field(..., description="Average interval between deployments in days")
    longest_interval_days: int = Field(..., description="Longest interval between deployments in days")
    shortest_interval_days: int = Field(..., description="Shortest interval between deployments in days")

    @field_validator('total_deployments', 'longest_interval_days', 'shortest_interval_days')
    @classmethod
    def validate_non_negative_int(cls, v: int) -> int:
        """Ensure integer fields are non-negative"""
        if v < 0:
            raise ValueError("Field must be non-negative")
        return v

    @field_validator('average_interval_days')
    @classmethod
    def validate_average_interval(cls, v: float) -> float:
        """Ensure average interval is non-negative"""
        if v < 0:
            raise ValueError("Average interval must be non-negative")
        return round(v, 1)


class CoverageMetrics(BaseModel):
    """Coverage metrics for deployment validation"""
    expected_days: int = Field(..., description="Expected number of days in analysis period")
    actual_days: int = Field(..., description="Actual number of days with deployment data")
    coverage_percentage: float = Field(..., description="Coverage percentage (0-100)")
    gap_count: int = Field(..., description="Number of gap days detected")
    meets_threshold: bool = Field(..., description="Whether coverage meets the minimum threshold")
    completeness_threshold: float = Field(default=95.0, description="Minimum coverage threshold")

    @field_validator('expected_days', 'actual_days', 'gap_count')
    @classmethod
    def validate_non_negative_int(cls, v: int) -> int:
        """Ensure integer fields are non-negative"""
        if v < 0:
            raise ValueError("Field must be non-negative")
        return v

    @field_validator('coverage_percentage', 'completeness_threshold')
    @classmethod
    def validate_coverage(cls, v: float) -> float:
        """Ensure coverage percentage is in valid range and rounded"""
        if v < 0 or v > 100:
            raise ValueError("Coverage percentage must be between 0 and 100")
        return round(v, 2)


class GapDetail(BaseModel):
    """Detailed information about a coverage gap"""
    gap_start_days_ago: int = Field(..., description="Days ago when gap started")
    gap_end_days_ago: int = Field(..., description="Days ago when gap ended")
    gap_duration_days: int = Field(..., description="Duration of gap in days")
    severity: GapSeverity = Field(..., description="Severity level based on gap duration")
    gap_start_date: Optional[str] = Field(None, description="Actual start date of gap (ISO format)")
    gap_end_date: Optional[str] = Field(None, description="Actual end date of gap (ISO format)")
    missing_data_types: List[str] = Field(default_factory=list, description="Types of data missing during gap")
    actionable_message: str = Field(default="", description="Human-readable actionable message")
    is_consecutive: bool = Field(default=False, description="Whether part of consecutive sequence")
    consecutive_sequence_id: Optional[int] = Field(None, description="Consecutive sequence identifier")
    position_in_sequence: Optional[int] = Field(None, description="Position in consecutive sequence (0-indexed)")

    @field_validator('gap_start_days_ago', 'gap_end_days_ago')
    @classmethod
    def validate_days_ago(cls, v: int) -> int:
        """Ensure days ago fields are non-negative"""
        if v < 0:
            raise ValueError("Days ago must be non-negative")
        return v

    @field_validator('gap_duration_days')
    @classmethod
    def validate_duration(cls, v: int) -> int:
        """Ensure gap duration is at least 1 day"""
        if v < 1:
            raise ValueError("Gap duration must be at least 1 day")
        return v


class GapValidationResult(BaseModel):
    """Comprehensive result of gap validation with actionable guidance"""
    is_valid: bool = Field(..., description="Whether validation passed")
    service_name: str = Field(..., description="Name of the service validated")
    expected_days: int = Field(..., ge=0, description="Expected days in analysis period")
    actual_days: int = Field(..., ge=0, description="Actual days with deployment data")
    coverage_percentage: float = Field(..., ge=0, le=100, description="Coverage percentage")
    gap_periods: List[GapPeriod] = Field(default_factory=list, description="List of gap periods")
    severity: GapSeverity = Field(default=GapSeverity.NONE, description="Overall severity level")
    error_message: str = Field(default="", description="Concise error message")
    actionable_guidance: List[str] = Field(default_factory=list, description="Actionable remediation steps")
    anomaly_messages: List[str] = Field(default_factory=list, description="Detected anomalies")
    deployment_intervals: Optional[DeploymentInterval] = Field(None, description="Deployment interval statistics")

    @field_validator('coverage_percentage')
    @classmethod
    def validate_coverage(cls, v: float) -> float:
        """Ensure coverage percentage is rounded to 2 decimal places"""
        return round(v, 2)


class CoverageGapResult(BaseModel):
    """Result of coverage gap validation"""
    has_gaps: bool = Field(..., description="Whether any gaps were detected")
    total_gaps: int = Field(..., ge=0, description="Total number of gaps detected")
    critical_gaps: int = Field(..., ge=0, description="Number of critical gaps (>7 days)")
    warning_gaps: int = Field(..., ge=0, description="Number of warning gaps (3-7 days)")
    info_gaps: int = Field(..., ge=0, description="Number of info gaps (<3 days)")
    gap_details: List[GapDetail] = Field(default_factory=list, description="Detailed gap information")
    error_messages: List[str] = Field(default_factory=list, description="Human-readable error messages")
    coverage_percentage: float = Field(default=0.0, ge=0, le=100, description="Overall coverage percentage")
    meets_threshold: bool = Field(default=False, description="Whether coverage meets minimum threshold")
    actionable_summary: str = Field(default="", description="High-level summary with remediation steps")

    @field_validator('coverage_percentage')
    @classmethod
    def validate_coverage(cls, v: float) -> float:
        """Ensure coverage percentage is rounded to 2 decimal places"""
        return round(v, 2)


class GapSummary(BaseModel):
    """Summary statistics for gap analysis"""
    total_gaps: int = Field(..., ge=0, description="Total number of gaps")
    isolated_gaps: int = Field(..., ge=0, description="Number of isolated gaps")
    consecutive_sequences: int = Field(..., ge=0, description="Number of consecutive gap sequences")
    longest_gap_days: int = Field(..., ge=0, description="Longest gap in days")
    longest_gap_start: Optional[str] = Field(None, description="Start of longest gap (ISO format)")
    longest_gap_end: Optional[str] = Field(None, description="End of longest gap (ISO format)")
    gap_intensity: float = Field(..., ge=0, description="Gap intensity (gaps per day)")
    total_analysis_days: int = Field(..., ge=0, description="Total days in analysis period")

    @field_validator('gap_intensity')
    @classmethod
    def validate_intensity(cls, v: float) -> float:
        """Ensure gap intensity is rounded to 4 decimal places"""
        return round(v, 4)


class GapAnomaly(BaseModel):
    """Detected anomaly in gap patterns"""
    severity: str = Field(..., description="Anomaly severity (critical, warning, info)")
    category: str = Field(..., description="Anomaly category")
    description: str = Field(..., description="Human-readable anomaly description")
    actionable_guidance: str = Field(..., description="Steps to remediate the anomaly")
    affected_period: Optional[str] = Field(None, description="Time period affected by anomaly")
    impact_assessment: str = Field(..., description="Assessment of anomaly impact")


class GapAnalysisReport(BaseModel):
    """Comprehensive gap analysis report"""
    service_name: str = Field(..., description="Service being analyzed")
    analysis_period_start: str = Field(..., description="Analysis period start (ISO format)")
    analysis_period_end: str = Field(..., description="Analysis period end (ISO format)")
    coverage_metrics: CoverageMetrics = Field(..., description="Coverage statistics")
    gap_summary: GapSummary = Field(..., description="Gap summary statistics")
    gap_details: List[GapDetail] = Field(default_factory=list, description="Detailed gap information")
    anomalies: List[GapAnomaly] = Field(default_factory=list, description="Detected anomalies")
    deployment_intervals: Optional[DeploymentInterval] = Field(None, description="Deployment interval analysis")
    generated_at: datetime = Field(default_factory=datetime.now, description="Report generation timestamp")
    is_valid: bool = Field(..., description="Whether validation passed")
    overall_severity: GapSeverity = Field(default=GapSeverity.NONE, description="Overall severity assessment")

    @field_validator('overall_severity')
    @classmethod
    def validate_severity(cls, v: GapSeverity) -> GapSeverity:
        """Ensure severity is a valid enum value"""
        if not isinstance(v, GapSeverity):
            raise ValueError("Severity must be a valid GapSeverity enum value")
        return v


__all__ = [
    "GapSeverity",
    "GapPeriod",
    "DeploymentInterval",
    "CoverageMetrics",
    "GapDetail",
    "GapValidationResult",
    "CoverageGapResult",
    "GapSummary",
    "GapAnomaly",
    "GapAnalysisReport",
]
