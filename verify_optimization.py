#!/usr/bin/env python3
"""Verify the router.md prompt optimization."""

import re
from pathlib import Path

def count_tokens(text: str) -> int:
    """Estimate token count: ~1 token per 4 characters."""
    text = re.sub(r'\s+', ' ', text).strip()
    return len(text) // 4

router_md = Path("/home/coding/aide-de-camp/prompts/router.md")
actual_prompt = router_md.read_text()

print("="*60)
print("Router.md Prompt Verification")
print("="*60)

token_count = count_tokens(actual_prompt)

print(f"\n📏 Current router.md:")
print(f"  Tokens: {token_count}")
print(f"  Characters: {len(actual_prompt)}")

print(f"\n📄 Content:")
print("-"*60)
print(actual_prompt)
print("-"*60)

# Original prompt for comparison
original_prompt = """# Intent Router
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

original_tokens = count_tokens(original_prompt)

print(f"\n📊 Comparison:")
print(f"  Original: {original_tokens} tokens")
print(f"  Current:  {token_count} tokens")
print(f"  Reduction: {100*(1-token_count/original_tokens):.1f}%")

if token_count <= 80:
    print(f"  ✅ Target achieved: ≤80 tokens")
else:
    print(f"  ❌ Target missed: should be ≤80 tokens")

print(f"\n📋 Intent Types:")
types = re.findall(r'Types: (.+)', actual_prompt)
if types:
    print(f"  {types[0]}")

schema = re.findall(r'Schema: (.+)', actual_prompt)
if schema:
    print(f"\n📋 Schema:")
    print(f"  {schema[0]}")

rules = re.findall(r'Rules: (.+)', actual_prompt)
if rules:
    print(f"\n📋 Rules:")
    print(f"  {rules[0]}")

print(f"\n{'='*60}")
