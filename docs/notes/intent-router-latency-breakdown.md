# Intent Router Latency Breakdown

**Total samples:** 10

## Summary by Phase

### ZAI Proxy Call (model inference)

- **p50:** 2591.25 ms
- **p95:** 3569.20 ms
- **p99:** 3569.20 ms
- **Min:** 1643.08 ms
- **Max:** 3569.20 ms
- **Mean:** 2604.72 ms

### JSON Parsing

- **p50:** 0.03 ms
- **p95:** 0.05 ms
- **p99:** 0.05 ms
- **Min:** 0.01 ms
- **Max:** 0.05 ms
- **Mean:** 0.03 ms

### Total Router Time (estimate)

- **p50:** 2591.29 ms
- **p95:** 3569.24 ms
- **p99:** 3569.24 ms
- **Min:** 1643.11 ms
- **Max:** 3569.24 ms
- **Mean:** 2604.75 ms

## Latency Distribution Analysis

- **ZAI Proxy Call:** 100.0% of total latency
- **JSON Parsing:** 0.0% of total latency

**Key Finding:** Time is primarily spent in the ZAI proxy call (model inference).
JSON parsing is typically < 1ms and is negligible compared to inference.

## Sample Data

Sample 1: proxy=2420.90ms, parse=0.02ms, total=2420.92ms
Sample 2: proxy=3033.74ms, parse=0.05ms, total=3033.79ms
Sample 3: proxy=3569.20ms, parse=0.04ms, total=3569.24ms
Sample 4: proxy=1690.97ms, parse=0.03ms, total=1691.00ms
Sample 5: proxy=2647.03ms, parse=0.01ms, total=2647.04ms
Sample 6: proxy=2591.25ms, parse=0.04ms, total=2591.29ms
Sample 7: proxy=1643.08ms, parse=0.03ms, total=1643.11ms
Sample 8: proxy=2490.99ms, parse=0.03ms, total=2491.02ms
Sample 9: proxy=2546.49ms, parse=0.02ms, total=2546.51ms
Sample 10: proxy=3413.57ms, parse=0.01ms, total=3413.58ms