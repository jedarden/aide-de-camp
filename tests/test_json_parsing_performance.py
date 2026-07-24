"""
Performance regression tests for JSON parsing.

Ensures that JSON parsing operations stay within acceptable performance bounds
to prevent regressions after refactoring or optimization changes.

Based on baseline metrics from bead adc-3e5gg.
"""

import json
import pytest
import time
from src.llm.response_parser import (
    strip_markdown_fences,
    parse_llm_response,
    ParseLLMError,
)


# ============================================================================
# Test Fixtures
# ============================================================================

# Small payload (~200 bytes) - typical router response
_SMALL_PAYLOAD_JSON = json.dumps({
    "intents": [
        {
            "intent_type": "status",
            "project_slug": "aide-de-camp",
            "confidence": 0.95,
            "utterance_fragment": "how are the pods doing?",
            "reasoning": "User wants pod status",
            "urgency": "normal"
        }
    ]
})

# Medium payload (~500 bytes) - typical synthesize response
_MEDIUM_PAYLOAD_JSON = json.dumps({
    "data": {
        "type": "pod-status",
        "items": [
            {"name": "web-0", "phase": "Running", "ready": "1/1", "restarts": 0},
            {"name": "web-1", "phase": "Running", "ready": "1/1", "restarts": 0},
            {"name": "worker-0", "phase": "Running", "ready": "1/1", "restarts": 2},
            {"name": "worker-1", "phase": "Pending", "ready": "0/1", "restarts": 0},
        ],
        "summary_fields": {
            "total": 4,
            "running": 3,
            "pending": 1,
            "restarts": 2
        }
    },
    "summary": "Cluster has 4 pods: 3 running, 1 pending. Total restarts: 2.",
    "urgency": "normal"
})

# Large payload (~13.1 KB) - complex fetch result
_LARGE_PAYLOAD_JSON = json.dumps({
    "data": {
        "type": "comprehensive-status",
        "sources": [
            {"name": f"source-{i}", "status": "healthy", "metrics": {"cpu": 50, "memory": 60}}
            for i in range(100)
        ],
        "aggregations": {
            "total_sources": 100,
            "healthy_count": 100,
            "unhealthy_count": 0
        }
    },
    "summary": "All 100 sources are healthy.",
    "urgency": "low"
})


# ============================================================================
# Performance Baselines (from adc-3e5gg benchmark)
# ============================================================================

# Manual fence stripping is the baseline (fastest approach)
# Baseline: ~0.0004ms for small, ~0.0004ms for medium, ~0.0009ms for large
# We allow 10x slack for test stability across different machines
_SMALL_FENCE_MAX_MS = 0.01  # 10x baseline of 0.0004ms
_MEDIUM_FENCE_MAX_MS = 0.01  # 10x baseline of 0.0004ms
_LARGE_FENCE_MAX_MS = 0.05  # 10x baseline of 0.0009ms

# Full parse_llm_response with optimized strip_markdown_fences
# Baseline after optimization: should be close to manual approach
_SMALL_PARSE_MAX_MS = 0.02  # Allow 2x fence stripping overhead
_MEDIUM_PARSE_MAX_MS = 0.02
_LARGE_PARSE_MAX_MS = 0.10


# ============================================================================
# Performance Tests
# ============================================================================

def _measure_avg_time_ms(func: callable, iterations: int = 1000) -> float:
    """Measure average execution time in milliseconds."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms
    return sum(times) / len(times)


def test_fence_stripping_small_payload_performance():
    """Test fence stripping on small payload stays within bounds."""
    fenced = f'```json\n{_SMALL_PAYLOAD_JSON}\n```'

    avg_time = _measure_avg_time_ms(lambda: strip_markdown_fences(fenced))

    assert avg_time < _SMALL_FENCE_MAX_MS, (
        f"Fence stripping too slow on small payload: {avg_time:.4f}ms "
        f"(max: {_SMALL_FENCE_MAX_MS:.4f}ms)"
    )


def test_fence_stripping_medium_payload_performance():
    """Test fence stripping on medium payload stays within bounds."""
    fenced = f'```json\n{_MEDIUM_PAYLOAD_JSON}\n```'

    avg_time = _measure_avg_time_ms(lambda: strip_markdown_fences(fenced))

    assert avg_time < _MEDIUM_FENCE_MAX_MS, (
        f"Fence stripping too slow on medium payload: {avg_time:.4f}ms "
        f"(max: {_MEDIUM_FENCE_MAX_MS:.4f}ms)"
    )


def test_fence_stripping_large_payload_performance():
    """Test fence stripping on large payload stays within bounds."""
    fenced = f'```json\n{_LARGE_PAYLOAD_JSON}\n```'

    avg_time = _measure_avg_time_ms(lambda: strip_markdown_fences(fenced))

    assert avg_time < _LARGE_FENCE_MAX_MS, (
        f"Fence stripping too slow on large payload: {avg_time:.4f}ms "
        f"(max: {_LARGE_FENCE_MAX_MS:.4f}ms)"
    )


def test_parse_llm_response_small_payload_performance():
    """Test full parsing pipeline on small payload stays within bounds."""
    fenced = f'```json\n{_SMALL_PAYLOAD_JSON}\n```'

    avg_time = _measure_avg_time_ms(lambda: parse_llm_response(fenced))

    assert avg_time < _SMALL_PARSE_MAX_MS, (
        f"parse_llm_response too slow on small payload: {avg_time:.4f}ms "
        f"(max: {_SMALL_PARSE_MAX_MS:.4f}ms)"
    )


def test_parse_llm_response_medium_payload_performance():
    """Test full parsing pipeline on medium payload stays within bounds."""
    fenced = f'```json\n{_MEDIUM_PAYLOAD_JSON}\n```'

    avg_time = _measure_avg_time_ms(lambda: parse_llm_response(fenced))

    assert avg_time < _MEDIUM_PARSE_MAX_MS, (
        f"parse_llm_response too slow on medium payload: {avg_time:.4f}ms "
        f"(max: {_MEDIUM_PARSE_MAX_MS:.4f}ms)"
    )


def test_parse_llm_response_large_payload_performance():
    """Test full parsing pipeline on large payload stays within bounds."""
    fenced = f'```json\n{_LARGE_PAYLOAD_JSON}\n```'

    avg_time = _measure_avg_time_ms(lambda: parse_llm_response(fenced))

    assert avg_time < _LARGE_PARSE_MAX_MS, (
        f"parse_llm_response too slow on large payload: {avg_time:.4f}ms "
        f"(max: {_LARGE_PARSE_MAX_MS:.4f}ms)"
    )


# ============================================================================
# Correctness Tests (ensure optimization didn't break functionality)
# ============================================================================

def test_fence_stripping_correctness_json_fence():
    """Test that fence stripping works correctly with ```json fence."""
    fenced = '```json\n{"key": "value"}\n```'
    result = strip_markdown_fences(fenced)
    assert result == '{"key": "value"}'


def test_fence_stripping_correctness_plain_fence():
    """Test that fence stripping works correctly with ``` fence."""
    fenced = '```\n{"key": "value"}\n```'
    result = strip_markdown_fences(fenced)
    assert result == '{"key": "value"}'


def test_fence_stripping_correctness_no_fence():
    """Test that fence stripping doesn't affect plain JSON."""
    plain = '{"key": "value"}'
    result = strip_markdown_fences(plain)
    assert result == '{"key": "value"}'


def test_fence_stripping_correctness_multiline():
    """Test that fence stripping works with multiline content."""
    fenced = '```json\n{\n  "key": "value",\n  "nested": {\n    "a": 1\n  }\n}\n```'
    result = strip_markdown_fences(fenced)
    assert result == '{\n  "key": "value",\n  "nested": {\n    "a": 1\n  }\n}'


def test_parse_llm_response_correctness():
    """Test that full parsing pipeline produces correct results."""
    fenced = '```json\n{"key": "value", "number": 42}\n```'
    result = parse_llm_response(fenced)
    assert result == {"key": "value", "number": 42}


def test_parse_llm_response_no_fence():
    """Test that parsing works without fence."""
    plain = '{"key": "value"}'
    result = parse_llm_response(plain)
    assert result == {"key": "value"}


def test_parse_llm_response_strip_fences_false():
    """Test that parsing with strip_fences=False preserves fences."""
    fenced = '```json\n{"key": "value"}\n```'
    result = parse_llm_response(fenced, strip_fences=False, expect_json=False)
    assert result.startswith('```json')


def test_parse_llm_response_error_handling():
    """Test that ParseLLMError is raised for malformed JSON."""
    malformed = '```json\n{invalid json}\n```'
    with pytest.raises(ParseLLMError):
        parse_llm_response(malformed)


def test_parse_llm_response_empty_input():
    """Test that empty input is handled correctly."""
    with pytest.raises(ParseLLMError):
        parse_llm_response("")


# ============================================================================
# Intent Router Specific Tests
# ============================================================================

def test_intent_router_parsing_correctness():
    """Test parsing of typical intent router response (JSON array)."""
    router_response = '''```json
[
    {
        "intent_type": "status",
        "project_slug": "aide-de-camp",
        "confidence": 0.95,
        "utterance_fragment": "how are the pods doing?",
        "reasoning": "User wants pod status",
        "urgency": "normal"
    },
    {
        "intent_type": "lookup",
        "project_slug": "aide-de-camp",
        "confidence": 0.85,
        "utterance_fragment": "check the logs",
        "reasoning": "User wants to see logs",
        "urgency": "high",
        "lookup_kind": "logs"
    }
]
```'''
    result = parse_llm_response(router_response)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["intent_type"] == "status"
    assert result[1]["intent_type"] == "lookup"
    assert result[1]["lookup_kind"] == "logs"


def test_intent_router_parsing_with_extra_whitespace():
    """Test parsing with irregular whitespace (GLM-4.7 sometimes adds extra spacing)."""
    router_response = '''```json

[
    {
        "intent_type": "status",
        "project_slug": "aide-de-camp"
    }
]

```'''
    result = parse_llm_response(router_response)
    assert isinstance(result, list)
    assert len(result) == 1


def test_intent_router_parsing_fence_with_language_marker():
    """Test parsing with different fence language markers."""
    for fence_lang in ["```json", "```JSON", "```", "```javascript"]:
        router_response = f'''{fence_lang}
[
    {{"intent_type": "status", "project_slug": "aide-de-camp"}}
]
{fence_lang}'''
        result = parse_llm_response(router_response)
        assert isinstance(result, list)
        assert len(result) == 1


def test_intent_router_parsing_single_intent():
    """Test parsing single intent (router can return 1+ intents)."""
    router_response = '''```json
[
    {
        "intent_type": "action",
        "project_slug": "spaxel",
        "confidence": 0.90,
        "utterance_fragment": "deploy the latest",
        "reasoning": "User wants to deploy"
    }
]
```'''
    result = parse_llm_response(router_response)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["intent_type"] == "action"


def test_intent_router_parsing_error_handling_malformed():
    """Test that malformed router responses raise ParseLLMError with raw_response."""
    malformed = '''```json
[
    {{"intent_type": "status", "invalid": }}
]
```'''
    with pytest.raises(ParseLLMError) as exc_info:
        parse_llm_response(malformed)

    # Verify raw_response is preserved for error reporting
    assert exc_info.value.raw_response is not None
    assert "invalid" in exc_info.value.raw_response or "Failed to parse" in str(exc_info.value)


def test_intent_router_parsing_bare_json():
    """Test parsing router response without fences (some models don't fence)."""
    bare_json = '''[
    {"intent_type": "status", "project_slug": "aide-de-camp"}
]'''
    result = parse_llm_response(bare_json)
    assert isinstance(result, list)
    assert len(result) == 1


def test_intent_router_parsing_empty_fences():
    """Test handling of fences with empty/whitespace content."""
    with pytest.raises(ParseLLMError):
        parse_llm_response("```json\n\n```")


def test_fence_stripping_no_trailing_newline_before_fence():
    """Test fence stripping when closing fence is directly after JSON (no trailing newline)."""
    no_trailing_nl = '```json\n{"key": "value"}```'
    result = strip_markdown_fences(no_trailing_nl)
    assert result == '{"key": "value"}'


def test_fence_stripping_multiple_fences():
    """Test that only outermost fences are stripped (content may contain ```)."""
    with_fences_in_content = '```json\n{"code": "console.log(````hello```")"}\n```'
    result = strip_markdown_fences(with_fences_in_content)
    assert result == '{"code": "console.log(````hello```")"}'
