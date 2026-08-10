"""Regression tests for deployment/resource metric alignment validation."""

from datetime import datetime, timezone
from pathlib import Path

from validate_metrics_deployment_alignment import build_report, nearest_timestamp

ROOT = Path(__file__).resolve().parents[1]


def report_inputs() -> tuple[Path, Path, Path]:
    return (
        ROOT / "deployment-events-30days.json",
        ROOT / "data/resource_metrics/resource-metrics-30d-20260810T111404Z.json",
        ROOT / "data/resource_metrics/disk-network-storage-metrics-30d-20260810T114451Z.json",
    )


def test_nearest_timestamp_returns_signed_offset() -> None:
    event = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    nearest, offset = nearest_timestamp(
        event,
        [
            datetime(2026, 8, 10, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc),
        ],
    )

    assert nearest == datetime(2026, 8, 10, 11, 0, tzinfo=timezone.utc)
    assert offset == -3600


def test_report_validates_four_categories_for_both_services() -> None:
    deployment, cpu_memory, disk_network = report_inputs()
    report, aligned = build_report(deployment, cpu_memory, disk_network)

    assert report["quality_summary"]["category_presence_passed"] == 8
    assert report["quality_summary"]["category_presence_checks"] == 8
    assert report["quality_summary"]["deployment_events_loaded"] == 9
    assert len(aligned["alignment_rows"]) == 36
    assert all(
        report["services"][service]["categories"][category]["present"]
        for service in ("pbx-web", "whisper-stt")
        for category in ("cpu", "memory", "disk", "network")
    )


def test_report_keeps_gaps_and_anomalies_explicit() -> None:
    deployment, cpu_memory, disk_network = report_inputs()
    report, _ = build_report(deployment, cpu_memory, disk_network)

    assert report["alignment_status"] == "validated_with_temporal_gaps"
    assert report["quality_summary"]["category_temporal_completeness_passed"] == 0
    assert report["quality_summary"]["internal_metric_gap_free"] is True
    assert any(gap["type"] == "leading_metric_coverage_gap" for gap in report["gaps"])
    assert any(
        anomaly["type"] == "constant_zero_metric"
        and anomaly["service"] == "pbx-web"
        for anomaly in report["anomalies"]
    )
    assert any(
        anomaly["type"] == "cross_category_timestamp_grid_offset"
        for anomaly in report["anomalies"]
    )
