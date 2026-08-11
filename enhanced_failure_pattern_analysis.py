#!/usr/bin/env python3
"""
Enhanced Failure Pattern Analysis Script
Provides comprehensive analysis including phase categorization, error type grouping, and pattern detection.
"""

import json
import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

class EnhancedFailurePatternAnalyzer:
    def __init__(self, data_dir: str = "/home/coding/aide-de-camp/data"):
        self.data_dir = Path(data_dir)
        self.services = ["pbx-web", "whisper-stt"]
        
    def categorize_exit_code_type(self, exit_code: int) -> str:
        """Categorize exit codes into meaningful groups"""
        if exit_code == 1:
            return "ExitCode_1_ApplicationError"
        elif exit_code == 137:
            return "ExitCode_137_SIGKILL_OOM"
        elif exit_code == 139:
            return "ExitCode_139_SegmentationFault"
        elif exit_code == 125:
            return "ExitCode_125_ContainerFailed"
        elif exit_code == 126:
            return "ExitCode_126_CommandNotExecutable"
        elif exit_code == 127:
            return "ExitCode_127_CommandNotFound"
        elif exit_code == 130:
            return "ExitCode_130_SIGINT_CtrlC"
        elif exit_code == 143:
            return "ExitCode_143_SIGTERM_GracefulShutdown"
        else:
            return f"ExitCode_{exit_code}_Unknown"

    def categorize_error_type(self, error_data: Dict) -> str:
        """Categorize error by type with enhanced categories"""
        reason = error_data.get("reason", "")
        message = error_data.get("message", "").lower()
        
        # OOM Killed
        if reason == "OOMKilled" or "oom" in message:
            return "OOM_Kill"
        
        # Exit code analysis
        elif error_data.get("exit_code") is not None:
            return self.categorize_exit_code_type(error_data['exit_code'])
        
        # Probe failures
        elif "probe" in message or "readiness" in message or "liveness" in message:
            return "Probe_Failure"
        
        # Image pull failures
        elif "image" in message and "pull" in message:
            return "Image_Pull_Failure"
        elif "backoff" in message and "image" in message:
            return "Image_Pull_BackOff"
        
        # Crash loop
        elif "crash" in message or "loop" in message:
            return "Crash_Loop_BackOff"
        
        # Runtime errors
        elif "exception" in message or "traceback" in message or "error" in message:
            return "Runtime_Error"
        
        # Network/connection issues
        elif "connection" in message or "network" in message or "timeout" in message:
            return "Network_Connection_Error"
        
        # Filesystem issues
        elif "permission" in message or "filesystem" in message or "mount" in message:
            return "Filesystem_Permission_Error"
        
        # Resource constraints
        elif "resource" in message or "cpu" in message or "memory" in message:
            return "Resource_Constraint"
        
        else:
            return "Other_Error"

    def categorize_deployment_phase(self, error_data: Dict) -> str:
        """Enhanced deployment phase categorization"""
        message = error_data.get("message", "").lower()
        reason = error_data.get("reason", "").lower()
        source = error_data.get("source", "")

        # Image pull phase
        if "imagepullbackoff" in reason or ("image" in message and "pull" in message):
            return "Image_Pull"
        elif "err_image" in message or "image" in message and "backoff" in message:
            return "Image_Pull"

        # Container startup phase  
        elif "create" in message and "container" in message:
            return "Container_Startup"
        elif "start" in message and "container" in message:
            return "Container_Startup"
        elif "run" in message and "container" in message:
            return "Container_Startup"

        # Health check phase
        elif "probe" in message or "readiness" in message or "liveness" in message:
            return "Health_Check"
        elif "probe" in reason:
            return "Health_Check"
        elif "startup" in message and "probe" in message:
            return "Health_Check"

        # Runtime phase
        elif "runtime" in message or "execution" in message:
            return "Runtime"
        elif "exception" in message or "traceback" in message:
            return "Runtime"
        elif "connection" in message or "network" in message:
            return "Runtime"

        # Configuration phase
        elif "config" in message or "annotation" in message:
            return "Configuration"

        # Infrastructure phase
        elif "pod" in message and ("failed" in message or "evicted" in message):
            return "Infrastructure"

        return "Unknown"

    def normalize_error_message(self, message: str) -> str:
        """Enhanced message normalization for pattern matching"""
        # Remove specific identifiers
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}T?\s*\d{2}:\d{2}:\d{2}', '[TIMESTAMP]', message)
        normalized = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '[UUID]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[IP]', normalized)
        normalized = re.sub(r'pod-[a-z0-9]+-[a-z0-9]+', '[POD_NAME]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'/[a-z0-9/_\-\.]+\.(wav|mp3|ogg|log|txt|json)', '[FILE_PATH]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\d{10,}', '[NUMBER]', normalized)
        normalized = re.sub(r'ronaldraygun/[a-z0-9\-]+:\d+\.\d+\.\d+', '[IMAGE_TAG]', normalized, flags=re.IGNORECASE)
        
        # Normalize common error patterns
        normalized = re.sub(r'errno \d+', '[ERRNO]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'signal \d+', '[SIGNAL]', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\(.*?\)', '', normalized)  # Remove parenthetical info
        
        return normalized.strip()

    def extract_error_patterns(self, messages: List[str], top_n: int = 10) -> List[Dict]:
        """Extract top N most frequent error message patterns"""
        if not messages:
            return []
            
        normalized_messages = [self.normalize_error_message(msg) for msg in messages]
        message_counts = Counter(normalized_messages)

        top_patterns = []
        for pattern, count in message_counts.most_common(top_n):
            percentage = round((count / len(messages)) * 100, 2)
            top_patterns.append({
                "pattern": pattern,
                "frequency": count,
                "percentage": percentage
            })

        return top_patterns

    def load_all_error_data(self) -> Dict:
        """Load all available error data from multiple sources"""
        all_data = {}
        
        # Load enhanced error metrics
        error_files = [
            "error_latency_metrics_30d_enhanced_20260806_211642.json",
            "error_latency_metrics_30d_enhanced_20260806_160930.json"
        ]
        
        for error_file in error_files:
            file_path = self.data_dir / error_file
            if file_path.exists():
                with open(file_path) as f:
                    data = json.load(f)
                    all_data.update(data)
                    break
        
        # Load existing failure analysis
        failure_file = self.data_dir / "adc-1gmwn" / "failure_analysis_report.json"
        if failure_file.exists():
            with open(failure_file) as f:
                all_data["historical_failure_analysis"] = json.load(f)
        
        # Load deployment events
        events_file = Path("/home/coding/aide-de-camp/deployment-events-30days.json")
        if events_file.exists():
            with open(events_file) as f:
                all_data["deployment_events"] = json.load(f)
                
        return all_data

    def analyze_comprehensive_patterns(self) -> Dict:
        """Comprehensive failure pattern analysis"""
        print("Loading comprehensive error data...")
        all_data = self.load_all_error_data()

        results = {
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "services_analyzed": self.services,
                "analysis_type": "comprehensive_failure_pattern_analysis",
                "data_sources": list(all_data.keys())
            },
            "by_service": {}
        }

        for service in self.services:
            print(f"Analyzing {service}...")
            service_results = {
                "error_type_counts": defaultdict(int),
                "phase_breakdown": defaultdict(int),
                "error_messages": [],
                "deployment_failures": [],
                "infrastructure_failures": [],
                "service_specific_failures": []
            }

            # Analyze deployment events
            if "deployment_events" in all_data:
                events_key = f"{service.replace('-', '_')}_deployments"
                if events_key in all_data["deployment_events"]:
                    deployments = all_data["deployment_events"][events_key].get("deployment_events", [])
                    for event in deployments:
                        if event.get("outcome") not in ["success", "succeeded"]:
                            failure_info = {
                                "timestamp": event.get("timestamp"),
                                "event_type": event.get("event_type"),
                                "outcome": event.get("outcome"),
                                "image": event.get("image"),
                                "notes": event.get("notes")
                            }
                            
                            if event.get("event_type") == "deployment_rollback":
                                service_results["deployment_failures"].append(failure_info)

            # Analyze error metrics from enhanced data
            if "services" in all_data and service in all_data["services"]:
                service_error_data = all_data["services"][service]

                # Pod errors
                if "error_metrics" in service_error_data:
                    pod_metrics = service_error_data["error_metrics"].get("pod_logs", {})
                    if pod_metrics.get("error_samples"):
                        for error_msg in pod_metrics["error_samples"]:
                            service_results["error_messages"].append(str(error_msg))

                            error_data_point = {
                                "message": str(error_msg),
                                "source": "pod_logs"
                            }
                            error_type = self.categorize_error_type(error_data_point)
                            phase = self.categorize_deployment_phase(error_data_point)

                            service_results["error_type_counts"][error_type] += 1
                            service_results["phase_breakdown"][phase] += 1

                # Infrastructure failures
                if pod_metrics.get("pods_with_oom_kills", 0) > 0:
                    service_results["infrastructure_failures"].append({
                        "type": "OOM_Kill",
                        "count": pod_metrics.get("total_oom_kill_count", 0),
                        "pods_affected": pod_metrics.get("pods_with_oom_kills", 0)
                    })

            # Analyze historical failure data
            if "historical_failure_analysis" in all_data:
                hist_data = all_data["historical_failure_analysis"]
                if "service_breakdown" in hist_data and service in hist_data["service_breakdown"]:
                    service_hist = hist_data["service_breakdown"][service]
                    if "categories" in service_hist:
                        for category, count in service_hist["categories"].items():
                            if category == "infrastructure":
                                service_results["infrastructure_failures"].append({
                                    "type": "Historical_Infrastructure",
                                    "count": count
                                })
                            elif category == "service-specific":
                                service_results["service_specific_failures"].append({
                                    "type": "Historical_Service_Specific",
                                    "count": count
                                })

            # Extract top error patterns
            if service_results["error_messages"]:
                service_results["top_error_patterns"] = self.extract_error_patterns(
                    service_results["error_messages"], top_n=10
                )
            else:
                service_results["top_error_patterns"] = []

            # Convert defaultdicts to regular dicts
            service_results["error_type_counts"] = dict(service_results["error_type_counts"])
            service_results["phase_breakdown"] = dict(service_results["phase_breakdown"])

            results["by_service"][service] = service_results

        # Cross-service analysis
        results["cross_service_analysis"] = self.analyze_cross_service_patterns(results)
        results["executive_summary"] = self.generate_executive_summary(results)

        return results

    def analyze_cross_service_patterns(self, results: Dict) -> Dict:
        """Analyze patterns across services"""
        cross_analysis = {
            "shared_error_types": [],
            "shared_phases": [],
            "shared_error_patterns": [],
            "service_specific_analysis": {}
        }

        error_types_by_service = {}
        phases_by_service = {}

        for service in self.services:
            service_data = results["by_service"][service]
            error_types_by_service[service] = set(service_data["error_type_counts"].keys())
            phases_by_service[service] = set(service_data["phase_breakdown"].keys())

        # Find shared patterns
        if len(self.services) >= 2:
            shared_errors = error_types_by_service[self.services[0]] & error_types_by_service[self.services[1]]
            shared_phases = phases_by_service[self.services[0]] & phases_by_service[self.services[1]]

            cross_analysis["shared_error_types"] = list(shared_errors)
            cross_analysis["shared_phases"] = list(shared_phases)

        # Service-specific analysis
        for service in self.services:
            service_data = results["by_service"][service]
            
            service_specific = {
                "unique_error_types": list(error_types_by_service[service] - set(cross_analysis["shared_error_types"])),
                "unique_phases": list(phases_by_service[service] - set(cross_analysis["shared_phases"])),
                "total_errors": sum(service_data["error_type_counts"].values()),
                "deployment_failures": len(service_data["deployment_failures"]),
                "infrastructure_failures": len(service_results["infrastructure_failures"]) if service in results["by_service"] else 0
            }
            
            cross_analysis["service_specific_analysis"][service] = service_specific

        return cross_analysis

    def generate_executive_summary(self, results: Dict) -> Dict:
        """Generate comprehensive executive summary"""
        summary = {
            "analysis_period": "30 days",
            "total_services": len(self.services),
            "services_with_failures": [],
            "total_errors_identified": 0,
            "error_type_distribution": {},
            "phase_distribution": {},
            "most_common_error_types": [],
            "most_common_phases": [],
            "key_findings": [],
            "recommendations": []
        }

        all_error_types = []
        all_phases = []

        for service in self.services:
            service_data = results["by_service"][service]
            total_errors = sum(service_data["error_type_counts"].values())
            summary["total_errors_identified"] += total_errors

            if total_errors > 0 or service_data["deployment_failures"]:
                summary["services_with_failures"].append(service)

            all_error_types.extend(list(service_data["error_type_counts"].items()))
            all_phases.extend(list(service_data["phase_breakdown"].items()))

        # Most common patterns
        if all_error_types:
            error_type_counts = Counter()
            for error_type, count in all_error_types:
                error_type_counts[error_type] += count
            summary["most_common_error_types"] = [
                {"type": error_type, "count": count}
                for error_type, count in error_type_counts.most_common(5)
            ]

        if all_phases:
            phase_counts = Counter()
            for phase, count in all_phases:
                phase_counts[phase] += count
            summary["most_common_phases"] = [
                {"phase": phase, "count": count}
                for phase, count in phase_counts.most_common(5)
            ]

        # Generate key findings and recommendations
        if not summary["services_with_failures"]:
            summary["key_findings"].append("No significant deployment failures detected in the 30-day analysis period")
        else:
            summary["key_findings"].append(f"Deployment failures detected in {len(summary['services_with_failures'])} service(s)")
            
            if results["cross_service_analysis"]["shared_error_types"]:
                summary["key_findings"].append(f"Shared failure patterns across services: {len(results['cross_service_analysis']['shared_error_types'])} error types")

            summary["recommendations"].append("Monitor services with detected failures for recurrence patterns")
            summary["recommendations"].append("Consider implementing automated rollback procedures for common failure modes")

        return summary

    def run_analysis(self) -> Dict:
        """Run comprehensive analysis"""
        print("Starting comprehensive failure pattern analysis...")
        results = self.analyze_comprehensive_patterns()
        print("Analysis complete!")
        return results


def main():
    """Main entry point"""
    analyzer = EnhancedFailurePatternAnalyzer()
    results = analyzer.run_analysis()

    # Save results
    output_file = "/home/coding/aide-de-camp/failure_pattern_analysis_comprehensive.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nComprehensive results saved to {output_file}")

    # Print executive summary
    print("\n" + "="*80)
    print("COMPREHENSIVE FAILURE PATTERN ANALYSIS - EXECUTIVE SUMMARY")
    print("="*80)
    print(json.dumps(results["executive_summary"], indent=2))

    print("\n" + "="*80)
    print("DETAILED RESULTS BY SERVICE")
    print("="*80)
    for service, data in results["by_service"].items():
        print(f"\n{service.upper()}:")
        print(f"  Error Type Distribution: {data['error_type_counts']}")
        print(f"  Phase Distribution: {data['phase_breakdown']}")
        if data['deployment_failures']:
            print(f"  Deployment Failures: {len(data['deployment_failures'])}")
        if data['top_error_patterns']:
            print(f"  Top Error Patterns: {len(data['top_error_patterns'])} patterns identified")
            for i, pattern in enumerate(data['top_error_patterns'][:3], 1):
                print(f"    {i}. {pattern['pattern'][:80]}... (freq: {pattern['frequency']})")


if __name__ == "__main__":
    main()
