export const meta = {
  name: 'deployment-failure-analysis',
  description: 'Compare deployment patterns and failure modes between pbx-web and whisper-stt',
  phases: [
    { title: 'Explore Clusters', detail: 'Locate pbx-web and whisper-stt across clusters' },
    { title: 'Gather Data', detail: 'Collect deployment history and logs for both services' },
    { title: 'Analyze Patterns', detail: 'Identify failure modes and deployment correlations' },
    { title: 'Generate Report', detail: 'Create comprehensive comparative analysis' }
  ]
}

const CLUSTERS = [
  { name: 'ardenone-cluster', kubectl: 'kubectl --server=http://traefik-ardenone-cluster:8001' },
  { name: 'apexalgo-iad', kubectl: 'kubectl --server=http://traefik-apexalgo-iad:8001' },
  { name: 'rs-manager', kubectl: 'kubectl --server=http://traefik-rs-manager:8001' },
  { name: 'ord-devimprint', kubectl: 'kubectl --server=http://kubectl-proxy-ord-devimprint:8001' },
  { name: 'iad-options', kubectl: 'kubectl --server=http://traefik-iad-options:8001' }
]

const THIRTY_DAYS_AGO = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()

phase('Explore Clusters')

log('Scanning all clusters for pbx-web and whisper-stt deployments...')

const clusterScan = await parallel(CLUSTERS.map(cluster => () => agent(
  `Check cluster ${cluster.name} for pbx-web and whisper-stt deployments. Use:\n${cluster.kubectl} get deployments -A\n${cluster.kubectl} get statefulsets -A\n${cluster.kubectl} get pods -A\n\nReturn ONLY a JSON object with this exact structure:\n{\n  "cluster": "${cluster.name}",\n  "services": {\n    "pbx-web": { "found": true/false, "namespace": "...", "type": "Deployment/StatefulSet", "name": "..." },\n    "whisper-stt": { "found": true/false, "namespace": "...", "type": "Deployment/StatefulSet", "name": "..." }\n  }\n}\n\nIf a service is not found, set found: false and omit namespace/type/name.\n\nIMPORTANT: Return ONLY the JSON. No markdown, no explanations.`,
  { label: `scan:${cluster.name}`, schema: { type: 'object', properties: { cluster: { type: 'string' }, services: { type: 'object' } }, required: ['cluster', 'services'] } }
)))

const foundServices = {}
clusterScan.filter(Boolean).forEach(result => {
  if (result.services['pbx-web'] && result.services['pbx-web'].found) {
    foundServices['pbx-web'] = { ...result.services['pbx-web'], cluster: result.cluster }
  }
  if (result.services['whisper-stt'] && result.services['whisper-stt'].found) {
    foundServices['whisper-stt'] = { ...result.services['whisper-stt'], cluster: result.cluster }
  }
})

log(`Found services: ${Object.keys(foundServices).join(', ')}`)

if (Object.keys(foundServices).length === 0) {
  log('ERROR: Neither pbx-web nor whisper-stt found on any cluster')
  return { error: 'Services not found', foundServices: {} }
}

phase('Gather Data')

log(`Gathering deployment history and logs from ${THIRTY_DAYS_AGO} to present...`)

const deploymentData = await parallel(Object.entries(foundServices).map(([serviceName, info]) => () => agent(
  `Gather deployment history and failure data for ${serviceName} from cluster ${info.cluster} in namespace ${info.namespace}.\n\nThe resource is ${info.type}/${info.name}.\n\nUse these commands:\nkubectl --server=http://traefik-${info.cluster}:8001 get ${info.type} ${info.name} -n ${info.namespace} -o yaml\n\nFor rollout history (last 30 days):\nkubectl --server=http://traefik-${info.cluster}:8001 get ${info.type} ${info.name} -n ${info.namespace} -o jsonpath='{.status}' | jq .\n\nFor pods with restarts and crash status:\nkubectl --server=http://traefik-${info.cluster}:8001 get pods -n ${info.namespace} -l app=${info.name} --sort-by=.metadata.creationTimestamp\n\nFor recent pod events:\nkubectl --server=http://traefik-${info.cluster}:8001 get events -n ${info.namespace} --field-selector involvedObject.name=${info.name} --sort-by=.lastTimestamp\n\nReturn a JSON object with:\n{\n  "service": "${serviceName}",\n  "cluster": "${info.cluster}",\n  "namespace": "${info.namespace}",\n  "deployment_history": {\n    "replicas": "...",\n    "updated_replicas": "...",\n    "available_replicas": "...",\n    "unavailable_replicas": "...",\n    "observed_generation": "..."\n  },\n  "pods": [\n    {\n      "name": "...",\n      "ready": "...",\n      "restarts": 0,\n      "status": "Running/Pending/Failed",\n      "node": "...",\n      "age": "..."\n    }\n  ],\n  "rollout_status": {\n    "updated": 0,\n    "ready": 0,\n    "available": 0\n  }\n}\n\nIMPORTANT: Return ONLY the JSON. No markdown, no explanations.`,
  { label: `gather:${serviceName}`, phase: 'Gather Data', schema: { type: 'object', properties: { service: { type: 'string' }, cluster: { type: 'string' }, namespace: { type: 'string' }, deployment_history: { type: 'object' }, pods: { type: 'array' }, rollout_status: { type: 'object' } }, required: ['service', 'cluster', 'namespace'] } }
)))

const logData = await parallel(Object.entries(foundServices).map(([serviceName, info]) => () => agent(
  `Check logs and error patterns for ${serviceName} from cluster ${info.cluster} in namespace ${info.namespace}.\n\nFor recent pods:\nkubectl --server=http://traefik-${info.cluster}:8001 get pods -n ${info.namespace} -l app=${info.name} -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\\\\n' | head -3\n\nFor each pod, check logs for errors:\nkubectl --server=http://traefik-${info.cluster}:8001 logs -n ${info.namespace} <pod-name> --tail=100 --since=720h\n\nLook for:\n- HTTP 500 errors\n- Connection timeouts\n- OOM killed messages\n- Panic/stack traces\n- Exit codes\n\nReturn a JSON object with:\n{\n  "service": "${serviceName}",\n  "cluster": "${info.cluster}",\n  "namespace": "${info.namespace}",\n  "error_patterns": {\n    "http_500": 0,\n    "timeouts": 0,\n    "oom_killed": 0,\n    "panics": 0\n  },\n  "recent_errors": [\n    {\n      "timestamp": "...",\n      "type": "http_500/timeout/oom/panic/other",\n      "message": "...",\n      "pod": "..."\n    }\n  ],\n  "log_sample": "first 500 chars of most recent relevant log"\n}\n\nIMPORTANT: Return ONLY the JSON. No markdown, no explanations.`,
  { label: `logs:${serviceName}`, phase: 'Gather Data', schema: { type: 'object', properties: { service: { type: 'string' }, cluster: { type: 'string' }, namespace: { type: 'string' }, error_patterns: { type: 'object' }, recent_errors: { type: 'array' }, log_sample: { type: 'string' } }, required: ['service', 'cluster', 'namespace'] } }
)))

phase('Analyze Patterns')

log('Analyzing deployment patterns, failure modes, and correlations...')

const deploymentDataFiltered = deploymentData.filter(Boolean)
const logDataFiltered = logData.filter(Boolean)

const analysis = await agent(
  `Analyze the collected data for deployment patterns and failure modes.\n\nDeployment Data:\n${JSON.stringify(deploymentDataFiltered, null, 2)}\n\nLog Data:\n${JSON.stringify(logDataFiltered, null, 2)}\n\nFound Services:\n${JSON.stringify(foundServices, null, 2)}\n\nProvide a comprehensive analysis including:\n1. Deployment stability comparison\n2. Common failure patterns across both services\n3. Service-specific anomalies\n4. Correlation between deployments and errors\n5. Resource saturation indicators\n\nReturn a JSON object with this structure:\n{\n  "summary": {\n    "services_analyzed": ["pbx-web", "whisper-stt"],\n    "timeframe_days": 30,\n    "total_deployments": 0,\n    "total_incidents": 0\n  },\n  "deployment_stability": {\n    "pbx-web": {\n      "availability_score": 0.0,\n      "restart_frequency": "high/medium/low",\n      "rollout_issues": []\n    },\n    "whisper-stt": {\n      "availability_score": 0.0,\n      "restart_frequency": "high/medium/low",\n      "rollout_issues": []\n    }\n  },\n  "failure_patterns": {\n    "shared": [],\n    "pbx-web_specific": [],\n    "whisper-stt_specific": []\n  },\n  "deployment_error_correlation": {\n    "deployments_followed_by_errors": 0,\n    "time_to_error_after_deployment": "immediate/within_hours/next_day"\n  },\n  "resource_indicators": {\n    "memory_pressure": "high/medium/low",\n    "cpu_saturation": "high/medium/low"\n  },\n  "key_findings": [\n    "finding 1",\n    "finding 2"\n  ],\n  "recommendations": [\n    "recommendation 1",\n    "recommendation 2"\n  ]\n}\n\nIMPORTANT: Return ONLY the JSON. No markdown, no explanations.`,
  { label: 'analyze-patterns', phase: 'Analyze Patterns', schema: { type: 'object', properties: { summary: { type: 'object' }, deployment_stability: { type: 'object' }, failure_patterns: { type: 'object' }, deployment_error_correlation: { type: 'object' }, resource_indicators: { type: 'object' }, key_findings: { type: 'array' }, recommendations: { type: 'array' } }, required: ['summary', 'deployment_stability', 'failure_patterns', 'key_findings', 'recommendations'] } }
)

phase('Generate Report')

const analysisResult = analysis

const report = `# Deployment & Failure Analysis: pbx-web vs whisper-stt

**Analysis Period:** Last 30 days (${THIRTY_DAYS_AGO} to ${new Date().toISOString()})
**Generated:** ${new Date().toISOString()}

---

## Executive Summary

- **Services Analyzed:** ${analysisResult.summary.services_analyzed.join(', ')}
- **Total Deployments:** ${analysisResult.summary.total_deployments}
- **Total Incidents:** ${analysisResult.summary.total_incidents}

---

## Deployment Stability

### pbx-web
- **Availability Score:** ${analysisResult.deployment_stability['pbx-web'].availability_score}
- **Restart Frequency:** ${analysisResult.deployment_stability['pbx-web'].restart_frequency}
- **Rollout Issues:** ${analysisResult.deployment_stability['pbx-web'].rollout_issues.length > 0 ? analysisResult.deployment_stability['pbx-web'].rollout_issues.join(', ') : 'None detected'}

### whisper-stt
- **Availability Score:** ${analysisResult.deployment_stability['whisper-stt'].availability_score}
- **Restart Frequency:** ${analysisResult.deployment_stability['whisper-stt'].restart_frequency}
- **Rollout Issues:** ${analysisResult.deployment_stability['whisper-stt'].rollout_issues.length > 0 ? analysisResult.deployment_stability['whisper-stt'].rollout_issues.join(', ') : 'None detected'}

---

## Failure Patterns

### Shared Across Both Services
${analysisResult.failure_patterns.shared.map(f => `- ${f}`).join('\n') || '- None detected'}

### pbx-web Specific
${analysisResult.failure_patterns['pbx-web_specific'].map(f => `- ${f}`).join('\n') || '- None detected'}

### whisper-stt Specific
${analysisResult.failure_patterns['whisper-stt_specific'].map(f => `- ${f}`).join('\n') || '- None detected'}

---

## Deployment ↔ Error Correlation

- **Deployments Followed by Errors:** ${analysisResult.deployment_error_correlation.deployments_followed_by_errors}
- **Time to Error After Deployment:** ${analysisResult.deployment_error_correlation.time_to_error_after_deployment}

---

## Resource Indicators

- **Memory Pressure:** ${analysisResult.resource_indicators.memory_pressure}
- **CPU Saturation:** ${analysisResult.resource_indicators.cpu_saturation}

---

## Key Findings

${analysisResult.key_findings.map(f => `### ${f}\n`).join('\n')}

---

## Recommendations

${analysisResult.recommendations.map(r => `1. ${r}`).join('\n')}

---

## Raw Data Appendix

### Deployment Data
\`\`\`json
${JSON.stringify(deploymentDataFiltered, null, 2)}
\`\`\`

### Error Log Data
\`\`\`json
${JSON.stringify(logDataFiltered, null, 2)}
\`\`\`

---

*Report generated by aide-de-camp deployment analysis workflow*
`

return {
  report,
  analysis: analysisResult,
  raw: { deploymentData: deploymentDataFiltered, logData: logDataFiltered, foundServices }
}
