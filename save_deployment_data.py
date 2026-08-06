#!/usr/bin/env python3
"""
Reformat pbx-web deployment data to match the expected schema.
"""
import json
from datetime import datetime

# Read the original data
with open('pbx-web-deployment-data-30days.json', 'r') as f:
    original_data = json.load(f)

# Extract deployments from both sections
deployments = []

# Add last 30 days deployments
for event in original_data.get('deployment_events_last_30_days', []):
    deployments.append(event)

# Add historical deployments (beyond 30 days)
for event in original_data.get('historical_deployments_beyond_30_days', []):
    deployments.append(event)

# Sort by timestamp
deployments.sort(key=lambda x: x.get('timestamp', ''))

# Create the new structure with required metadata
output_data = {
    "metadata": {
        "generated_at": original_data['metadata']['data_collected_at'],
        "date_range_start": original_data['metadata']['time_period']['start'],
        "date_range_end": original_data['metadata']['time_period']['end'],
        "service": original_data['metadata']['service'],
        "namespace": original_data['metadata']['namespace'],
        "cluster": original_data['metadata']['cluster'],
        "managed_by": original_data['metadata']['managed_by'],
        "strategy": original_data['metadata']['strategy']
    },
    "deployments": deployments
}

# Write to the target location
output_path = 'docs/research/deployment-data/pbx-web-deployments.json'
with open(output_path, 'w') as f:
    json.dump(output_data, f, indent=2)

print(f"✓ Saved deployment data to {output_path}")
print(f"  Total deployments: {len(deployments)}")
print(f"  Date range: {output_data['metadata']['date_range_start']} to {output_data['metadata']['date_range_end']}")

# Verify the file is valid JSON
print("\nVerifying JSON validity...")
with open(output_path, 'r') as f:
    verification_data = json.load(f)
print("✓ JSON is valid")
print(f"✓ Contains {len(verification_data['deployments'])} deployment records")
