"""
VictoriaLogs query infrastructure for latency metrics.

This module provides query templates and utilities for querying latency metrics
from VictoriaLogs, including percentile calculations (p50, p95, p99) and time
range parameterization.
"""

from .client import VictoriaLogsClient
from .queries import LatencyQueryTemplates
from .metrics import LatencyMetricsCalculator

__all__ = [
    'VictoriaLogsClient',
    'LatencyQueryTemplates',
    'LatencyMetricsCalculator'
]
