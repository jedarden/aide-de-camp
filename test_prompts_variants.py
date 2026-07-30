#!/usr/bin/env python3
"""Test different prompt optimization levels."""

import re

def count_tokens(text):
    """Count tokens using rough estimate: ~1 token per 4 characters."""
    text = re.sub(r'\s+', ' ', text).strip()
    return len(text) // 4

# Current prompt
current = """# Intent Router

Classify the utterance into intents. Return ONLY a JSON array.

## Intent Types
- status: Query state (pods, pipelines, beads)
- action: Execute commands (deploy, restart, create)
- brainstorm: Explore options/design/architecture
- lookup: Find info (requires lookup_kind: logs|config|docs)
- reminder: Time-based tasks
- task-profile: Multi-step work (implement/fix/investigate)

## Schema per intent
{
  "intent_type": "<type>",
  "project_slug": "<project-id or null>",
  "utterance_fragment": "<text fragment>",
  "lookup_kind": "<logs|config|docs for lookup intents>"
}

## Rules
- Different type/project/target → separate intents
- Map projects by name/alias/context"""

# Balanced optimization (30-35% target)
balanced = """# Intent Router
Classify utterances. Return JSON array.

Types:
- status: Query state
- action: Execute commands
- brainstorm: Explore options
- lookup: Find info (lookup_kind: logs|config|docs)
- reminder: Time-based tasks
- task-profile: Multi-step work

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Different type/project/target → separate intents. Map projects by name."""

# Moderate optimization (35-40% target)
moderate = """# Intent Router
Classify utterances. Return JSON array.

Types:
- status: Query state
- action: Execute commands
- brainstorm: Explore options
- lookup: Find info (kind: logs|config|docs)
- reminder: Time tasks
- task-profile: Multi-step

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project/target. Map projects by name."""

current_tokens = count_tokens(current)
balanced_tokens = count_tokens(balanced)
moderate_tokens = count_tokens(moderate)

print(f"Current:   {current_tokens} tokens")
print(f"Balanced:  {balanced_tokens} tokens ({100*(1-balanced_tokens/current_tokens):.1f}% reduction)")
print(f"Moderate:  {moderate_tokens} tokens ({100*(1-moderate_tokens/current_tokens):.1f}% reduction)")

print(f"\nToken savings: {current_tokens - balanced_tokens} (balanced), {current_tokens - moderate_tokens} (moderate)")

# Expected latency improvement (assuming ~3-4ms per token for GLM-4.7)
ms_per_token = 3.5
balanced_latency_ms = (current_tokens - balanced_tokens) * ms_per_token
moderate_latency_ms = (current_tokens - moderate_tokens) * ms_per_token

print(f"\nExpected latency improvement: ~{balanced_latency_ms:.0f}ms (balanced), ~{moderate_latency_ms:.0f}ms (moderate)")

print("\n" + "="*60)
print("BALANCED OPTIMIZED PROMPT (RECOMMENDED):")
print("="*60)
print(balanced)

print("\n" + "="*60)
print("MODERATE OPTIMIZED PROMPT (MORE AGGRESSIVE):")
print("="*60)
print(moderate)
