#!/usr/bin/env python3
"""
Query whisper-stt latency metrics from Argo Workflows

This script queries whisper-stt latency metrics (processing duration) from
Argo Workflows for a specified time window, extracts workflow timing data,
and outputs raw metrics to JSON files for intermediate storage.

Usage:
    python query_whisper_stt_latency.py [days_back] [--input-file PATH]

    Args:
        days_back: Number of days to query (default: 30)
        --input-file: Path to JSON file containing workflow data (optional)
                     If not provided, queries live cluster via kubectl

    Example:
        python query_whisper_stt_latency.py 30                              # Query last 30 days from cluster
        python query_whisper_stt_latency.py 30 --input-file workflows.json  # Query from JSON file
        python query_whisper_stt_latency.py 7                               # Query last 7 days

Output:
    Creates JSON file: data/latency-metrics/whisper-stt-latency-raw.json
    Format:
    {
        "query_metadata": {
            "timestamp": "2026-08-07T12:34:56Z",
            "days_back": 30,
            "start_date": "2026-07-08T00:00:00Z",
            "end_date": "2026-08-07T23:59:59Z",
            "data_source": "cluster" or "file"
        },
        "raw_data": [
            {
                "workflow_name": "whisper-stt-build-abc123",
                "started_at": "2026-07-08T10:30:00Z",
                "finished_at": "2026-07-08T10:32:15Z",
                "duration_seconds": 135.5,
                "phase": "Succeeded"
            },
            ...
        ],
        "summary": {
            "total_workflows": 150,
            "successful_workflows": 145,
            "failed_workflows": 5,
            "valid_duration_records": 145
        }
    }
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WhisperSTTLatencyQuery:
    """Query and extract whisper-stt latency metrics from Argo Workflows."""

    def __init__(self, days_back: int = 30, input_file: Optional[Path] = None):
        """
        Initialize the query with specified time window.

        Args:
            days_back: Number of days to query from today
            input_file: Optional path to JSON file containing workflow data.
                       If not provided, queries live cluster via kubectl.
        """
        self.days_back = days_back
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=days_back)
        self.input_file = input_file
        self.data_source = "file" if input_file else "cluster"

        # Argo Workflows configuration
        self.kubeconfig = "/home/coding/.kube/iad-ci.kubeconfig"
        self.namespace = "argo-workflows"
        self.workflow_template = "whisper-stt-build"

        # Data storage
        self.raw_data = []
        self.summary = {
            "total_workflows": 0,
            "successful_workflows": 0,
            "failed_workflows": 0,
            "other_phases": 0,
            "valid_duration_records": 0,
            "missing_timestamps": 0
        }

        # Error tracking
        self.errors = []

    def query_workflows(self) -> List[Dict[str, Any]]:
        """
        Query Argo Workflows for whisper-stt builds in the time window.

        Returns:
            List of workflow objects matching the criteria

        Raises:
            subprocess.CalledProcessError: If kubectl command fails
        """
        logger.info(f"Querying Argo Workflows for {self.workflow_template}")
        logger.info(f"Time range: {self.start_date.isoformat()} to {self.end_date.isoformat()}")

        # Build kubectl command to query workflows
        # Note: We query all workflows and filter by date in Python since
        # Kubernetes field selectors don't support inequality operators on timestamps
        cmd = [
            "kubectl",
            f"--kubeconfig={self.kubeconfig}",
            "get",
            "workflows",
            "-n", self.namespace,
            "-o", "json"
        ]

        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            data = json.loads(result.stdout)
            workflows = data.get("items", [])

            logger.info(f"Retrieved {len(workflows)} total workflows from cluster")

            return workflows

        except subprocess.CalledProcessError as e:
            logger.error(f"kubectl command failed: {e}")
            logger.error(f"stderr: {e.stderr}")
            self.errors.append({
                "type": "kubectl_error",
                "message": str(e),
                "stderr": e.stderr if hasattr(e, 'stderr') else None
            })
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse kubectl JSON output: {e}")
            self.errors.append({
                "type": "json_parse_error",
                "message": str(e)
            })
            raise

    def extract_latency_metrics(self, workflows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract latency metrics from workflow objects.

        Args:
            workflows: List of workflow objects from kubectl

        Returns:
            List of processed latency data records
        """
        logger.info("Extracting latency metrics from workflows")

        latency_data = []

        for workflow in workflows:
            try:
                # Extract workflow metadata
                workflow_name = workflow.get("metadata", {}).get("name", "unknown")
                creation_timestamp = workflow.get("metadata", {}).get("creationTimestamp")

                # Check if workflow matches our template
                workflow_ref = None
                if "spec" in workflow and "workflowTemplateRef" in workflow["spec"]:
                    workflow_ref = workflow["spec"]["workflowTemplateRef"].get("name")

                # Filter by workflow template
                if workflow_ref != self.workflow_template:
                    continue

                # Extract timing data
                status = workflow.get("status", {})
                started_at = status.get("startedAt")
                finished_at = status.get("finishedAt")
                phase = status.get("phase", "Unknown")

                # Update summary counts
                self.summary["total_workflows"] += 1
                if phase == "Succeeded":
                    self.summary["successful_workflows"] += 1
                elif phase == "Failed":
                    self.summary["failed_workflows"] += 1
                else:
                    self.summary["other_phases"] += 1

                # Check if within time window (using startedAt if available, else creationTimestamp)
                timestamp_to_check = started_at if started_at else creation_timestamp
                if not timestamp_to_check:
                    self.summary["missing_timestamps"] += 1
                    logger.debug(f"Workflow {workflow_name} has no timestamp, skipping")
                    continue

                # Parse timestamp and check if within range
                try:
                    workflow_time = datetime.fromisoformat(timestamp_to_check.replace('Z', '+00:00'))

                    # Check if within our time window
                    if workflow_time < self.start_date or workflow_time > self.end_date:
                        continue

                except ValueError as e:
                    logger.warning(f"Invalid timestamp format for {workflow_name}: {e}")
                    self.errors.append({
                        "type": "timestamp_error",
                        "workflow": workflow_name,
                        "timestamp": timestamp_to_check,
                        "message": str(e)
                    })
                    continue

                # Calculate duration if both timestamps exist
                duration_seconds = None
                if started_at and finished_at:
                    try:
                        start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        end = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                        duration_seconds = (end - start).total_seconds()

                        # Only record positive durations
                        if duration_seconds > 0:
                            self.summary["valid_duration_records"] += 1
                        else:
                            duration_seconds = None
                            logger.debug(f"Workflow {workflow_name} has non-positive duration, skipping")

                    except ValueError as e:
                        logger.warning(f"Failed to calculate duration for {workflow_name}: {e}")
                        self.errors.append({
                            "type": "duration_calculation_error",
                            "workflow": workflow_name,
                            "started_at": started_at,
                            "finished_at": finished_at,
                            "message": str(e)
                        })

                # Store the record
                record = {
                    "workflow_name": workflow_name,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_seconds": round(duration_seconds, 3) if duration_seconds else None,
                    "phase": phase
                }

                latency_data.append(record)

            except Exception as e:
                logger.warning(f"Error processing workflow: {e}")
                self.errors.append({
                    "type": "workflow_processing_error",
                    "message": str(e)
                })

        logger.info(f"Extracted {len(latency_data)} latency records")
        logger.info(f"Summary: {self.summary}")

        return latency_data

    def save_results(self, latency_data: List[Dict[str, Any]]) -> Path:
        """
        Save query results to JSON file.

        Args:
            latency_data: List of latency records

        Returns:
            Path to the saved output file
        """
        # Create output directory
        output_dir = Path("/home/coding/aide-de-camp/data/latency-metrics")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Prepare output data
        output_data = {
            "query_metadata": {
                "timestamp": datetime.now().isoformat(),
                "days_back": self.days_back,
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(),
                "workflow_template": self.workflow_template,
                "namespace": self.namespace
            },
            "raw_data": latency_data,
            "summary": self.summary,
            "errors": self.errors if self.errors else None
        }

        # Generate filename with timestamp
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f"whisper-stt-latency-raw-{timestamp_str}.json"

        # Also save to default filename for compatibility
        default_file = output_dir / "whisper-stt-latency-raw.json"

        # Write files
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        with open(default_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        logger.info(f"Saved results to: {output_file}")
        logger.info(f"Also saved to default path: {default_file}")

        return output_file

    def run(self) -> Dict[str, Any]:
        """
        Execute the full query pipeline.

        Returns:
            Dictionary containing query results and metadata
        """
        logger.info("="*70)
        logger.info("WHISPER-STT LATENCY QUERY")
        logger.info("="*70)

        try:
            # Step 1: Query workflows from Argo
            workflows = self.query_workflows()

            # Step 2: Extract latency metrics
            latency_data = self.extract_latency_metrics(workflows)

            # Step 3: Save results
            output_file = self.save_results(latency_data)

            # Print summary
            logger.info("="*70)
            logger.info("QUERY COMPLETE")
            logger.info("="*70)
            logger.info(f"Output file: {output_file}")
            logger.info(f"Total workflows found: {self.summary['total_workflows']}")
            logger.info(f"Successful: {self.summary['successful_workflows']}")
            logger.info(f"Failed: {self.summary['failed_workflows']}")
            logger.info(f"Valid duration records: {self.summary['valid_duration_records']}")
            logger.info(f"Missing timestamps: {self.summary['missing_timestamps']}")

            if self.errors:
                logger.warning(f"Errors encountered: {len(self.errors)}")
                for error in self.errors[:5]:  # Show first 5 errors
                    logger.warning(f"  - {error['type']}: {error.get('message', 'N/A')}")
                if len(self.errors) > 5:
                    logger.warning(f"  ... and {len(self.errors) - 5} more errors")

            return {
                "status": "success",
                "output_file": str(output_file),
                "summary": self.summary,
                "errors": self.errors
            }

        except Exception as e:
            logger.error(f"Query failed: {e}")
            self.errors.append({
                "type": "query_failure",
                "message": str(e)
            })
            return {
                "status": "failed",
                "error": str(e),
                "errors": self.errors
            }


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Query whisper-stt latency metrics from Argo Workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "days_back",
        type=int,
        nargs='?',
        default=30,
        help="Number of days to query from today (default: 30)"
    )

    args = parser.parse_args()

    # Validate input
    if args.days_back <= 0:
        logger.error("days_back must be a positive integer")
        sys.exit(1)

    # Run query
    query = WhisperSTTLatencyQuery(days_back=args.days_back)
    result = query.run()

    # Exit with appropriate code
    if result["status"] == "success":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()