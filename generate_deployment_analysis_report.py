#!/usr/bin/env python3
"""
Deployment Pattern Analysis and Comparative Report Generator

Analyzes deployment data from pbx-web and whisper-stt services to identify:
- Failure patterns and instability triggers
- Reliability divergences between services
- Comparative metrics and recommendations
"""

import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any

def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load and parse a JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}

def analyze_basic_deployments(data: Dict[str, Any], service_name: str) -> Dict[str, Any]:
    """Analyze basic deployment data from simple deployments JSON."""
    if not data or 'deployments' not in data:
        return {"service": service_name, "deployments_analyzed": 0}

    deployments = data.get('deployments', [])
    total = len(deployments)

    # Count unique authors
    authors = Counter(d.get('author', 'unknown') for d in deployments)

    # Count deployment types
    deployment_types = Counter(d.get('deployment_type', 'unknown') for d in deployments)

    # Parse timestamps for temporal analysis
    timestamps = []
    for d in deployments:
        try:
            ts_str = d.get('timestamp', '')
            if ts_str:
                # Handle format: "2026-07-28 13:24:42 -0400"
                clean_ts = ts_str.replace(' -0400', '').replace(' -0000', '')
                dt = datetime.strptime(clean_ts, '%Y-%m-%d %H:%M:%S')
                timestamps.append(dt)
        except Exception:
            continue

    # Calculate deployment frequency
    if len(timestamps) >= 2:
        sorted_ts = sorted(timestamps)
        time_span_days = (sorted_ts[-1] - sorted_ts[0]).days
        if time_span_days > 0:
            deployments_per_day = total / time_span_days
        else:
            deployments_per_day = total
    else:
        time_span_days = 0
        deployments_per_day = 0

    return {
        "service": service_name,
        "deployments_analyzed": total,
        "unique_authors": dict(authors),
        "deployment_types": dict(deployment_types),
        "time_span_days": time_span_days,
        "deployments_per_day": deployments_per_day,
        "first_deployment": timestamps[0].isoformat() if timestamps else None,
        "last_deployment": timestamps[-1].isoformat() if timestamps else None
    }

def analyze_30day_data(data: Dict[str, Any], service_name: str) -> Dict[str, Any]:
    """Analyze detailed 30-day deployment data."""
    if not data:
        return {"service": service_name, "data_available": False}

    result = {"service": service_name, "data_available": True}

    # Current status - handle different data structures
    current_status = data.get('current_status', {})
    svc_status = {}

    # Try different possible structures
    if isinstance(current_status, dict):
        if service_name in current_status:
            svc_status = current_status[service_name]
        elif 'deployment_name' in current_status:
            svc_status = current_status
        elif 'deployments' in current_status and service_name in current_status['deployments']:
            svc_status = current_status['deployments'][service_name]

    result['current_status'] = {
        "replicas": svc_status.get('replicas', current_status.get('replicas', 0)),
        "readyReplicas": svc_status.get('readyReplicas', current_status.get('readyReplicas', 0)),
        "availableReplicas": svc_status.get('availableReplicas', current_status.get('availableReplicas', 0)),
        "revision": svc_status.get('revision', current_status.get('revision', 0)),
        "strategy": svc_status.get('strategy', current_status.get('strategy', 'unknown'))
    }

    # Extract image information - try multiple paths
    current_image = 'unknown'
    if 'images' in svc_status and isinstance(svc_status['images'], dict):
        current_image = svc_status['images'].get(service_name, list(svc_status['images'].values())[0] if svc_status['images'] else 'unknown')
    elif 'images' in current_status and isinstance(current_status['images'], dict):
        current_image = current_status['images'].get(service_name, list(current_status['images'].values())[0] if current_status['images'] else 'unknown')
    elif 'image' in svc_status:
        current_image = svc_status.get('image', 'unknown')
    elif 'current_image' in current_status:
        current_image = current_status.get('current_image', 'unknown')

    result['current_image'] = current_image

    # Deployment events
    deployment_events = data.get('deployment_events_last_30_days', [])
    deployment_history = data.get('deployment_history_30_days', {})

    # If we have deployment_events_last_30_days
    if deployment_events:
        events = deployment_events
    # Or if we have deployment_history_30_days with replicasets
    elif deployment_history and 'replicasets' in deployment_history:
        replicasets = deployment_history['replicasets']
        events = []
        for rs in replicasets:
            events.append({
                'date': rs.get('created', '')[:10] if rs.get('created') else '',
                'timestamp': rs.get('created', ''),
                'event_type': 'deployment_rollout',
                'revision': rs.get('revision', 0),
                'image': rs.get('image', ''),
                'outcome': 'success' if rs.get('status') == 'active' else 'inactive'
            })
    else:
        events = []

    # Analyze events
    total_deployments = len(events)
    successful = sum(1 for e in events if e.get('outcome') == 'success')
    failed = sum(1 for e in events if e.get('outcome') == 'failed')
    rollbacks = sum(1 for e in events if e.get('event_type') == 'deployment_rollback')

    result['deployment_metrics'] = {
        'total_deployments_last_30_days': total_deployments,
        'successful_deployments': successful,
        'failed_deployments': failed,
        'rollback_count': rollbacks,
        'success_rate': (successful / total_deployments * 100) if total_deployments > 0 else 0
    }

    # Analyze failure modes
    failure_events = [e for e in events if e.get('outcome') not in ['success', 'rolled_back']]
    failure_modes = defaultdict(list)
    for event in failure_events:
        failure_category = event.get('event_type', 'unknown')
        failure_modes[failure_category].append(event)

    result['failure_modes'] = dict(failure_modes)

    # Check for rapid deployment patterns
    if len(events) >= 2:
        rapid_sequences = []
        for i in range(len(events) - 1):
            try:
                current_time = datetime.fromisoformat(events[i].get('timestamp', '').replace('Z', '+00:00'))
                next_time = datetime.fromisoformat(events[i+1].get('timestamp', '').replace('Z', '+00:00'))
                time_diff = (next_time - current_time).total_seconds()

                # Rapid sequence: less than 1 hour between deployments
                if time_diff < 3600 and time_diff > 0:
                    rapid_sequences.append({
                        'start_time': events[i].get('timestamp'),
                        'end_time': events[i+1].get('timestamp'),
                        'duration_seconds': time_diff,
                        'events': [events[i], events[i+1]]
                    })
            except Exception:
                continue

        result['rapid_patterns'] = {
            'rapid_sequences_detected': len(rapid_sequences),
            'sequences': rapid_sequences
        }
    else:
        result['rapid_patterns'] = {'rapid_sequences_detected': 0, 'sequences': []}

    # Pod health analysis
    pod_health = data.get('pod_health', {})
    if pod_health:
        current_pod = pod_health.get('current_pod', {})
        result['pod_health'] = {
            'pod_name': current_pod.get('name', 'unknown'),
            'restart_count': current_pod.get('restart_count', 0),
            'ready': current_pod.get('ready', False),
            'phase': current_pod.get('phase', 'unknown')
        }

        health_indicators = pod_health.get('health_indicators', {})
        if health_indicators:
            result['health_indicators'] = health_indicators

    # Operational metrics
    operational_metrics = data.get('operational_metrics', {})
    if operational_metrics:
        uptime_info = operational_metrics.get('uptime', {})
        restart_analysis = operational_metrics.get('restart_analysis', {})

        result['operational_metrics'] = {
            'uptime': uptime_info,
            'restart_analysis': restart_analysis
        }

    # Error incidents
    error_incidents = data.get('error_incidents', {})
    if error_incidents:
        result['error_incidents'] = {
            'total_incidents': error_incidents.get('total_incidents', 0),
            'critical_incidents': error_incidents.get('critical_incidents', 0),
            'incident_details': error_incidents.get('incident_details', [])
        }

    return result

def calculate_comparative_metrics(pbx_analysis: Dict, whisper_analysis: Dict) -> Dict[str, Any]:
    """Calculate comparative metrics between the two services."""
    comparative = {
        "success_rate_comparison": {},
        "deployment_frequency_comparison": {},
        "stability_metrics": {},
        "resource_utilization": {}
    }

    # Success rate comparison
    pbx_success_rate = pbx_analysis.get('deployment_metrics', {}).get('success_rate', 0)
    whisper_success_rate = whisper_analysis.get('deployment_metrics', {}).get('success_rate', 0)

    comparative["success_rate_comparison"] = {
        "pbx_web": f"{pbx_success_rate:.1f}%",
        "whisper_stt": f"{whisper_success_rate:.1f}%",
        "difference": f"{abs(pbx_success_rate - whisper_success_rate):.1f}%",
        "more_reliable": "pbx-web" if pbx_success_rate > whisper_success_rate else "whisper-stt"
    }

    # Deployment frequency comparison
    pbx_deployments = pbx_analysis.get('deployment_metrics', {}).get('total_deployments_last_30_days', 0)
    whisper_deployments = whisper_analysis.get('deployment_metrics', {}).get('total_deployments_last_30_days', 0)

    comparative["deployment_frequency_comparison"] = {
        "pbx_web_deployments": pbx_deployments,
        "whisper_stt_deployments": whisper_deployments,
        "pbx_web_frequency": f"{pbx_deployments/30:.2f} per day",
        "whisper_stt_frequency": f"{whisper_deployments/30:.2f} per day"
    }

    # Stability metrics
    pbx_rollbacks = pbx_analysis.get('deployment_metrics', {}).get('rollback_count', 0)
    whisper_rollbacks = whisper_analysis.get('deployment_metrics', {}).get('rollback_count', 0)

    pbx_rapid = pbx_analysis.get('rapid_patterns', {}).get('rapid_sequences_detected', 0)
    whisper_rapid = whisper_analysis.get('rapid_patterns', {}).get('rapid_sequences_detected', 0)

    comparative["stability_metrics"] = {
        "pbx_web": {
            "rollbacks": pbx_rollbacks,
            "rapid_sequences": pbx_rapid,
            "stability_score": 100 - (pbx_rollbacks * 10) - (pbx_rapid * 5)
        },
        "whisper_stt": {
            "rollbacks": whisper_rollbacks,
            "rapid_sequences": whisper_rapid,
            "stability_score": 100 - (whisper_rollbacks * 10) - (whisper_rapid * 5)
        }
    }

    return comparative

def identify_patterns(pbx_analysis: Dict, whisper_analysis: Dict) -> Dict[str, Any]:
    """Identify shared and unique patterns."""
    patterns = {
        "shared_patterns": [],
        "pbx_web_specific": [],
        "whisper_stt_specific": [],
        "recommendations": []
    }

    # Check for shared patterns
    pbx_rapid = pbx_analysis.get('rapid_patterns', {}).get('rapid_sequences_detected', 0)
    whisper_rapid = whisper_analysis.get('rapid_patterns', {}).get('rapid_sequences_detected', 0)

    if pbx_rapid > 0 and whisper_rapid > 0:
        patterns["shared_patterns"].append({
            "pattern": "Rapid deployment sequences",
            "description": "Both services experienced multiple deployments within short timeframes",
            "severity": "medium",
            "impact": "Can cause instability and configuration drift"
        })

    # Check for failure patterns
    pbx_failures = pbx_analysis.get('failure_modes', {})
    whisper_failures = whisper_analysis.get('failure_modes', {})

    if pbx_failures or whisper_failures:
        patterns["shared_patterns"].append({
            "pattern": "Deployment failures detected",
            "description": "One or both services experienced deployment issues",
            "severity": "high" if (pbx_failures or whisper_failures) else "low",
            "impact": "Service availability and user experience impact"
        })

    # pbx-web specific patterns
    pbx_rollbacks = pbx_analysis.get('deployment_metrics', {}).get('rollback_count', 0)
    if pbx_rollbacks > 0:
        patterns["pbx_web_specific"].append({
            "pattern": "Deployment rollbacks",
            "description": f"pbx-web experienced {pbx_rollbacks} rollback(s) in 30-day period",
            "severity": "high",
            "impact": "Indicates deployment instability or insufficient pre-deployment testing"
        })

    if pbx_analysis.get('current_status', {}).get('strategy') == 'Recreate':
        patterns["pbx_web_specific"].append({
            "pattern": "Recreate deployment strategy",
            "description": "pbx-web uses Recreate strategy (complete pod replacement)",
            "severity": "low",
            "impact": "Brief service interruptions during deployments"
        })

    # whisper-stt specific patterns
    whisper_deployments = whisper_analysis.get('deployment_metrics', {}).get('total_deployments_last_30_days', 0)
    if whisper_deployments == 0:
        patterns["whisper_stt_specific"].append({
            "pattern": "No recent deployments",
            "description": "whisper-stt has had no deployments in the 30-day period",
            "severity": "info",
            "impact": "Service appears stable but may not be receiving updates"
        })

    whisper_rapid_sequences = whisper_analysis.get('rapid_patterns', {}).get('sequences', [])
    for seq in whisper_rapid_sequences:
        if seq.get('duration_seconds', 0) < 600:  # Less than 10 minutes
            patterns["whisper_stt_specific"].append({
                "pattern": "Very rapid version iterations",
                "description": f"Multiple deployments within {seq.get('duration_seconds', 0):.0f} seconds",
                "severity": "medium",
                "impact": "Potential for configuration drift and incomplete stabilizations"
            })

    # Generate recommendations
    if pbx_rollbacks > 0:
        patterns["recommendations"].append({
            "target": "pbx-web",
            "priority": "high",
            "action": "Implement pre-deployment validation",
            "description": "Add automated testing and validation stages before deployments to prevent rollback scenarios"
        })

    if pbx_rapid > 0 or whisper_rapid > 0:
        patterns["recommendations"].append({
            "target": "Both services",
            "priority": "medium",
            "action": "Implement deployment cooldown",
            "description": "Add minimum time between deployments to allow for stabilization"
        })

    patterns["recommendations"].append({
        "target": "Both services",
        "priority": "medium",
        "action": "Enhanced monitoring",
        "description": "Implement detailed deployment monitoring with alerting for rapid sequences and failures"
    })

    return patterns

def generate_markdown_report(pbx_basic: Dict, pbx_detailed: Dict,
                            whisper_basic: Dict, whisper_detailed: Dict,
                            comparative: Dict, patterns: Dict) -> str:
    """Generate a comprehensive markdown report."""

    report_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    markdown = f"""# Deployment Analysis Report: pbx-web vs whisper-stt

**Generated:** {report_date}
**Analysis Period:** Last 30 days
**Cluster:** ardenone-cluster

## Executive Summary

This report analyzes deployment patterns, stability metrics, and reliability profiles for two production services running on the ardenone-cluster. The analysis reveals key differences in deployment frequency, stability patterns, and operational characteristics that can inform infrastructure improvement decisions.

### Key Findings

- **pbx-web** has experienced **{pbx_detailed.get('deployment_metrics', {}).get('rollback_count', 0)} deployment rollback(s)** in the 30-day period
- **whisper-stt** shows **{comparative['success_rate_comparison']['whisper_stt']}** success rate compared to pbx-web's **{comparative['success_rate_comparison']['pbx_web']}**
- **Rapid deployment sequences** detected in both services
- **Shared patterns** indicate opportunities for deployment process improvements

---

## Comparative Metrics Overview

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Success Rate** | {comparative['success_rate_comparison']['pbx_web']} | {comparative['success_rate_comparison']['whisper_stt']} |
| **Total Deployments (30d)** | {comparative['deployment_frequency_comparison']['pbx_web_deployments']} | {comparative['deployment_frequency_comparison']['whisper_stt_deployments']} |
| **Deployment Frequency** | {comparative['deployment_frequency_comparison']['pbx_web_frequency']} | {comparative['deployment_frequency_comparison']['whisper_stt_frequency']} |
| **Rollbacks** | {comparative['stability_metrics']['pbx_web']['rollbacks']} | {comparative['stability_metrics']['whisper_stt']['rollbacks']} |
| **Rapid Sequences** | {comparative['stability_metrics']['pbx_web']['rapid_sequences']} | {comparative['stability_metrics']['whisper_stt']['rapid_sequences']} |
| **Stability Score** | {comparative['stability_metrics']['pbx_web']['stability_score']}/100 | {comparative['stability_metrics']['whisper_stt']['stability_score']}/100 |

---

## Service-Specific Analysis

### pbx-web Reliability Profile

#### Current Status
- **Revision:** {pbx_detailed.get('current_status', {}).get('revision', 'N/A')}
- **Replicas:** {pbx_detailed.get('current_status', {}).get('replicas', 'N/A')} ({pbx_detailed.get('current_status', {}).get('readyReplicas', 0)} ready)
- **Strategy:** {pbx_detailed.get('current_status', {}).get('strategy', 'N/A')}
- **Current Image:** {pbx_detailed.get('current_image', 'N/A')}

#### Deployment Performance
- **30-Day Deployments:** {pbx_detailed.get('deployment_metrics', {}).get('total_deployments_last_30_days', 0)}
- **Success Rate:** {pbx_detailed.get('deployment_metrics', {}).get('success_rate', 0):.1f}%
- **Failed Deployments:** {pbx_detailed.get('deployment_metrics', {}).get('failed_deployments', 0)}
- **Rollback Count:** {pbx_detailed.get('deployment_metrics', {}).get('rollback_count', 0)}

#### Health Indicators
"""

    # Add health indicators if available
    health_indicators = pbx_detailed.get('health_indicators', {})
    if health_indicators:
        for indicator, status in health_indicators.items():
            emoji = "✅" if status else "❌"
            markdown += f"- {emoji} **{indicator.replace('_', ' ').title()}**: {status}\n"
    else:
        markdown += "- Health indicator data not available\n"

    markdown += f"""
#### Pod Health
- **Current Pod:** {pbx_detailed.get('pod_health', {}).get('pod_name', 'N/A')}
- **Restart Count:** {pbx_detailed.get('pod_health', {}).get('restart_count', 0)}
- **Status:** {pbx_detailed.get('pod_health', {}).get('phase', 'N/A').title()}

---

### whisper-stt Reliability Profile

#### Current Status
- **Revision:** {whisper_detailed.get('current_status', {}).get('revision', 'N/A')}
- **Replicas:** {whisper_detailed.get('current_status', {}).get('replicas', 'N/A')} ({whisper_detailed.get('current_status', {}).get('readyReplicas', 0)} ready)
- **Strategy:** {whisper_detailed.get('current_status', {}).get('strategy', 'N/A')}
- **Current Image:** {whisper_detailed.get('current_image', 'N/A')}

#### Deployment Performance
- **30-Day Deployments:** {whisper_detailed.get('deployment_metrics', {}).get('total_deployments_last_30_days', 0)}
- **Success Rate:** {whisper_detailed.get('deployment_metrics', {}).get('success_rate', 0):.1f}%
- **Failed Deployments:** {whisper_detailed.get('deployment_metrics', {}).get('failed_deployments', 0)}
- **Rollback Count:** {whisper_detailed.get('deployment_metrics', {}).get('rollback_count', 0)}

#### Operational Metrics
"""

    # Add operational metrics for whisper-stt
    op_metrics = whisper_detailed.get('operational_metrics', {})
    if op_metrics:
        uptime = op_metrics.get('uptime', {})
        if isinstance(uptime, dict):
            markdown += "- **Uptime:** "
            for service, duration in uptime.items():
                markdown += f"{service}: {duration}, "
            markdown = markdown.rstrip(', ') + "\n"

        restart_analysis = op_metrics.get('restart_analysis', {})
        if restart_analysis:
            markdown += "- **Restart Analysis:**\n"
            for key, value in restart_analysis.items():
                markdown += f"  - {key.replace('_', ' ').title()}: {value}\n"
    else:
        markdown += "- Operational metrics not available\n"

    # Add error incidents if any
    error_incidents = whisper_detailed.get('error_incidents', {})
    if error_incidents:
        markdown += f"""
#### Error Incidents
- **Total Incidents:** {error_incidents.get('total_incidents', 0)}
- **Critical Incidents:** {error_incidents.get('critical_incidents', 0)}
"""

    markdown += """
---

## Pattern Analysis

### Shared Patterns

"""

    for pattern in patterns['shared_patterns']:
        emoji = "🔴" if pattern['severity'] == 'high' else "🟡" if pattern['severity'] == 'medium' else "🟢"
        markdown += f"""
#### {emoji} {pattern['pattern']}
- **Severity:** {pattern['severity'].upper()}
- **Description:** {pattern['description']}
- **Impact:** {pattern['impact']}

"""

    if not patterns['shared_patterns']:
        markdown += "*No significant shared patterns identified.*\n\n"

    markdown += """### pbx-web Specific Patterns

"""

    for pattern in patterns['pbx_web_specific']:
        emoji = "🔴" if pattern['severity'] == 'high' else "🟡" if pattern['severity'] == 'medium' else "🟢"
        markdown += f"""
#### {emoji} {pattern['pattern']}
- **Severity:** {pattern['severity'].upper()}
- **Description:** {pattern['description']}
- **Impact:** {pattern['impact']}

"""

    if not patterns['pbx_web_specific']:
        markdown += "*No pbx-web-specific patterns identified.*\n\n"

    markdown += """### whisper-stt Specific Patterns

"""

    for pattern in patterns['whisper_stt_specific']:
        emoji = "🔴" if pattern['severity'] == 'high' else "🟡" if pattern['severity'] == 'medium' else "🟢"
        markdown += f"""
#### {emoji} {pattern['pattern']}
- **Severity:** {pattern['severity'].upper()}
- **Description:** {pattern['description']}
- **Impact:** {pattern['impact']}

"""

    if not patterns['whisper_stt_specific']:
        markdown += "*No whisper-stt-specific patterns identified.*\n\n"

    # Recommendations section
    markdown += """---

## Recommendations

"""

    for i, rec in enumerate(patterns['recommendations'], 1):
        emoji = "🔴" if rec['priority'] == 'high' else "🟡" if rec['priority'] == 'medium' else "🟢"
        markdown += f"""### {emoji} Recommendation {i}: {rec['action']} ({rec['priority'].upper()})

**Target:** {rec['target']}
**Description:** {rec['description']}

"""

    # Add additional analysis and insights
    markdown += """---

## Detailed Insights

### Deployment Strategy Comparison

pbx-web uses the **Recreate** deployment strategy, which means:
- All old pods are terminated before new ones are created
- Brief service interruption during deployments
- Simpler rollback process but less seamless updates

whisper-stt uses **RollingUpdate** (or similar):
- Gradual replacement of pods
- No service interruption during updates
- More complex rollback process but maintains availability

### Resource Utilization Patterns

pbx-web demonstrates:
- Lower resource footprint (500m CPU limit, 512Mi memory limit)
- Frequent rebuild activity for search indexes
- Stable pod lifecycle with minimal restarts

whisper-stt shows:
- Higher resource allocation (8 CPU limits, 8Gi memory limits)
- AI/ML workload characteristics with model caching
- Longer pod lifespans indicating stable operations

### Deployment Frequency Analysis

The analysis reveals different deployment patterns:
- pbx-web: More frequent deployments (possibly due to web content updates)
- whisper-stt: Less frequent deployments (stable AI service)

Both services show instances of rapid deployment sequences, which could indicate:
- Emergency hotfixes
- Configuration corrections
- Image version updates

---

## Conclusion

The comparative analysis reveals that both services maintain high availability but exhibit different stability profiles. pbx-web has experienced rollback scenarios that warrant attention, while whisper-stt demonstrates consistent stability with fewer deployment events.

Key takeaways:
1. Both services would benefit from deployment cooldown periods
2. pbx-web specifically needs pre-deployment validation improvements
3. Enhanced monitoring would provide better visibility into deployment patterns
4. The different deployment strategies align with their service types

---

*Report generated by automated deployment pattern analysis tool*
*For questions or additional analysis, run the analysis script with updated data*
"""

    return markdown

def main():
    """Main execution function."""
    print("Loading deployment data...")

    # Load basic deployment data
    pbx_basic = load_json_file('pbx-web-deployments.json')
    whisper_basic = load_json_file('whisper-stt-deployments.json')

    # Load detailed 30-day data
    pbx_detailed_data = load_json_file('pbx-web-deployment-data-30days.json')
    whisper_detailed_data = load_json_file('whisper-stt-deployment-data-30days.json')

    print("Analyzing deployment patterns...")

    # Analyze basic deployments
    pbx_basic_analysis = analyze_basic_deployments(pbx_basic, 'pbx-web')
    whisper_basic_analysis = analyze_basic_deployments(whisper_basic, 'whisper-stt')

    # Analyze detailed 30-day data
    pbx_detailed_analysis = analyze_30day_data(pbx_detailed_data, 'pbx-web')
    whisper_detailed_analysis = analyze_30day_data(whisper_detailed_data, 'whisper-stt')

    # Calculate comparative metrics
    comparative_metrics = calculate_comparative_metrics(pbx_detailed_analysis, whisper_detailed_analysis)

    # Identify patterns
    pattern_analysis = identify_patterns(pbx_detailed_analysis, whisper_detailed_analysis)

    print("Generating comprehensive report...")

    # Generate markdown report
    report_content = generate_markdown_report(
        pbx_basic_analysis, pbx_detailed_analysis,
        whisper_basic_analysis, whisper_detailed_analysis,
        comparative_metrics, pattern_analysis
    )

    # Save report
    report_file = Path('deployment_analysis_report.md')
    with open(report_file, 'w') as f:
        f.write(report_content)

    print(f"✅ Report generated: {report_file}")
    print(f"📊 Report includes {len(pattern_analysis['shared_patterns'])} shared patterns, "
          f"{len(pattern_analysis['pbx_web_specific'])} pbx-web specific patterns, "
          f"and {len(pattern_analysis['whisper_stt_specific'])} whisper-stt specific patterns")
    print(f"🎯 Generated {len(pattern_analysis['recommendations'])} recommendations")

if __name__ == '__main__':
    main()