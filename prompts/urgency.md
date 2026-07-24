# Urgency Classification

Assign urgency tiers based on time sensitivity, impact severity, and user attention state.

## Tiers

- **critical**: Production incident, security event, data loss, manual intervention required, pipeline blocked >30min
- **high**: Active work user initiated, deployment monitoring, health degradation
- **normal**: Routine status check, historical lookup, general state query
- **low**: Nice-to-have info, long-term research, passive monitoring, documentation

## Contextual Adjustment

- User asks every 2 minutes → high urgency (actively waiting)
- User hasn't asked in days → low urgency (background)
- Ambiguous without context → default to normal

## Output

```json
{
  "urgency": "critical|high|normal|low",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}
```
