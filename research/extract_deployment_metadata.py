#!/usr/bin/env python3
"""
Deployment Metadata Extractor for pbx-web and whisper-stt
Extracts deployment events, timestamps, outcomes, and patterns over the last 30 days
"""

import json
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from collections import defaultdict

@dataclass
class DeploymentEvent:
    """Structured deployment event data"""
    service: str
    deployment_name: str
    revision: int
    replicaset: str
    timestamp: str
    age_days: int
    status: str
    replicas: int
    available: int
    ready: int
    image: str
    strategy: str
    success: bool
    deployment_duration_seconds: float = None

@dataclass
class DeploymentSummary:
    """High-level deployment metrics for a service"""
    service: str
    deployment_name: str
    total_revisions_30_days: int
    deployment_frequency: str
    last_deployment_timestamp: str
    days_since_last_deployment: int
    strategy: str
    current_status: str
    current_revision: int
    current_image: str
    success_rate: float
    failures: int

class DeploymentExtractor:
    """Extract and analyze deployment metadata from JSON files"""

    def __init__(self, base_dir: Path = Path("research")):
        self.base_dir = base_dir
        self.events: List[DeploymentEvent] = []
        self.summaries: List[DeploymentSummary] = []

    def load_json_file(self, path: Path) -> Dict:
        """Load and parse JSON file"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: File not found: {path}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {path}: {e}")
            return {}

    def extract_from_deployment_data(self, data: Dict, service_name: str) -> List[DeploymentEvent]:
        """Extract deployment events from deployment JSON structure"""
        events = []

        if not data or 'deployments' not in data:
            return events

        deployments = data['deployments']

        for deployment_name, deployment_data in deployments.items():
            deployment_events = deployment_data.get('deployment_events', [])
            strategy = deployment_data.get('strategy', 'Unknown')
            current_image = deployment_data.get('current_image', 'unknown')

            for event in deployment_events:
                # Determine image for this revision
                # Use current image for active, otherwise extract from replicaset or use unknown
                image = current_image if event['status'] == 'active' else 'unknown'

                event_obj = DeploymentEvent(
                    service=service_name,
                    deployment_name=deployment_name,
                    revision=event['revision'],
                    replicaset=event['replicaset'],
                    timestamp=event['timestamp'],
                    age_days=event['age_days'],
                    status=event['status'],
                    replicas=event['replicas'],
                    available=event['available'],
                    ready=event['ready'],
                    image=image,
                    strategy=strategy,
                    success=event['success'],
                    deployment_duration_seconds=event.get('deployment_duration_seconds')
                )
                events.append(event_obj)

        return events

    def calculate_summary(self, events: List[DeploymentEvent],
                         deployment_patterns: Dict, service_name: str) -> List[DeploymentSummary]:
        """Calculate deployment summary metrics"""
        summaries = []

        # Group events by deployment name
        by_deployment = defaultdict(list)
        for event in events:
            by_deployment[event.deployment_name].append(event)

        for deployment_name, deployment_events in by_deployment.items():
            pattern_key = deployment_name
            pattern = deployment_patterns.get(pattern_key, {})

            # Calculate success rate
            total = len(deployment_events)
            successful = sum(1 for e in deployment_events if e.success)
            success_rate = (successful / total * 100) if total > 0 else 0

            summary = DeploymentSummary(
                service=service_name,
                deployment_name=deployment_name,
                total_revisions_30_days=pattern.get('total_revisions_30_days', len(deployment_events)),
                deployment_frequency=pattern.get('deployment_frequency', 'unknown'),
                last_deployment_timestamp=pattern.get('last_deployment', 'unknown'),
                days_since_last_deployment=pattern.get('days_since_last_deployment', 0),
                strategy=pattern.get('strategy', 'unknown'),
                current_status='healthy',  # Default based on data
                current_revision=max(e.revision for e in deployment_events),
                current_image=deployment_events[0].image if deployment_events else 'unknown',
                success_rate=success_rate,
                failures=total - successful
            )
            summaries.append(summary)

        return summaries

    def extract_pbx_web_data(self) -> tuple:
        """Extract pbx-web deployment data"""
        print("Extracting pbx-web deployment data...")

        pbx_file = self.base_dir / "pbx-web-30days" / "deployments-30days.json"
        data = self.load_json_file(pbx_file)

        events = self.extract_from_deployment_data(data, "pbx-web")
        patterns = data.get('deployment_patterns', {})
        summaries = self.calculate_summary(events, patterns, "pbx-web")

        return events, summaries, data

    def extract_whisper_stt_data(self) -> tuple:
        """Extract whisper-stt deployment data"""
        print("Extracting whisper-stt deployment data...")

        whisper_file = self.base_dir / "whisper-stt-30days" / "deployments-30days.json"
        data = self.load_json_file(whisper_file)

        events = self.extract_from_deployment_data(data, "whisper-stt")
        patterns = data.get('deployment_patterns', {})
        summaries = self.calculate_summary(events, patterns, "whisper-stt")

        return events, summaries, data

    def compare_deployment_patterns(self, pbx_summaries: List[DeploymentSummary],
                                   whisper_summaries: List[DeploymentSummary]) -> Dict:
        """Compare deployment patterns between services"""
        comparison = {
            "extraction_date": datetime.now().isoformat(),
            "analysis_period": "30_days",
            "services_compared": ["pbx-web", "whisper-stt"],
            "pbx_web_deployments": [],
            "whisper_stt_deployments": [],
            "key_findings": []
        }

        # Add pbx-web data
        for summary in pbx_summaries:
            comparison["pbx_web_deployments"].append({
                "deployment_name": summary.deployment_name,
                "revisions_30_days": summary.total_revisions_30_days,
                "frequency": summary.deployment_frequency,
                "strategy": summary.strategy,
                "success_rate": summary.success_rate,
                "days_since_last": summary.days_since_last_deployment
            })

        # Add whisper-stt data
        for summary in whisper_summaries:
            comparison["whisper_stt_deployments"].append({
                "deployment_name": summary.deployment_name,
                "revisions_30_days": summary.total_revisions_30_days,
                "frequency": summary.deployment_frequency,
                "strategy": summary.strategy,
                "success_rate": summary.success_rate,
                "days_since_last": summary.days_since_last_deployment
            })

        # Generate key findings
        pbx_main = next((s for s in pbx_summaries if s.deployment_name == "pbx-web"), None)
        whisper_main = next((s for s in whisper_summaries if s.deployment_name == "whisper-stt"), None)

        if pbx_main and whisper_main:
            comparison["key_findings"] = [
                f"pbx-web had {pbx_main.total_revisions_30_days} deployments vs whisper-stt's {whisper_main.total_revisions_30_days}",
                f"pbx-web uses {pbx_main.strategy} strategy vs whisper-stt's {whisper_main.strategy}",
                f"pbx-web deployment frequency: {pbx_main.deployment_frequency} vs whisper-stt: {whisper_main.deployment_frequency}",
                f"pbx-web success rate: {pbx_main.success_rate:.1f}% vs whisper-stt: {whisper_main.success_rate:.1f}%"
            ]

        return comparison

    def save_to_json(self, data: Dict, filename: Path):
        """Save data to JSON file"""
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Saved: {filename}")

    def save_to_csv(self, events: List[DeploymentEvent], filename: Path):
        """Save deployment events to CSV file"""
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'service', 'deployment_name', 'revision', 'replicaset',
                'timestamp', 'age_days', 'status', 'replicas', 'available',
                'ready', 'image', 'strategy', 'success'
            ])
            writer.writeheader()

            for event in events:
                writer.writerow({
                    'service': event.service,
                    'deployment_name': event.deployment_name,
                    'revision': event.revision,
                    'replicaset': event.replicaset,
                    'timestamp': event.timestamp,
                    'age_days': event.age_days,
                    'status': event.status,
                    'replicas': event.replicas,
                    'available': event.available,
                    'ready': event.ready,
                    'image': event.image,
                    'strategy': event.strategy,
                    'success': event.success
                })
        print(f"Saved: {filename}")

    def create_data_sources_doc(self, pbx_data: Dict, whisper_data: Dict, output_dir: Path):
        """Document data sources and query parameters"""
        doc = {
            "extraction_date": datetime.now().isoformat(),
            "analysis_period": "30_days (2026-07-07 to 2026-08-06)",
            "data_sources": {
                "pbx_web": {
                    "cluster": pbx_data.get('infrastructure_context', {}).get('cluster', 'unknown'),
                    "namespace": pbx_data.get('infrastructure_context', {}).get('namespace', 'unknown'),
                    "query_parameters": pbx_data.get('query_parameters', {}),
                    "data_files": [
                        "kubernetes_replicasets_api",
                        "kubernetes_events_api"
                    ],
                    "raw_data_path": "research/pbx-web-30days/deployments-30days.json"
                },
                "whisper_stt": {
                    "cluster": whisper_data.get('infrastructure_context', {}).get('cluster', 'unknown'),
                    "namespace": whisper_data.get('infrastructure_context', {}).get('namespace', 'unknown'),
                    "query_parameters": whisper_data.get('query_parameters', {}),
                    "data_files": [
                        "kubernetes_replicasets_api",
                        "kubernetes_events_api",
                        "argo_workflows_api"
                    ],
                    "raw_data_path": "research/whisper-stt-30days/deployments-30days.json"
                }
            },
            "query_methods": {
                "kubectl_read_only": "kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n <namespace>",
                "replicasets_query": "kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n <namespace>",
                "events_query": "kubectl --server=http://traefik-ardenone-cluster:8001 get events -n <namespace> --sort-by='.lastTimestamp'"
            },
            "limitations": [
                "Kubernetes does not retain detailed metadata for deleted pods",
                "Historical pod deletion timestamps are estimated from ReplicaSet data",
                "Deployment duration metrics require pod log analysis (not yet implemented)",
                "Container image pull times are not captured in current data collection"
            ],
            "next_steps_for_enhanced_collection": [
                "Extract pod logs for deployment duration metrics",
                "Query Kubernetes events for ScalingReplicaSet and FailedCreate events",
                "Analyze Argo Workflows for build pipeline execution history",
                "Capture container image pull durations from pod events"
            ]
        }

        output_path = output_dir / "data_sources_documentation.json"
        self.save_to_json(doc, output_path)

        # Also create markdown version
        md_path = output_dir / "DATA_SOURCES.md"
        with open(md_path, 'w') as f:
            f.write("# Deployment Metadata - Data Sources Documentation\n\n")
            f.write(f"**Extraction Date:** {doc['extraction_date']}\n\n")
            f.write(f"**Analysis Period:** {doc['analysis_period']}\n\n")

            f.write("## Data Sources\n\n")
            for service, info in doc['data_sources'].items():
                f.write(f"### {service.replace('_', '-').title()}\n\n")
                f.write(f"- **Cluster:** {info['cluster']}\n")
                f.write(f"- **Namespace:** {info['namespace']}\n")
                f.write(f"- **Raw Data Path:** `{info['raw_data_path']}`\n\n")

            f.write("## Query Methods\n\n")
            for method, query in doc['query_methods'].items():
                f.write(f"- **{method.replace('_', ' ').title()}:** `{query}`\n")

            f.write("\n## Limitations\n\n")
            for limitation in doc['limitations']:
                f.write(f"- {limitation}\n")

            f.write("\n## Next Steps for Enhanced Collection\n\n")
            for step in doc['next_steps_for_enhanced_collection']:
                f.write(f"- {step}\n")

        print(f"Saved: {md_path}")

    def run_extraction(self):
        """Main extraction workflow"""
        print("=" * 60)
        print("Deployment Metadata Extraction")
        print("=" * 60)

        # Create output directory
        output_dir = Path("research") / "deployment-metadata-extraction"
        output_dir.mkdir(exist_ok=True)

        # Extract data from both services
        pbx_events, pbx_summaries, pbx_data = self.extract_pbx_web_data()
        whisper_events, whisper_summaries, whisper_data = self.extract_whisper_stt_data()

        # Combine all events
        all_events = pbx_events + whisper_events

        # Create comparison analysis
        comparison = self.compare_deployment_patterns(pbx_summaries, whisper_summaries)

        # Save results
        print("\nSaving extracted data...")

        # Save individual service data
        self.save_to_json(
            {"service": "pbx-web", "extraction_date": datetime.now().isoformat(), "events": [asdict(e) for e in pbx_events]},
            output_dir / "pbx-web-deployment-events.json"
        )

        self.save_to_json(
            {"service": "whisper-stt", "extraction_date": datetime.now().isoformat(), "events": [asdict(e) for e in whisper_events]},
            output_dir / "whisper-stt-deployment-events.json"
        )

        # Save combined data
        self.save_to_json(
            {"extraction_date": datetime.now().isoformat(), "total_events": len(all_events), "events": [asdict(e) for e in all_events]},
            output_dir / "all-deployment-events.json"
        )

        # Save summaries
        self.save_to_json(
            {"extraction_date": datetime.now().isoformat(), "summaries": [asdict(s) for s in (pbx_summaries + whisper_summaries)]},
            output_dir / "deployment-summaries.json"
        )

        # Save comparison
        self.save_to_json(comparison, output_dir / "deployment-comparison.json")

        # Save CSV for spreadsheet analysis
        self.save_to_csv(all_events, output_dir / "all-deployment-events.csv")
        self.save_to_csv(pbx_events, output_dir / "pbx-web-events.csv")
        self.save_to_csv(whisper_events, output_dir / "whisper-stt-events.csv")

        # Create data sources documentation
        self.create_data_sources_doc(pbx_data, whisper_data, output_dir)

        # Print summary
        print("\n" + "=" * 60)
        print("Extraction Complete!")
        print("=" * 60)
        print(f"Total deployment events extracted: {len(all_events)}")
        print(f"pbx-web events: {len(pbx_events)}")
        print(f"whisper-stt events: {len(whisper_events)}")
        print(f"\nOutput directory: {output_dir}")
        print("\nFiles generated:")
        for file in output_dir.glob("*"):
            print(f"  - {file.name}")

        print("\n" + "=" * 60)
        print("Key Findings:")
        print("=" * 60)
        for finding in comparison.get('key_findings', []):
            print(f"  • {finding}")

def main():
    """Main entry point"""
    extractor = DeploymentExtractor()
    extractor.run_extraction()

if __name__ == "__main__":
    main()