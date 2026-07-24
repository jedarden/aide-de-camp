"""
Edge case test coverage for JSON parsing.

Tests for unusual, boundary, and malformed inputs that could cause parsing
failures in production. Ensures robustness of strip_markdown_fences() and
parse_llm_response() functions.

Based on audit adc-5mbc6 and task adc-636du.
"""

import json
import pytest
from src.llm.response_parser import (
    strip_markdown_fences,
    parse_llm_response,
    ParseLLMError,
)


# ============================================================================
# Empty String Edge Cases
# ============================================================================

class TestEmptyStringEdgeCases:
    """Test various forms of empty or whitespace-only input."""

    def test_strip_markdown_fences_empty_string(self):
        """Test completely empty string."""
        result = strip_markdown_fences("")
        assert result == ""

    def test_strip_markdown_fences_whitespace_only(self):
        """Test string with only spaces."""
        result = strip_markdown_fences("   ")
        assert result == "   "

    def test_strip_markdown_fences_newlines_only(self):
        """Test string with only newlines."""
        result = strip_markdown_fences("\n\n\n")
        assert result == "\n\n\n"

    def test_strip_markdown_fences_tabs_only(self):
        """Test string with only tabs."""
        result = strip_markdown_fences("\t\t\t")
        assert result == "\t\t\t"

    def test_strip_markdown_fences_mixed_whitespace(self):
        """Test string with mixed whitespace characters."""
        result = strip_markdown_fences("  \n\t  \n  ")
        assert result == "  \n\t  \n  "

    def test_strip_markdown_fences_empty_json_fence(self):
        """Test fence with no content between fences."""
        result = strip_markdown_fences("```json\n\n```")
        assert result == ""

    def test_strip_markdown_fences_empty_plain_fence(self):
        """Test plain fence with no content."""
        result = strip_markdown_fences("```\n\n```")
        assert result == ""

    def test_strip_markdown_fences_empty_fence_whitespace(self):
        """Test fence with only whitespace between fences."""
        result = strip_markdown_fences("```json\n   \n```")
        assert result == ""

    def test_parse_llm_response_empty_string_raises(self):
        """Test empty string raises ParseLLMError when expecting JSON."""
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response("")
        assert "Empty response provided" in str(exc_info.value)

    def test_parse_llm_response_whitespace_only_raises(self):
        """Test whitespace-only string raises ParseLLMError when expecting JSON."""
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response("   \n  \t  ")
        assert "Empty response provided" in str(exc_info.value)

    def test_parse_llm_response_empty_string_no_json(self):
        """Test empty string is returned when not expecting JSON."""
        result = parse_llm_response("", expect_json=False)
        assert result == ""

    def test_parse_llm_response_whitespace_only_no_json(self):
        """Test whitespace-only string is returned when not expecting JSON."""
        result = parse_llm_response("  \n  ", expect_json=False)
        assert result == "  \n  "


# ============================================================================
# Malformed JSON with Markdown Fences
# ============================================================================

class TestMalformedJsonWithFences:
    """Test malformed JSON wrapped in markdown fences."""

    def test_malformed_json_missing_closing_brace(self):
        """Test JSON with missing closing brace inside fences."""
        malformed = "```json\n{\"key\": \"value\"\n```"
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed)
        assert "Failed to parse JSON" in str(exc_info.value)

    def test_malformed_json_missing_opening_brace(self):
        """Test JSON with missing opening brace inside fences."""
        malformed = "```json\n\"key\": \"value\"}\n```"
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)

    def test_malformed_json_trailing_comma(self):
        """Test JSON with trailing comma inside fences."""
        malformed = "```json\n{\"key\": \"value\",}\n```"
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)

    def test_malformed_json_unclosed_string(self):
        """Test JSON with unclosed string inside fences."""
        malformed = "```json\n{\"key\": \"value\n```"
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)

    def test_malformed_json_invalid_escape_sequence(self):
        """Test JSON with invalid escape sequence inside fences."""
        malformed = "```json\n{\"key\": \"value\\x\"}\n```"
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)

    def test_malformed_json_missing_value(self):
        """Test JSON with missing value after colon."""
        malformed = "```json\n{\"key\":}\n```"
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)

    def test_malformed_json_comma_instead_of_colon(self):
        """Test JSON with comma instead of colon."""
        malformed = "```json\n{\"key\", \"value\"}\n```"
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)

    def test_malformed_json_extra_comma(self):
        """Test JSON with extra comma inside fences."""
        malformed = "```json\n{\"key\": \"value\",,}\n```"
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)


# ============================================================================
# Nested/Malformed Fence Patterns
# ============================================================================

class TestNestedAndMalformedFencePatterns:
    """Test edge cases with fence patterns within content."""

    def test_triple_backtick_in_json_string(self):
        """Test JSON containing triple backticks as a value."""
        # Use escaped newlines in JSON (\\n becomes \n after parsing)
        json_with_backticks = r'{"code": "```python\nprint(\"hello\")\n```"}'
        fenced = f"```json\n{json_with_backticks}\n```"
        result = parse_llm_response(fenced)
        assert result["code"] == "```python\nprint(\"hello\")\n```"

    def test_multiple_fences_in_json_string(self):
        """Test JSON containing multiple fence markers."""
        json_with_fences = '{"description": "Use ``` for code blocks"}'
        fenced = f"```json\n{json_with_fences}\n```"
        result = parse_llm_response(fenced)
        assert result["description"] == "Use ``` for code blocks"

    def test_nested_fence_like_pattern(self):
        """Test content that looks like nested fences but isn't."""
        content = '{"explain": "The fence pattern ``` is used for markdown"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert "```" in result["explain"]

    def test_incomplete_fence_at_start(self):
        """Test string starting with only two backticks."""
        content = '{"key": "value"}'
        fenced = f"``json\n{content}\n```"
        result = strip_markdown_fences(fenced)
        # Should NOT strip anything (doesn't start with 3 backticks)
        assert result == fenced

    def test_fence_without_language_specifier(self):
        """Test fence with content but no language specifier."""
        content = '{"key": "value"}'
        fenced = f"```\n{content}\n```"
        result = strip_markdown_fences(fenced)
        assert result == content

    def test_fence_with_extra_backticks(self):
        """Test fence with 4+ backticks."""
        content = '{"key": "value"}'
        fenced = f"````json\n{content}\n````"
        result = strip_markdown_fences(fenced)
        # The function strips the first ``` and then rsplit removes another ````
        # leaving one backtick - this is expected behavior for non-standard fence
        assert result == f"{content}\n`"

    def test_fence_no_newline_after_opening(self):
        """Test fence with no newline after opening marker."""
        content = '{"key": "value"}'
        # Not standard markdown but some LLMs might do this
        fenced = f"```json{content}\n```"
        result = strip_markdown_fences(fenced)
        # When there's no newline after opening fence, the function's split logic
        # results in empty string because it splits on first \n which is after the content
        assert result == ""

    def test_multiple_closing_fences(self):
        """Test content with multiple closing fence markers."""
        content = '{"key": "value", "note": "end ```"}'
        fenced = f"```json\n{content}\n```\n```"
        result = strip_markdown_fences(fenced)
        # rsplit removes the LAST ``` marker, keeping everything before it
        # So we get the content with the proper closing fence, minus the extra ```
        expected = f"{content}\n```"
        assert result == expected

    def test_fence_in_middle_of_json(self):
        """Test fence marker appearing within JSON structure."""
        # This is malformed but tests parsing behavior
        content = '{"key1": "value1", "```": "fence", "key2": "value2"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["```"] == "fence"


# ============================================================================
# Unicode and Special Characters
# ============================================================================

class TestUnicodeAndSpecialCharacters:
    """Test handling of Unicode and special characters in fenced content."""

    def test_unicode_emoji_in_json(self):
        """Test JSON with emoji characters."""
        content = '{"status": "✅", "mood": "😊", "weather": "🌤️"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["status"] == "✅"
        assert result["mood"] == "😊"
        assert result["weather"] == "🌤️"

    def test_unicode_chinese_characters(self):
        """Test JSON with Chinese characters."""
        content = '{"name": "张三", "city": "北京", "message": "你好世界"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["name"] == "张三"
        assert result["city"] == "北京"
        assert result["message"] == "你好世界"

    def test_unicode_arabic_characters(self):
        """Test JSON with Arabic characters (RTL text)."""
        content = '{"greeting": "مرحبا", "name": "أحمد"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["greeting"] == "مرحبا"
        assert result["name"] == "أحمد"

    def test_unicode_cyrillic_characters(self):
        """Test JSON with Cyrillic characters."""
        content = '{"greeting": "Привет", "name": "Иван"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["greeting"] == "Привет"
        assert result["name"] == "Иван"

    def test_special_escape_sequences(self):
        """Test JSON with various escape sequences."""
        content = r'{"newline": "\n", "tab": "\t", "quote": "\"", "backslash": "\\"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["newline"] == "\n"
        assert result["tab"] == "\t"
        assert result["quote"] == '"'
        assert result["backslash"] == "\\"

    def test_unicode_surrogate_pairs(self):
        """Test JSON with characters requiring surrogate pairs."""
        # Using character outside BMP
        content = '{"symbol": "𝕿𝖍𝖎𝖘 𝖎𝖘 𝖆 𝖙𝖊𝖘𝖙"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert "𝕿" in result["symbol"]

    def test_mixed_line_endings(self):
        """Test JSON with mixed line endings (\\r\\n vs \\n)."""
        content = '{\r\n"key": "value"\r\n}'
        fenced = f"```json\r\n{content}\r\n```"
        result = parse_llm_response(fenced)
        assert result["key"] == "value"

    def test_null_character_in_json_string(self):
        """Test JSON containing null character via escaped unicode."""
        # Using \\u0000 which is valid JSON escape for null character
        content = '{"key": "value\\u0000end"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        # After JSON parsing, the null character should be in the string
        assert result["key"] == "value\x00end"

    def test_zero_width_joiner(self):
        """Test JSON with emoji zero-width joiner sequences."""
        content = '{"family": "👨‍👩‍👧‍👦", "skin_tone": "👋🏽"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        # These should be preserved
        assert len(result["family"]) > 0
        assert len(result["skin_tone"]) > 0


# ============================================================================
# Large Payload Edge Cases
# ============================================================================

class TestLargePayloadEdgeCases:
    """Test very large payloads to ensure no memory issues."""

    def test_very_large_payload_no_crash(self):
        """Test that very large payload doesn't cause crashes."""
        # Create a JSON payload ~1MB in size
        large_data = {
            "items": [
                {
                    "id": i,
                    "name": f"item-{i}",
                    "description": "x" * 100,  # 100 char description
                    "tags": [f"tag-{j}" for j in range(10)],
                    "metadata": {
                        "created": 1234567890,
                        "updated": 1234567890,
                        "active": True
                    }
                }
                for i in range(5000)  # ~5000 items
            ]
        }
        large_json = json.dumps(large_data)
        fenced = f"```json\n{large_json}\n```"

        # Should parse without error
        result = parse_llm_response(fenced)
        assert len(result["items"]) == 5000
        assert result["items"][0]["id"] == 0

    def test_large_nested_structure(self):
        """Test deeply nested JSON structure."""
        # Create a deeply nested structure
        data = {"level": 0}
        current = data
        for i in range(100):  # 100 levels deep
            current["nested"] = {"level": i + 1}
            current = current["nested"]
        current["value"] = "deep"

        large_json = json.dumps(data)
        fenced = f"```json\n{large_json}\n```"

        result = parse_llm_response(fenced)
        assert result["level"] == 0

    def test_large_array_with_unicode(self):
        """Test large array with many unicode entries."""
        data = {
            "unicode_items": [
                f"item-{i}-你好-😊-مرحبا"
                for i in range(1000)
            ]
        }
        large_json = json.dumps(data)
        fenced = f"```json\n{large_json}\n```"

        result = parse_llm_response(fenced)
        assert len(result["unicode_items"]) == 1000
        assert "你好" in result["unicode_items"][0]

    def test_large_payload_performance_reasonable(self):
        """Test that large payload parsing completes in reasonable time."""
        import time

        # Create a 500KB payload
        large_data = {"data": ["x" * 1000 for _ in range(500)]}
        large_json = json.dumps(large_data)
        fenced = f"```json\n{large_json}\n```"

        start = time.perf_counter()
        result = parse_llm_response(fenced)
        elapsed = time.perf_counter() - start

        assert result is not None
        # Should complete in less than 1 second even for large payload
        assert elapsed < 1.0, f"Large payload took {elapsed:.3f}s (too slow)"

    def test_malformed_large_payload_clear_error(self):
        """Test that malformed large payload gives clear error."""
        # Create a large malformed JSON
        malformed = '{"data": [' + ', '.join(['"x"' * 100 for _ in range(1000)]) + '}'
        fenced = f"```json\n{malformed}\n```"

        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(fenced)
        # Error message should include snippet
        assert "Failed to parse JSON" in str(exc_info.value)
        # Raw response should be available
        assert exc_info.value.raw_response is not None


# ============================================================================
# Additional Fence Edge Cases
# ============================================================================

class TestAdditionalFenceEdgeCases:
    """Test additional edge cases around fence handling."""

    def test_fence_with_extra_whitespace_variations(self):
        """Test fence with various whitespace patterns."""
        content = '{"key": "value"}'

        # Whitespace before opening fence
        result = strip_markdown_fences(f"   ```json\n{content}\n```")
        assert result == content

        # Whitespace after opening fence (but before newline)
        fenced = f"```json   \n{content}\n```"
        result = strip_markdown_fences(fenced)
        assert "key" in result

    def test_fence_case_sensitivity(self):
        """Test that fence language specifiers are case-sensitive."""
        content = '{"key": "value"}'

        # Lowercase (standard)
        fenced = f"```json\n{content}\n```"
        result = strip_markdown_fences(fenced)
        assert result == content

        # Uppercase (non-standard but should still strip)
        fenced = f"```JSON\n{content}\n```"
        result = strip_markdown_fences(fenced)
        assert result == content

        # Mixed case
        fenced = f"```Json\n{content}\n```"
        result = strip_markdown_fences(fenced)
        assert result == content

    def test_fence_with_language_dialect(self):
        """Test fence with language dialect specifier."""
        content = '{"key": "value"}'

        # With dialect
        fenced = f"```json/python\n{content}\n```"
        result = strip_markdown_fences(fenced)
        assert "key" in result

    def test_single_backtick_no_strip(self):
        """Test that single backtick is not treated as fence."""
        content = '{"key": "value"}'
        fenced = f"`json\n{content}\n`"
        result = strip_markdown_fences(fenced)
        # Should NOT strip (only 1 backtick)
        assert result.startswith("`json")

    def test_double_backtick_no_strip(self):
        """Test that double backtick is not treated as fence."""
        content = '{"key": "value"}'
        fenced = f"``json\n{content}\n``"
        result = strip_markdown_fences(fenced)
        # Should NOT strip (only 2 backticks)
        assert result.startswith("``json")

    def test_fence_with_trailing_spaces_on_closing(self):
        """Test fence with spaces after closing marker."""
        content = '{"key": "value"}'
        fenced = f"```json\n{content}\n```   "
        result = strip_markdown_fences(fenced)
        # rsplit should handle trailing spaces
        assert result == content

    def test_multiple_fences_only_first_stripped(self):
        """Test content with fence-like opening that isn't actually a fence."""
        # This tests a case where content contains what looks like a fence
        content = '{"text": "This is not a fence: ```json"}'
        fenced = f"```\n{content}\n```"
        result = strip_markdown_fences(fenced)
        # Should strip the outer fences but preserve inner one
        assert "```json" in result

    def test_incomplete_fence_only_opening(self):
        """Test string with only opening fence, no closing."""
        content = '{"key": "value"}'
        fenced = f"```json\n{content}"
        result = strip_markdown_fences(fenced)
        # Should strip opening fence and return rest
        assert result == content

    def test_parse_llm_response_preserves_raw_on_error(self):
        """Test that raw response is preserved in ParseLLMError."""
        malformed = "```json\n{bad}\n```"
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed)
        assert exc_info.value.raw_response == malformed


# ============================================================================
# Mixed Format Edge Cases
# ============================================================================

class TestMixedFormatEdgeCases:
    """Test edge cases mixing different formats."""

    def test_json_with_html_content(self):
        """Test JSON containing HTML strings."""
        content = r'{"html": "<div class=\"test\">Hello</div>"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["html"] == '<div class="test">Hello</div>'

    def test_json_with_javascript_content(self):
        """Test JSON containing JavaScript code strings."""
        content = r'{"code": "const x = () => { return \"hello\" };"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert "=>" in result["code"]

    def test_json_with_base64_content(self):
        """Test JSON containing base64 encoded data."""
        import base64
        original = b"Hello, world!"
        encoded = base64.b64encode(original).decode('ascii')
        content = f'{{"data": "{encoded}"}}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        decoded = base64.b64decode(result["data"])
        assert decoded == original

    def test_json_with_url_strings(self):
        """Test JSON containing URL strings."""
        content = r'{"url": "https://example.com/path?query=value&foo=bar"}'
        fenced = f"```json\n{content}\n```"
        result = parse_llm_response(fenced)
        assert result["url"] == "https://example.com/path?query=value&foo=bar"
