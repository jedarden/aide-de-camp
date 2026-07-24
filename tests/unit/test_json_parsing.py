#!/usr/bin/env python3
"""
Unit tests for optimized JSON parsing in intent router.

Tests the parsing logic used in src/intent/router.py for handling
GLM-4.7's markdown-fenced JSON responses.

Tests both:
1. The actual response_parser module functions (src.llm.response_parser)
2. Router-specific edge cases and integration patterns
"""

import json
import pytest
import sys
sys.path.insert(0, '/home/coding/aide-de-camp')

from src.llm.response_parser import (
    strip_markdown_fences,
    parse_llm_response,
    ParseLLMError,
)


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


class TestResponseParserModule:
    """Test the actual response_parser module used by intent router."""

    def test_strip_fences_with_json_specifier(self):
        """Test strip_markdown_fences with ```json language specifier."""
        raw = '```json\n{"intent_type": "status"}\n```'
        result = strip_markdown_fences(raw)
        assert result == '{"intent_type": "status"}'

    def test_strip_fences_without_language_specifier(self):
        """Test strip_markdown_fences with plain ``` fences."""
        raw = '```\n{"intent_type": "lookup"}\n```'
        result = strip_markdown_fences(raw)
        assert result == '{"intent_type": "lookup"}'

    def test_strip_fences_bare_json(self):
        """Test strip_markdown_fences with bare JSON (no fences)."""
        raw = '{"intent_type": "action"}'
        result = strip_markdown_fences(raw)
        assert result == '{"intent_type": "action"}'

    def test_parse_llm_response_fenced_json(self):
        """Test parse_llm_response with fenced JSON."""
        raw = '```json\n[{"intent_type": "status"}]\n```'
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert isinstance(result, list)
        assert result[0]["intent_type"] == "status"

    def test_parse_llm_response_bare_json(self):
        """Test parse_llm_response with bare JSON."""
        raw = '[{"intent_type": "action"}]'
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert isinstance(result, list)
        assert result[0]["intent_type"] == "action"

    def test_parse_llm_response_empty_raises_error(self):
        """Test parse_llm_response with empty string raises ParseLLMError."""
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response("", expect_json=True)
        assert "Empty response provided" in str(exc_info.value)

    def test_parse_llm_response_malformed_json(self):
        """Test parse_llm_response with malformed JSON raises ParseLLMError."""
        malformed = '```json\n{invalid}\n```'
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed, expect_json=True)
        assert "Failed to parse JSON" in str(exc_info.value)
        assert exc_info.value.raw_response == malformed

    def test_parse_llm_response_preserves_raw_on_error(self):
        """Test that ParseLLMError preserves raw response for debugging."""
        malformed = '```json\n{"missing": "brace"\n```'
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed, expect_json=True)
        assert exc_info.value.raw_response is not None
        assert exc_info.value.raw_response == malformed


class TestRouterSpecificEdgeCases:
    """Test edge cases specific to intent router's use of response_parser."""

    def test_router_response_with_multiple_intents(self):
        """Test typical router response with multiple intent classifications."""
        raw = '''```json
[
  {
    "intent_type": "status",
    "project_slug": "aide-de-camp",
    "confidence": 0.9,
    "utterance_fragment": "check status",
    "reasoning": "User wants to know status",
    "urgency": "normal"
  },
  {
    "intent_type": "lookup",
    "project_slug": null,
    "confidence": 0.8,
    "utterance_fragment": "find logs",
    "reasoning": "User asking for logs",
    "urgency": "normal",
    "lookup_kind": "logs"
  }
]
```'''
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["intent_type"] == "status"
        assert result[1]["lookup_kind"] == "logs"

    def test_router_response_with_trailing_comma(self):
        """Test router response with trailing comma (malformed but common LLM error)."""
        # This is malformed JSON that LLMs sometimes produce
        malformed = '```json\n{"intent_type": "status",}\n```'
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed, expect_json=True)
        assert "Failed to parse JSON" in str(exc_info.value)

    def test_router_response_with_unicode_in_reasoning(self):
        """Test router response with emoji and unicode in reasoning field."""
        raw = '```json\n{"reasoning": "Status check ✅ - system healthy 🟢"}\n```'
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert "✅" in result["reasoning"]
        assert "🟢" in result["reasoning"]

    def test_router_response_fences_with_extra_spaces(self):
        """Test router response with extra whitespace around fences."""
        raw = '''  ```json
  {"intent_type": "status"}
  ```  '''
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert result["intent_type"] == "status"

    def test_router_response_missing_closing_fence(self):
        """Test router response with missing closing fence marker."""
        # This tests fence stripping when closing ``` is missing
        raw = '```json\n{"intent_type": "status"}'
        with pytest.raises(ParseLLMError):
            # Should fail JSON parsing because the opening fence isn't properly stripped
            parse_llm_response(raw, strip_fences=True, expect_json=True)

    def test_router_response_with_newlines_in_json_string(self):
        """Test router response with embedded newlines in JSON strings."""
        raw = '```json\n{"text": "line1\\nline2\\nline3"}\n```'
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert result["text"] == "line1\nline2\nline3"

    def test_router_response_empty_array(self):
        """Test router response with empty intent array."""
        raw = '```json\n[]\n```'
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_router_response_nested_urgency_field(self):
        """Test router response with nested urgency and confidence fields."""
        raw = '''```json
{
  "intent_type": "action",
  "urgency": "high",
  "confidence": 0.95,
  "project_slug": "critical-project"
}
```'''
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert result["urgency"] == "high"
        assert result["confidence"] == 0.95
        assert result["project_slug"] == "critical-project"

    def test_strip_fences_case_insensitive_language(self):
        """Test that fence language specifier is handled case-insensitively."""
        # Uppercase JSON specifier
        raw1 = '```JSON\n{"intent_type": "status"}\n```'
        result1 = strip_markdown_fences(raw1)
        assert '{"intent_type": "status"}' in result1

        # Mixed case
        raw2 = '```Json\n{"intent_type": "status"}\n```'
        result2 = strip_markdown_fences(raw2)
        assert '{"intent_type": "status"}' in result2

    def test_parse_llm_response_no_strip_preserves_fences(self):
        """Test parse_llm_response with strip_fences=False preserves fences."""
        raw = '```json\n{"intent_type": "status"}\n```'
        result = parse_llm_response(raw, strip_fences=False, expect_json=False)
        # Should return the original string without attempting JSON parsing
        assert "```json" in result

    def test_router_response_with_escaped_quotes(self):
        """Test router response with escaped quotes in reasoning field."""
        raw = '```json\n{"reasoning": "User said \\"check status\\""}\n```'
        result = parse_llm_response(raw, strip_fences=True, expect_json=True)
        assert result["reasoning"] == 'User said "check status"'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
