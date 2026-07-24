#!/usr/bin/env python3
"""
Test script to measure prompt token counts.
Uses rough estimates: ~1 token per 4 characters.
"""

import re

# Current prompt from router.md
current_prompt = """# Intent Router

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

# Optimized prompt
optimized_prompt = """# Intent Router
Classify utterances into intents. Return JSON array.

Types:
- status: Query state
- action: Execute commands
- brainstorm: Explore options
- lookup: Find info (lookup_kind: logs|config|docs)
- reminder: Time-based tasks
- task-profile: Multi-step work

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules:
- Different type/project/target → separate intents
- Map projects by name/alias/context"""

# Ultra-optimized prompt (more aggressive)
ultra_optimized_prompt = """# Intent Router
Classify utterances. Return JSON array.

Types: status/query | action/execute | brainstorm/explore | lookup/find | reminder/time | task-profile/multi-step

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project/target. Map projects by name."""

def count_tokens(text):
    """Count tokens using rough estimate: ~1 token per 4 characters."""
    # Remove extra whitespace for more accurate counting
    text = re.sub(r'\s+', ' ', text).strip()
    return len(text) // 4

if __name__ == "__main__":
    current_tokens = count_tokens(current_prompt)
    optimized_tokens = count_tokens(optimized_prompt)
    ultra_tokens = count_tokens(ultra_optimized_prompt)

    print(f"Current prompt: {current_tokens} tokens")
    print(f"Optimized prompt: {optimized_tokens} tokens ({100*(1-optimized_tokens/current_tokens):.1f}% reduction)")
    print(f"Ultra-optimized prompt: {ultra_tokens} tokens ({100*(1-ultra_tokens/current_tokens):.1f}% reduction)")
    print(f"\nToken savings: {current_tokens - optimized_tokens} tokens (optimized), {current_tokens - ultra_tokens} tokens (ultra)")

    # Show the prompts
    print("\n" + "="*50)
    print("CURRENT PROMPT:")
    print("="*50)
    print(current_prompt)

    print("\n" + "="*50)
    print("OPTIMIZED PROMPT:")
    print("="*50)
    print(optimized_prompt)

    print("\n" + "="*50)
    print("ULTRA-OPTIMIZED PROMPT:")
    print("="*50)
    print(ultra_optimized_prompt)
