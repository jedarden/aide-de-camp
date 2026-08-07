#!/usr/bin/env python3
"""
Failure Pattern Analysis Script
Analyzes failed deployments to identify and categorize failure patterns by error type, phase, and message.
"""

import json
import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

class FailurePatternAnalyzer:
    def __init__(self, data_dir: str = "/home/coding/aide-de-camp/data"):
        self.data_dir = Path(data_dir)
        self.services = ["pbx-web", "whisper-stt"]
        self.failures_by_service = defaultdict(lambda: defaultdict(list))
        self.error_patterns = defaultdict(list)

    def categorize_error_type(self, error_data: Dict) -> str:
        """Categorize error by type (ExitCode, OOMKilled, Probe failure, etc.)"""
        if error_data.get("reason") == "OOMKilled":
            return "OOM_Killed"
        elif error_data.get("exit_code") is not None:
            return f"ExitCode_{error_data['exit_code']}"
        elif "probe" in error_data.get("message", "").lower():
            return "Probe_Failure"
        elif "image" in error_data.get("message", "").lower() or "pull" in error_data.get("message", "").lower():
            return "Image_Pull_Failure"
        elif "crash" in error_data.get("message", "").lower():
            return "Crash_Loop_BackOff"
        elif "error" in error_data.get("message", "").lower():
            return "Error_State"
        else:
            return "Other"

    def categorize_deployment_phase(self, error_data: Dict) -> str:
        """Categorize failure by deployment phase"""
        message = error_data.get("message", "").lower()
        reason = error_data.get("reason", "").lower()

        # Image pull phase
        if "image" in message and "pull" in message:
            return "Image_Pull"
        elif "err_image" in message or "imagepullbackoff" in reason:
            return "Image_Pull"

        # Container startup phase
        elif "create" in message or "start" in message:
            return "Container_Startup"
        elif "container" in message and "creating" in message:
            return "Container_Startup"

        # Health check phase
        elif "probe" in message or "readiness" in message or "liveness" in message:
            return "Health_Check"
        elif "probe" in reason:
            return "Health_Check"

        # Runtime phase
        elif "runtime" in message or "execution" in message:
            return "Runtime"

        # Default to unknown if we can't determine
        return "Unknown"

    def normalize_error_message(self, message: str) -> str:
        """Normalize error messages for pattern matching using fuzzy matching"""
        # Remove specific identifiers (timestamps, UUIDs, IPs, pod names, replica sets)
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}T?\s*\d{2}:\d{2}:\d{2}', '[TIMESTAMP]', message)
        normalized = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '[UUID]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[IP]', normalized)
        normalized = re.sub(r'pod-[a-z0-9]+-[a-z0-9]+', '[POD_NAME]', normalized, flags=re.IGNORECASE)

        # Add more aggressive patterns for replica sets and image tags
        normalized = re.sub(r'[a-z]+-web-[a-f0-9]{8,}', '[REPLICASET]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'[a-z]+-stt-[a-f0-9]{8,}', '[REPLICASET]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'ronaldraygun/[a-z-]+:[\d.]+', '[IMAGE]', normalized, flags=re.IGNORECASE)

        # File paths
        normalized = re.sub(r'/[a-z0-9/_\-\.]+\.(wav|mp3|ogg|log)', '[FILE_PATH]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\d{10,}', '[NUMBER]', normalized)

        return normalized.strip()

    def extract_error_patterns(self, messages: List[str], top_n: int = 5) -> List[Dict]:
        """Extract top N most frequent error message patterns"""
        normalized_messages = [self.normalize_error_message(msg) for msg in messages]
        message_counts = Counter(normalized_messages)

        top_patterns = []
        for pattern, count in message_counts.most_common(top_n):
            top_patterns.append({
                "pattern": pattern,
                "frequency": count,
                "percentage": round((count / len(messages)) * 100, 2) if messages else 0
            })

        return top_patterns

    def load_deployment_data(self) -> Dict:
        """Load deployment data from deployment_data_raw.json"""
        deployment_file = Path("/home/coding/aide-de-camp/deployment_data_raw.json")
        if deployment_file.exists():
            with open(deployment_file) as f:
                return json.load(f)
        return {}

    def analyze_failure_patterns(self) -> Dict:
        """Main analysis function to identify failure patterns"""
        print("Loading deployment data...")
        deployment_data = self.load_deployment_data()

        results = {
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "services_analyzed": self.services,
                "analysis_type": "failure_pattern_identification"
            },
            "by_service": {}
        }

        cluster_deployments = deployment_data.get("cluster_deployments", {})

        for service in self.services:
            print(f"Analyzing {service}...")
            service_results = {
                "error_type_counts": defaultdict(int),
                "phase_breakdown": defaultdict(int),
                "error_messages": [],
                "deployment_failures": []
            }

            if service in cluster_deployments:
                service_data = cluster_deployments[service]
                replica_history = service_data.get("replica_history", [])

                for replica in replica_history:
                    status = replica.get("status", "unknown")

                    # Only analyze non-successful replicas
                    if status != "successful":
                        # Create error message from replica data
                        error_msg = self._construct_replica_error_message(service, replica)
                        service_results["error_messages"].append(error_msg)

                        # Categorize error type
                        error_type = self._categorize_replica_error_type(replica)
                        service_results["error_type_counts"][error_type] += 1

                        # Categorize deployment phase
                        phase = self._determine_replica_failure_phase(replica)
                        service_results["phase_breakdown"][phase] += 1

                        # Track deployment failures
                        if status in ["scaled_down_or_failed", "failed"]:
                            service_results["deployment_failures"].append({
                                "timestamp": replica.get("created_at", "unknown"),
                                "replicaSet": replica.get("name", "unknown"),
                                "image": replica.get("image", "unknown"),
                                "status": status,
                                "phase": phase,
                                "error_type": error_type
                            })

            # Calculate top error patterns
            if service_results["error_messages"]:
                service_results["top_error_patterns"] = self.extract_error_patterns(
                    service_results["error_messages"], top_n=5
                )
            else:
                service_results["top_error_patterns"] = []

            # Convert defaultdicts to regular dicts for JSON serialization
            service_results["error_type_counts"] = dict(service_results["error_type_counts"])
            service_results["phase_breakdown"] = dict(service_results["phase_breakdown"])

            results["by_service"][service] = service_results

        # Cross-service analysis
        results["shared_patterns"] = self.find_shared_patterns(results)
        results["service_specific_patterns"] = self.find_service_specific_patterns(results)

        return results

    def _categorize_replica_error_type(self, replica: Dict) -> str:
        """Categorize replica error by type"""
        status = replica.get("status", "unknown")

        if status == "scaled_down_or_failed":
            return "Scaled_Down_Or_Failed"
        elif status == "failed":
            return "Failed"
        elif status == "rolled_over":
            return "Rolled_Over"
        else:
            return "Other"

    def _determine_replica_failure_phase(self, replica: Dict) -> str:
        """Determine the deployment phase where failure occurred"""
        status = replica.get("status", "unknown")
        replicas = replica.get("replicas", 0)
        ready_replicas = replica.get("ready_replicas", 0)
        available_replicas = replica.get("available_replicas", 0)

        if status == "scaled_down_or_failed":
            if replicas == 0:
                return "Runtime"
            else:
                return "Container_Startup"
        elif status == "rolled_over":
            return "Runtime"
        elif status == "failed":
            if ready_replicas == 0 and available_replicas == 0:
                return "Container_Startup"
            elif ready_replicas < replicas:
                return "Health_Check"
            else:
                return "Runtime"
        else:
            return "Unknown"

    def _construct_replica_error_message(self, service: str, replica: Dict) -> str:
        """Construct error message from replica data"""
        status = replica.get("status", "unknown")
        name = replica.get("name", "unknown")
        image = replica.get("image", "unknown")

        if status == "scaled_down_or_failed":
            return f"[{service}] ReplicaSet {name} with image {image} was scaled down or failed"
        elif status == "failed":
            return f"[{service}] ReplicaSet {name} with image {image} failed"
        elif status == "rolled_over":
            return f"[{service}] ReplicaSet {name} with image {image} was rolled over to new version"
        else:
            return f"[{service}] ReplicaSet {name} with image {image} has status: {status}"

    def find_shared_patterns(self, results: Dict) -> Dict:
        """Identify error patterns that appear in both services"""
        shared = {
            "error_types": set(),
            "phases": set(),
            "error_message_patterns": []
        }

        error_types_by_service = {}
        phases_by_service = {}

        for service in self.services:
            service_data = results["by_service"][service]
            error_types_by_service[service] = set(service_data["error_type_counts"].keys())
            phases_by_service[service] = set(service_data["phase_breakdown"].keys())

        # Find shared error types
        shared["error_types"] = error_types_by_service[self.services[0]] & error_types_by_service[self.services[1]]

        # Find shared phases
        shared["phases"] = phases_by_service[self.services[0]] & phases_by_service[self.services[1]]

        # Find shared error message patterns (normalized)
        all_patterns = []
        for service in self.services:
            for pattern in results["by_service"][service].get("top_error_patterns", []):
                all_patterns.append({
                    "service": service,
                    "pattern": pattern["pattern"],
                    "frequency": pattern["frequency"]
                })

        # Look for patterns that appear in both services
        pattern_by_text = defaultdict(list)
        for item in all_patterns:
            pattern_by_text[item["pattern"]].append(item["service"])

        shared["error_message_patterns"] = [
            {"pattern": pattern, "services": list(set(services))}
            for pattern, services in pattern_by_text.items()
            if len(set(services)) > 1
        ]

        return {
            "error_types": list(shared["error_types"]),
            "phases": list(shared["phases"]),
            "error_message_patterns": shared["error_message_patterns"]
        }

    def find_service_specific_patterns(self, results: Dict) -> Dict:
        """Identify patterns unique to each service"""
        specific = {}

        shared = results["shared_patterns"]

        for service in self.services:
            service_data = results["by_service"][service]

            # Service-specific error types
            specific_error_types = [
                error_type for error_type in service_data["error_type_counts"].keys()
                if error_type not in shared["error_types"]
            ]

            # Service-specific phases
            specific_phases = [
                phase for phase in service_data["phase_breakdown"].keys()
                if phase not in shared["phases"]
            ]

            # Service-specific error patterns
            specific_patterns = [
                pattern for pattern in service_data.get("top_error_patterns", [])
                if not any(shared_pattern["pattern"] == pattern["pattern"]
                          for shared_pattern in shared["error_message_patterns"])
            ]

            specific[service] = {
                "specific_error_types": specific_error_types,
                "specific_phases": specific_phases,
                "specific_error_patterns": specific_patterns
            }

        return specific

    def generate_summary(self, results: Dict) -> Dict:
        """Generate executive summary of findings"""
        summary = {
            "total_errors_analyzed": 0,
            "services_with_failures": [],
            "most_common_error_type": None,
            "most_common_phase": None,
            "key_findings": []
        }

        all_error_types = []
        all_phases = []

        for service in self.services:
            service_data = results["by_service"][service]
            error_count = sum(service_data["error_type_counts"].values())
            summary["total_errors_analyzed"] += error_count

            if error_count > 0:
                summary["services_with_failures"].append(service)

            all_error_types.extend(list(service_data["error_type_counts"].keys()))
            all_phases.extend(list(service_data["phase_breakdown"].keys()))

        # Most common patterns
        if all_error_types:
            summary["most_common_error_type"] = Counter(all_error_types).most_common(1)[0][0]
        if all_phases:
            summary["most_common_phase"] = Counter(all_phases).most_common(1)[0][0]

        # Key findings
        if not summary["services_with_failures"]:
            summary["key_findings"].append("No significant failures detected in 30-day period")
        else:
            summary["key_findings"].append(
                f"Failures detected in {len(summary['services_with_failures'])} service(s)"
            )

        if results["shared_patterns"]["error_types"]:
            summary["key_findings"].append(
                f"Shared failure patterns across services: {len(results['shared_patterns']['error_types'])} error types"
            )

        return summary

    def run_analysis(self) -> Dict:
        """Run complete failure pattern analysis"""
        print("Starting failure pattern analysis...")
        results = self.analyze_failure_patterns()
        results["executive_summary"] = self.generate_summary(results)
        print("Analysis complete!")
        return results


def main():
    """Main entry point"""
    analyzer = FailurePatternAnalyzer()
    results = analyzer.run_analysis()

    # Output results
    output_file = "/home/coding/aide-de-camp/failure_pattern_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_file}")
    print("\n" + "="*60)
    print("EXECUTIVE SUMMARY")
    print("="*60)
    print(json.dumps(results["executive_summary"], indent=2))
    print("\n" + "="*60)
    print("DETAILED RESULTS BY SERVICE")
    print("="*60)
    for service, data in results["by_service"].items():
        print(f"\n{service.upper()}:")
        print(f"  Error Types: {data['error_type_counts']}")
        print(f"  Phases: {data['phase_breakdown']}")
        if data['deployment_failures']:
            print(f"  Deployment Failures: {len(data['deployment_failures'])}")


if __name__ == "__main__":
    main()
