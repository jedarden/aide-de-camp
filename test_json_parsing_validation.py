#!/usr/bin/env .venv/bin/python
"""
Quick validation test for JSON parsing optimizations.

Tests:
1. Fast path for clean JSON (no fences)
2. Fenced JSON processing
3. Performance comparison
"""

import time
from src.llm.response_parser import parse_llm_response, ParseLLMError


def test_clean_json_fast_path():
    """Test that clean JSON (no fences) takes fast path."""
    test_cases = [
        '{"intent_type": "status", "project_slug": "test"}',
        '[{"a": 1}, {"b": 2}]',
        '{"nested": {"data": {"value": 123}}}',
    ]

    for test_json in test_cases:
        start = time.perf_counter()
        result = parse_llm_response(test_json, strip_fences=True, expect_json=True)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"✓ Clean JSON parsed in {elapsed_ms:.3f}ms: {test_json[:40]}...")
        assert isinstance(result, dict) or isinstance(result, list)


def test_fenced_json():
    """Test fenced JSON processing."""
    test_cases = [
        '```json\n{"intent_type": "status"}\n```',
        '```\n{"intent_type": "status"}\n```',
        '```json\n{"code": "```hello```"}\n```',
    ]

    for test_json in test_cases:
        start = time.perf_counter()
        result = parse_llm_response(test_json, strip_fences=True, expect_json=True)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"✓ Fenced JSON parsed in {elapsed_ms:.3f}ms")
        assert isinstance(result, dict)


def test_performance_comparison():
    """Compare performance of clean vs fenced JSON."""
    clean_json = '{"intent_type": "status", "project_slug": "test", "data": {"value": 123}}'
    fenced_json = f'```json\n{clean_json}\n```'

    # Test clean JSON (should use fast path)
    iterations = 100
    clean_start = time.perf_counter()
    for _ in range(iterations):
        result = parse_llm_response(clean_json, strip_fences=True, expect_json=True)
    clean_total = (time.perf_counter() - clean_start) * 1000

    # Test fenced JSON
    fenced_start = time.perf_counter()
    for _ in range(iterations):
        result = parse_llm_response(fenced_json, strip_fences=True, expect_json=True)
    fenced_total = (time.perf_counter() - fenced_start) * 1000

    print(f"\n✓ Performance ({iterations} iterations):")
    print(f"  Clean JSON:   {clean_total:.2f}ms total ({clean_total/iterations:.3f}ms avg)")
    print(f"  Fenced JSON:  {fenced_total:.2f}ms total ({fenced_total/iterations:.3f}ms avg)")
    print(f"  Difference:   {fenced_total - clean_total:.2f}ms ({((fenced_total/clean_total) - 1) * 100:.1f}% slower)")

    # Clean JSON should be faster (or at least not significantly slower)
    assert clean_total <= fenced_total * 1.5, "Clean JSON should be faster or similar to fenced"


def test_error_handling():
    """Test error handling for malformed JSON."""
    test_cases = [
        '{"invalid": }',
        '```json\n{"broken"}\n```',
        '',
    ]

    for test_json in test_cases:
        try:
            result = parse_llm_response(test_json, strip_fences=True, expect_json=True)
            print(f"✗ Should have raised ParseLLMError for: {test_json[:40]}")
            assert False, "Expected ParseLLMError"
        except ParseLLMError as e:
            print(f"✓ Correctly raised ParseLLMError for: {test_json[:40]}...")
            assert e.raw_response is not None or test_json == ""


def test_no_fence_processing():
    """Test that strip_fences=False skips fence processing."""
    fenced_json = '```json\n{"intent_type": "status"}\n```'

    # With strip_fences=True, should parse successfully
    result_with_strip = parse_llm_response(fenced_json, strip_fences=True, expect_json=True)
    assert result_with_strip["intent_type"] == "status"

    # With strip_fences=False, should fail (can't parse the fences)
    try:
        result_no_strip = parse_llm_response(fenced_json, strip_fences=False, expect_json=True)
        print(f"✗ Should have failed without fence stripping")
        assert False, "Expected ParseLLMError"
    except ParseLLMError:
        print(f"✓ Correctly fails without fence stripping")


if __name__ == "__main__":
    print("Testing JSON parsing optimizations...\n")

    test_clean_json_fast_path()
    print()
    test_fenced_json()
    print()
    test_performance_comparison()
    print()
    test_error_handling()
    print()
    test_no_fence_processing()

    print("\n✅ All validation tests passed!")
