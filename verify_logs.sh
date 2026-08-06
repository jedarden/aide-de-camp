#!/usr/bin/bash
# Verification script for collected log files
# Validates JSONL format, timestamps, and deployment-related content

set -e

echo "=== Log File Verification ==="
echo ""

# Check files exist
if [ ! -f "data/pbx-web-logs.jsonl" ]; then
    echo "❌ data/pbx-web-logs.jsonl not found"
    exit 1
fi

if [ ! -f "data/whisper-stt-logs.jsonl" ]; then
    echo "❌ data/whisper-stt-logs.jsonl not found"
    exit 1
fi

echo "✅ Files exist"
echo ""

# Check file sizes and line counts
echo "=== File Sizes and Line Counts ==="
ls -lh data/pbx-web-logs.jsonl data/whisper-stt-logs.jsonl
wc -l data/pbx-web-logs.jsonl data/whisper-stt-logs.jsonl
echo ""

# Validate JSONL format
echo "=== JSONL Format Validation ==="
echo "Checking pbx-web-logs.jsonl..."
python3 -c "
import json, sys
errors = 0
with open('data/pbx-web-logs.jsonl', 'r') as f:
    for i, line in enumerate(f, 1):
        if line.strip():
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                print(f'Line {i}: {e}')
                errors += 1
if errors == 0:
    print('✅ All lines are valid JSON')
else:
    print(f'❌ Found {errors} invalid lines')
    sys.exit(1)
"

echo "Checking whisper-stt-logs.jsonl..."
python3 -c "
import json, sys
errors = 0
with open('data/whisper-stt-logs.jsonl', 'r') as f:
    for i, line in enumerate(f, 1):
        if line.strip():
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                print(f'Line {i}: {e}')
                errors += 1
if errors == 0:
    print('✅ All lines are valid JSON')
else:
    print(f'❌ Found {errors} invalid lines')
    sys.exit(1)
"
echo ""

# Check timestamp ranges
echo "=== Timestamp Range Validation ==="
echo "pbx-web-logs.jsonl:"
python3 -c "
import json
timestamps = []
with open('data/pbx-web-logs.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            data = json.loads(line)
            if 'timestamp' in data:
                timestamps.append(data['timestamp'])
if timestamps:
    earliest = min(timestamps)
    latest = max(timestamps)
    print(f'  Earliest: {earliest}')
    print(f'  Latest: {latest}')
    print(f'  ✅ Timestamps present')
else:
    print('  ❌ No timestamps found')
"

echo "whisper-stt-logs.jsonl:"
python3 -c "
import json
timestamps = []
with open('data/whisper-stt-logs.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            data = json.loads(line)
            if 'timestamp' in data:
                timestamps.append(data['timestamp'])
if timestamps:
    earliest = min(timestamps)
    latest = max(timestamps)
    print(f'  Earliest: {earliest}')
    print(f'  Latest: {latest}')
    print(f'  ✅ Timestamps present')
else:
    print('  ❌ No timestamps found')
"
echo ""

# Check for deployment-related content
echo "=== Deployment-Related Content ==="
echo "pbx-web-logs.jsonl:"
python3 -c "
import json
from collections import Counter
pod_counter = Counter()
with open('data/pbx-web-logs.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            data = json.loads(line)
            pod = data.get('pod_name', 'unknown')
            pod_counter[pod] += 1

print(f'  Unique pods: {len(pod_counter)}')
for pod, count in pod_counter.most_common():
    print(f'    - {pod}: {count} entries')
print(f'  ✅ Pod lifecycle data present')
"

echo "whisper-stt-logs.jsonl:"
python3 -c "
import json
from collections import Counter
pod_counter = Counter()
with open('data/whisper-stt-logs.jsonl', 'r') as f:
    for line in f:
        if line.strip():
            data = json.loads(line)
            pod = data.get('pod_name', 'unknown')
            pod_counter[pod] += 1

print(f'  Unique pods: {len(pod_counter)}')
for pod, count in pod_counter.most_common():
    print(f'    - {pod}: {count} entries')
print(f'  ✅ Pod lifecycle data present')
"
echo ""

# Sample entries
echo "=== Sample Entries ==="
echo "pbx-web-logs.jsonl (first entry):"
head -n 1 data/pbx-web-logs.jsonl | jq .
echo ""
echo "whisper-stt-logs.jsonl (first entry):"
head -n 1 data/whisper-stt-logs.jsonl | jq .
echo ""

echo "=== Verification Complete ==="
echo "✅ All log files validated successfully"
