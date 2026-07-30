#!/usr/bin/env python3
"""Test that the router prompt loads correctly."""

import sys
sys.path.insert(0, '/home/coding/aide-de-camp')

from src.components.hot_reload import get_reload_manager

def test_prompt_load():
    """Test that the router prompt loads correctly."""
    try:
        manager = get_reload_manager()
        prompt = manager.get_prompt('router')
        print("✓ Router prompt loaded successfully")
        print(f"✓ Prompt length: {len(prompt)} characters")
        print(f"✓ First 200 chars:\n{prompt[:200]}")
        return True
    except Exception as e:
        print(f"✗ Failed to load router prompt: {e}")
        return False

if __name__ == "__main__":
    success = test_prompt_load()
    sys.exit(0 if success else 1)
