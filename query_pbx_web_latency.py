#!/usr/bin/env python3
"""
Query pbx-web latency metrics from Argo Workflows for a specified date range.

This script queries Argo Workflows directly from the iad-ci cluster to extract
pbx-web build latency metrics (p50, p95, p99 response times). It filters workflows
by workflowTemplateRef matching pbx-web builds and handles missing data gracefully.

Output format:
{
    "query_metadata": {
        "timestamp": "ISO 8601 timestamp",
        "start_date": "ISO 8601 start date",
        "end_date": "ISO 8601 end date",
        "days_queried": 30,
        "workflow_template": "pbx-web-build",
        "cluster": "iad-ci"
    },
    "latency_metrics": {
        "p50_seconds": 0.0,
        "p95_seconds": 0.0,
        "p99_seconds": 0.0,
        "count": 0,
        "mean_seconds": 0.0,
        "min_seconds": 0.0,
        "max_seconds": 0.0
    },
    "raw_data": [
        {
            "workflow_name": "workflow-name",
            "started_at": "ISO 8601 timestamp",
            "finished_at": "ISO 8601 timestamp",
            "duration_seconds": 0.0,
            "status": "Succeeded|Failed|Error"
        }
    ],
    "data_quality": {
        "total_workflows_found": 0,
        "valid_workflows": 0,
        "invalid_workflows": 0,
        "errors": []
    }
}
"""

import argparse
import json
import logging
import statistics
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PBXWebLatencyQuery:
    """Query pbx-web latency metrics from Argo Workflows."""

    def __init__(self, start_date: str, end_date: str, kubeconfig: str):
        """
        Initialize the query with date range and cluster config.

        Args:
            start_date: ISO 8601 start date (e.g., "2026-07-08T00:00:00Z")
            end_date: ISO 8601 end date (e.g., "2026-08-07T23:59:59Z")
            kubeconfig: Path to kubectl kubeconfig file
        """
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.kubeconfig = kubeconfig
        self.workflow_template = "pbx-web-build"
        self.namespace = "argo-workflows"

        # Data storage
        self.raw_data = []
        self.errors = []
        self.valid_workflows = 0
        self.invalid_workflows = 0

        logger.info(f"Query initialized for {start_date} to {end_date}")
        logger.info(f"Kubeconfig: {kubeconfig}")

    def query_argo_workflows(self) -> List[Dict[str, Any]]:
        """
        Query Argo Workflows from iad-ci cluster.

        Returns:
            List of workflow dictionaries matching pbx-web-build template
        """
        logger.info("Querying Argo Workflows from iad-ci cluster...")

        cmd = [
            "kubectl",
            f"--kubeconfig={self.kubeconfig}",
            "get", "workflows", "-n", self.namespace,
            "-o", "json"
        ]

        try:
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5 minute timeout
            )

            data = json.loads(result.stdout)
            workflows = data.get('items', [])

            logger.info(f"Retrieved {len(workflows)} total workflows from cluster")

            return workflows

        except subprocess.TimeoutExpired:
            logger.error("kubectl command timed out after 5 minutes")
            self.errors.append({
                "type": "timeout",
                "message": "kubectl command timed out after 5 minutes"
            })
            return []
        except subprocess.CalledProcessError as e:
            logger.error(f"kubectl command failed: {e.stderr}")
            self.errors.append({
                "type": "kubectl_error",
                "message": f"kubectl failed: {e.stderr}"
            })
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse kubectl JSON output: {e}")
            self.errors.append({
                "type": "json_error",
                "message": f"Failed to parse JSON: {str(e)}"
            })
            return []
        except Exception as e:
            logger.error(f"Unexpected error querying workflows: {e}")
            self.errors.append({
                "type": "unexpected_error",
                "message": str(e)
            })
            return []

    def filter_pbx_web_workflows(self, workflows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter workflows for pbx-web builds within date range.

        Args:
            workflows: List of all workflows from cluster

        Returns:
            List of pbx-web workflows within date range
        """
        logger.info("Filtering for pbx-web-build workflows within date range...")

        pbx_workflows = []

        for workflow in workflows:
            try:
                # Check workflow template reference
                workflow_ref = None
                spec = workflow.get('spec', {})
                if 'workflowTemplateRef' in spec:
                    workflow_ref = spec['workflowTemplateRef'].get('name')

                # Filter by workflow template
                if workflow_ref != self.workflow_template:
                    continue

                # Extract creation timestamp
                metadata = workflow.get('metadata', {})
                creation_ts = metadata.get('creationTimestamp')

                if not creation_ts:
                    continue

                created_at = datetime.fromisoformat(creation_ts.replace('Z', '+00:00'))

                # Check if within date range
                if self.start_date <= created_at <= self.end_date:
                    pbx_workflows.append(workflow)

            except Exception as e:
                workflow_name = workflow.get('metadata', {}).get('name', 'unknown')
                logger.warning(f"Error filtering workflow {workflow_name}: {e}")
                self.errors.append({
                    "type": "filter_error",
                    "workflow": workflow_name,
                    "message": str(e)
                })

        logger.info(f"Found {len(pbx_workflows)} pbx-web workflows within date range")
        return pbx_workflows

    def extract_latency_metrics(self, workflows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract latency metrics from workflow data.

        Args:
            workflows: List of pbx-web workflows

        Returns:
            List of latency data dictionaries
        """
        logger.info("Extracting latency metrics from workflows...")

        latency_data = []

        for workflow in workflows:
            try:
                metadata = workflow.get('metadata', {})
                status = workflow.get('status', {})

                workflow_name = metadata.get('name', 'unknown')
                started_at = status.get('startedAt')
                finished_at = status.get('finishedAt')
                phase = status.get('phase', 'Unknown')

                # Validate timestamps
                if not started_at or not finished_at:
                    logger.debug(f"Workflow {workflow_name} missing timestamps")
                    self.invalid_workflows += 1
                    self.errors.append({
                        "type": "missing_timestamps",
                        "workflow": workflow_name,
                        "message": "Missing startedAt or finishedAt"
                    })
                    continue

                # Parse timestamps
                start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))

                # Calculate duration
                duration_seconds = (end_time - start_time).total_seconds()

                # Validate duration
                if duration_seconds <= 0:
                    logger.debug(f"Workflow {workflow_name} has non-positive duration")
                    self.invalid_workflows += 1
                    self.errors.append({
                        "type": "invalid_duration",
                        "workflow": workflow_name,
                        "duration": duration_seconds,
                        "message": "Non-positive duration"
                    })
                    continue

                # Store valid data
                latency_entry = {
                    "workflow_name": workflow_name,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_seconds": round(duration_seconds, 3),
                    "status": phase
                }

                latency_data.append(latency_entry)
                self.valid_workflows += 1

            except Exception as e:
                workflow_name = workflow.get('metadata', {}).get('name', 'unknown')
                logger.warning(f"Error extracting metrics from {workflow_name}: {e}")
                self.invalid_workflows += 1
                self.errors.append({
                    "type": "extraction_error",
                    "workflow": workflow_name,
                    "message": str(e)
                })

        logger.info(f"Extracted {len(latency_data)} valid latency entries")
        logger.info(f"Invalid workflows: {self.invalid_workflows}")

        return latency_data

    def calculate_percentiles(self, durations: List[float]) -> Dict[str, float]:
        """
        Calculate percentile statistics for latency data.

        Args:
            durations: List of duration values in seconds

        Returns:
            Dictionary with percentile metrics
        """
        if not durations:
            return {
                "count": 0,
                "p50_seconds": 0.0,
                "p75_seconds": 0.0,
                "p90_seconds": 0.0,
                "p95_seconds": 0.0,
                "p99_seconds": 0.0,
                "mean_seconds": 0.0,
                "median_seconds": 0.0,
                "min_seconds": 0.0,
                "max_seconds": 0.0
            }

        sorted_durations = sorted(durations)
        n = len(sorted_durations)

        try:
            # Use statistics.quantiles for Python 3.8+
            quantiles = statistics.quantiles(durations, n=100, method='inclusive')
            return {
                "count": n,
                "p50_seconds": round(quantiles[49], 3),   # 50th percentile
                "p75_seconds": round(quantiles[74], 3),   # 75th percentile
                "p90_seconds": round(quantiles[89], 3),   # 90th percentile
                "p95_seconds": round(quantiles[94], 3),   # 95th percentile
                "p99_seconds": round(quantiles[98], 3),   # 99th percentile
                "mean_seconds": round(statistics.mean(durations), 3),
                "median_seconds": round(statistics.median(durations), 3),
                "min_seconds": round(min(durations), 3),
                "max_seconds": round(max(durations), 3)
            }
        except Exception as e:
            logger.warning(f"Error using statistics.quantiles: {e}, using manual calculation")
            return self._manual_percentiles(durations)

    def _manual_percentiles(self, durations: List[float]) -> Dict[str, float]:
        """
        Manual percentile calculation as fallback.

        Args:
            durations: List of duration values in seconds

        Returns:
            Dictionary with percentile metrics
        """
        sorted_data = sorted(durations)
        n = len(sorted_data)

        def percentile(p: float) -> float:
            index = int(n * p / 100)
            return sorted_data[min(index, n - 1)]

        return {
            "count": n,
            "p50_seconds": round(percentile(50), 3),
            "p75_seconds": round(percentile(75), 3),
            "p90_seconds": round(percentile(90), 3),
            "p95_seconds": round(percentile(95), 3),
            "p99_seconds": round(percentile(99), 3),
            "mean_seconds": round(statistics.mean(durations), 3),
            "median_seconds": round(statistics.median(durations), 3),
            "min_seconds": round(min(durations), 3),
            "max_seconds": round(max(durations), 3)
        }

    def run_query(self) -> Dict[str, Any]:
        """
        Execute the complete query pipeline.

        Returns:
            Dictionary with query results
        """
        logger.info("="*60)
        logger.info("Starting pbx-web latency query")
        logger.info("="*60)

        # Step 1: Query workflows from cluster
        workflows = self.query_argo_workflows()

        if not workflows:
            logger.warning("No workflows retrieved from cluster")
            return self._build_result(None)

        # Step 2: Filter for pbx-web workflows
        pbx_workflows = self.filter_pbx_web_workflows(workflows)

        if not pbx_workflows:
            logger.warning("No pbx-web workflows found in date range")
            return self._build_result(None)

        # Step 3: Extract latency metrics
        self.raw_data = self.extract_latency_metrics(pbx_workflows)

        # Step 4: Calculate percentiles (even if empty - returns zero metrics)
        durations = [entry['duration_seconds'] for entry in self.raw_data]
        latency_metrics = self.calculate_percentiles(durations)

        logger.info("="*60)
        logger.info("Query Results:")
        logger.info(f"  Valid workflows: {self.valid_workflows}")

        if self.valid_workflows > 0:
            logger.info(f"  p50: {latency_metrics['p50_seconds']}s")
            logger.info(f"  p95: {latency_metrics['p95_seconds']}s")
            logger.info(f"  p99: {latency_metrics['p99_seconds']}s")
        logger.info("="*60)

        return self._build_result(latency_metrics)

    def _build_result(self, latency_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Build the result dictionary.

        Args:
            latency_metrics: Calculated percentile metrics (optional)

        Returns:
            Complete result dictionary
        """
        # If no metrics provided, calculate empty metrics
        if latency_metrics is None:
            latency_metrics = self.calculate_percentiles([])

        return {
            "query_metadata": {
                "timestamp": datetime.now().isoformat(),
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat(),
                "days_queried": (self.end_date - self.start_date).days + 1,
                "workflow_template": self.workflow_template,
                "cluster": "iad-ci",
                "namespace": self.namespace
            },
            "latency_metrics": latency_metrics,
            "raw_data": self.raw_data,
            "data_quality": {
                "total_workflows_found": len(self.raw_data) + self.invalid_workflows,
                "valid_workflows": self.valid_workflows,
                "invalid_workflows": self.invalid_workflows,
                "errors": self.errors
            }
        }

    def save_results(self, result: Dict[str, Any], output_file: Path) -> None:
        """
        Save query results to JSON file.

        Args:
            result: Query result dictionary
            output_file: Path to output file
        """
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)

            logger.info(f"Results saved to: {output_file}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            self.errors.append({
                "type": "save_error",
                "message": f"Failed to save results: {str(e)}"
            })


def parse_date_range(days_back: int) -> tuple[str, str]:
    """
    Parse date range for N days back from today.

    Args:
        days_back: Number of days to query back from today

    Returns:
        Tuple of (start_date, end_date) as ISO 8601 strings
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    return (
        start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Query pbx-web latency metrics from Argo Workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Number of days to query back from today (default: 30)"
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in ISO 8601 format (e.g., 2026-07-08T00:00:00Z). "
             "If not specified, uses --days-back"
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in ISO 8601 format (e.g., 2026-08-07T23:59:59Z). "
             "If not specified, uses current time"
    )

    parser.add_argument(
        "--kubeconfig",
        type=str,
        default="/home/coding/.kube/iad-ci.kubeconfig",
        help="Path to kubectl kubeconfig file (default: /home/coding/.kube/iad-ci.kubeconfig)"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: data/latency-metrics/pbx-web-latency-raw.json)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse date range
    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        start_date, end_date = parse_date_range(args.days_back)

    logger.info(f"Querying pbx-web latency from {start_date} to {end_date}")

    # Initialize query
    query = PBXWebLatencyQuery(
        start_date=start_date,
        end_date=end_date,
        kubeconfig=args.kubeconfig
    )

    # Execute query
    try:
        result = query.run_query()

        # Determine output file
        if args.output:
            output_file = Path(args.output)
        else:
            output_dir = Path("data/latency-metrics")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"pbx-web-latency-{timestamp}.json"

        # Save results
        query.save_results(result, output_file)

        # Print summary
        print(f"\n{'='*60}")
        print("PBX-WEB LATENCY QUERY RESULTS")
        print(f"{'='*60}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Valid workflows: {result['data_quality']['valid_workflows']}")
        print(f"Invalid workflows: {result['data_quality']['invalid_workflows']}")

        latency = result['latency_metrics']
        if latency['count'] > 0:
            print(f"\nLatency Metrics:")
            print(f"  p50:  {latency['p50_seconds']}s")
            print(f"  p95:  {latency['p95_seconds']}s")
            print(f"  p99:  {latency['p99_seconds']}s")
            print(f"  Mean: {latency['mean_seconds']}s")
            print(f"  Min:  {latency['min_seconds']}s")
            print(f"  Max:  {latency['max_seconds']}s")
        else:
            print(f"\nNo valid latency data found")

        print(f"\nOutput: {output_file}")

        if result['data_quality']['errors']:
            print(f"\nWarnings/Errors: {len(result['data_quality']['errors'])}")
            if args.verbose:
                for error in result['data_quality']['errors'][:5]:  # Show first 5
                    print(f"  - {error['type']}: {error.get('message', 'No message')}")
                if len(result['data_quality']['errors']) > 5:
                    print(f"  ... and {len(result['data_quality']['errors']) - 5} more")

        return 0

    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())