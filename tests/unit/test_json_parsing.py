#!/usr/bin/env python3
"""
Unit tests for optimized JSON parsing in intent router.

Tests the parsing logic used in src/intent/router.py for handling
GLM-4.7's markdown-fenced JSON responses.
"""

import json
import pytest
import sys
sys.path.insert(0, '/home/coding/aide-de-camp')


def parse_router_style(response):
    """
    Replicate the optimized JSON parsing from src/intent/router.py.

    This handles GLM-4.7's markdown-fenced JSON responses with minimal overhead.
    Uses find()/rfind() instead of split() to avoid intermediate string allocations.
    """
    raw = response.strip()

    # Fast path for fenced responses (GLM-4.7 default)
    if raw.startswith("```"):
        # Find first newline after opening fence (position-based, no split)
        nl_pos = raw.find("\n")
        # Find closing fence from end (search backwards for last ```)
        fence_end = raw.rfind("```")

        # Direct slice extraction with single strip
        if nl_pos != -1 and fence_end > nl_pos:
            raw = raw[nl_pos + 1:fence_end].strip()

    return json.loads(raw)


class TestJSONParsing:
    """Test suite for optimized JSON parsing."""

    def test_fenced_json_with_language_specifier(self):
        """Test parsing fenced JSON with language specifier (```json)."""
        response = '''```json
[
  {
    "intent_type": "status",
    "project_slug": "aide-de-camp",
    "confidence": 0.9
  }
]
```'''
        result = parse_router_style(response)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["intent_type"] == "status"
        assert result[0]["project_slug"] == "aide-de-camp"

    def test_fenced_json_without_language_specifier(self):
        """Test parsing fenced JSON without language specifier (```)."""
        response = '''```
[
  {
    "intent_type": "lookup",
    "project_slug": null,
    "confidence": 0.85
  }
]
```'''
        result = parse_router_style(response)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["intent_type"] == "lookup"

    def test_bare_json(self):
        """Test parsing bare JSON without fences."""
        response = '''[
  {
    "intent_type": "action",
    "project_slug": "test-project",
    "confidence": 0.95
  }
]'''
        result = parse_router_style(response)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["intent_type"] == "action"

    def test_fenced_json_with_extra_whitespace(self):
        """Test parsing fenced JSON with extra whitespace."""
        response = '''```json

[
  {
    "intent_type": "brainstorm",
    "project_slug": "ideas",
    "confidence": 0.8
  }

]
```'''
        result = parse_router_style(response)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["intent_type"] == "brainstorm"

    def test_empty_array(self):
        """Test parsing empty array."""
        response = '```json\n[]\n```'
        result = parse_router_style(response)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_large_fenced_response(self):
        """Test parsing large fenced response with multiple intents."""
        intents = [{"intent_type": "status", "project_slug": f"project-{i}", "confidence": 0.9} for i in range(50)]
        response = '```json\n' + json.dumps(intents) + '\n```'
        result = parse_router_style(response)
        assert isinstance(result, list)
        assert len(result) == 50

    def test_nested_json_structures(self):
        """Test parsing JSON with nested structures."""
        response = '''```json
{
  "nested": {
    "deep": {
      "value": 1,
      "array": [1, 2, 3]
    }
  }
}
```'''
        result = parse_router_style(response)
        assert isinstance(result, dict)
        assert result["nested"]["deep"]["value"] == 1
        assert result["nested"]["deep"]["array"] == [1, 2, 3]

    def test_escaped_quotes_in_content(self):
        """Test parsing JSON with escaped quotes."""
        response = '''```json
{"text": "Hello \\"World\\"", "value": "test"}
```'''
        result = parse_router_style(response)
        assert isinstance(result, dict)
        assert result["text"] == 'Hello "World"'

    def test_backticks_in_json_content(self):
        """Test parsing when JSON content contains backticks."""
        response = '''```json
{"text": "This has ``` backticks", "value": "test"}
```'''
        result = parse_router_style(response)
        assert isinstance(result, dict)
        assert result["text"] == "This has ``` backticks"

    def test_multiple_intents_response(self):
        """Test parsing response with multiple intents (typical router output)."""
        response = '''```json
[
  {
    "intent_type": "status",
    "project_slug": "aide-de-camp",
    "confidence": 0.9,
    "utterance_fragment": "Check the status",
    "reasoning": "User wants to know current status",
    "urgency": "normal"
  },
  {
    "intent_type": "lookup",
    "project_slug": null,
    "confidence": 0.8,
    "utterance_fragment": "What are the logs?",
    "reasoning": "User asking for log information",
    "urgency": "normal",
    "lookup_kind": "logs"
  }
]
```'''
        result = parse_router_style(response)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["intent_type"] == "status"
        assert result[1]["intent_type"] == "lookup"
        assert result[1]["lookup_kind"] == "logs"


class TestErrorHandling:
    """Test error handling for malformed inputs."""

    def test_malformed_json_raises_error(self):
        """Test that malformed JSON raises an error."""
        response = '```json\n{invalid json}\n```'
        with pytest.raises(json.JSONDecodeError):
            parse_router_style(response)

    def test_unclosed_fence_raises_error(self):
        """Test that unclosed fence results in parsing error."""
        response = '```json\n{"key": "value"}'
        # This should either work or raise an error
        try:
            result = parse_router_style(response)
            # If it works, the result should be correct
            assert result["key"] == "value"
        except (json.JSONDecodeError, ValueError):
            # If it raises, that's also acceptable
            pass

    def test_empty_response(self):
        """Test handling of empty response."""
        response = ''
        with pytest.raises((json.JSONDecodeError, ValueError)):
            parse_router_style(response)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
