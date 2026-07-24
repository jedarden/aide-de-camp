"""
ZAI Response Parser - Centralized utility for parsing LLM responses.

Handles:
1. ZAI proxy response unwrapping (removes outer "result" field)
2. Markdown code fence stripping (```json, ```, etc.)
3. JSON parsing with clear error messages
4. Graceful fallback for malformed responses

This utility is used across:
- Intent Router (src/intent/router.py)
- Synthesize Strand (src/synthesize/strand.py)
- Self-Modification Agent (src/agents/self_modification.py)
- Any other LLM interaction points

## Error Handling Patterns

When ParseLLMError is raised, choose recovery strategy based on context:

### Corrective Retry Pattern (Router-style)
Use when:
- LLM call is early in pipeline (cheap to retry)
- Failure cascades to downstream operations
- Retrying doesn't require re-running expensive operations

Example: Intent router retries once because malformed response affects all downstream processing.

See: src/intent/router.py classify_utterance()

### Fallback Result Pattern (Synthesize-style)
Use when:
- LLM call is AFTER expensive operations (fetch, DB queries, etc.)
- Data already obtained should not be discarded
- User should see partial results in degraded-state UX

Example: Synthesize strand returns fallback result because fetch operations already completed.

See: src/synthesize/strand.py synthesize()

### Documentation
See: docs/error-handling-standardization.md for complete pattern comparison and examples.
"""

import json
from logging import getLogger
from typing import Any, Dict, Optional


logger = getLogger(__name__)


class ParseLLMError(Exception):
    """
    Raised when LLM response parsing fails.

    Attributes:
        message: Human-readable error message
        raw_response: The raw LLM response text that failed parsing (preserved for debugging)

    The raw_response attribute is critical for debugging and degraded-state UX.
    Always pass it when raising ParseLLMError so error handlers can include
    response snippets in error events and logs.
    """

    def __init__(self, message: str, raw_response: Optional[str] = None):
        self.raw_response = raw_response
        super().__init__(message)


def strip_markdown_fences(raw: str) -> str:
    """
    Strip markdown code fences from a response using fast manual string splitting.

    Handles:
    - ```json ... ```
    - ``` ... ```
    - ` ... ` (rare but possible)

    Performance: Uses manual string splitting which is 7-179x faster than regex-based
    alternatives (see benchmarking in notes/adc-3e5gg.md). This is the optimal approach
    for hot-path LLM response parsing.

    Args:
        raw: Raw response text that may contain markdown fences

    Returns:
        Text with markdown fences removed

    Examples:
        >>> strip_markdown_fences('```json\\n{"a": 1}\\n```')
        '{"a": 1}'
        >>> strip_markdown_fences('```\\n{"a": 1}\\n```')
        '{"a": 1}'
        >>> strip_markdown_fences('{"a": 1}')
        '{"a": 1}'
    """
    # Early return for empty/whitespace strings
    if not raw or not raw.strip():
        return raw

    # Optimized: single strip at start, avoid redundant operations
    text = raw.strip()

    # Fast manual fence stripping (7-179x faster than regex)
    # Pattern: ```optional_lang\n content \n```
    if text.startswith("```"):
        # Split after first newline to skip opening fence line
        text = text.split("\n", 1)[-1]
        # Remove closing fence and any trailing whitespace
        text = text.rsplit("```", 1)[0].strip()

    return text


def unwrap_zai_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unwrap ZAI proxy response structure.

    The ZAI proxy wraps Anthropic responses under a "result" key.
    This function extracts the inner payload if present.

    Args:
        response_data: Raw response dict from ZAI proxy

    Returns:
        Unwrapped response dict (or original if no wrapping detected)

    Examples:
        >>> unwrap_zai_response({"result": {"content": [...]}})
        {"content": [...]}
        >>> unwrap_zai_response({"content": [...]})
        {"content": [...]}
    """
    # Check if response has "result" wrapper (ZAI proxy pattern)
    if "result" in response_data and isinstance(response_data["result"], dict):
        inner = response_data["result"]
        logger.debug("Unwrapped ZAI proxy response (removed 'result' field)")
        return inner

    return response_data


def extract_text_from_response(payload: Dict[str, Any]) -> str:
    """
    Extract text content from an Anthropic-style response payload.

    Args:
        payload: Response payload with "content" array

    Returns:
        Extracted text content

    Raises:
        ParseLLMError: If content cannot be extracted
    """
    content = payload.get("content", [])

    if content and isinstance(content, list) and len(content) > 0:
        text = content[0].get("text", "")
        if text:
            return text

    # Fallback: try to stringify the content
    logger.warning(f"Could not extract text from content array, using fallback")
    return str(content)


def parse_llm_response(
    raw_text: str,
    *,
    strip_fences: bool = True,
    expect_json: bool = True,
) -> Any:
    """
    Parse an LLM text response, optionally stripping fences and parsing JSON.

    This is the main entry point for parsing LLM responses across the codebase.
    It handles the common pattern of:
    1. Stripping markdown code fences (```json ... ```)
    2. Parsing JSON (when expect_json=True)
    3. Providing clear error messages

    Performance: Optimized with fast manual fence stripping (7-179x faster than
    regex) and early returns on empty inputs. Operations are sequential but efficient.

    Args:
        raw_text: Raw response text from LLM
        strip_fences: Whether to strip markdown code fences (default: True)
        expect_json: Whether to parse as JSON (default: True)

    Returns:
        Parsed JSON object if expect_json=True, otherwise cleaned text

    Raises:
        ParseLLMError: If parsing fails

    Examples:
        >>> parse_llm_response('```json\\n{"a": 1}\\n```')
        {'a': 1}
        >>> parse_llm_response('```json\\n{"a": 1}\\n```', expect_json=False)
        '{"a": 1}'
    """
    # Early return for empty input
    if not raw_text or not raw_text.strip():
        if expect_json:
            raise ParseLLMError(
                "Empty response provided",
                raw_response=raw_text,
            )
        return raw_text

    try:
        # Step 1: Strip markdown fences if present
        if strip_fences:
            text = strip_markdown_fences(raw_text)
        else:
            text = raw_text.strip()

        # Step 2: Parse JSON if expected
        if expect_json:
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                # Provide helpful error message with snippet
                snippet = text[:200] if text else "(empty)"
                raise ParseLLMError(
                    f"Failed to parse JSON: {e}\nResponse snippet: {snippet}...",
                    raw_response=raw_text,
                ) from e

        return text

    except ParseLLMError:
        # Re-raise ParseLLMError without wrapping
        raise
    except Exception as e:
        raise ParseLLMError(
            f"Unexpected error parsing response: {e}",
            raw_response=raw_text,
        ) from e


def parse_zai_proxy_response(
    response_dict: dict,
    *,
    extract_text: bool = True,
    strip_fences: bool = True,
    expect_json: bool = True,
) -> Any:
    """
    Parse a complete ZAI proxy response from HTTP.

    This handles the full flow:
    1. Unwrap ZAI proxy's "result" field
    2. Extract text from Anthropic content array
    3. Strip markdown fences
    4. Parse JSON if expected

    Args:
        response_dict: Raw response dict from httpx.Response.json()
        extract_text: Whether to extract text from content array (default: True)
        strip_fences: Whether to strip markdown fences (default: True)
        expect_json: Whether to parse as JSON (default: True)

    Returns:
        Parsed JSON object or text depending on expect_json

    Raises:
        ParseLLMError: If parsing fails

    Examples:
        >>> response = {"result": {"content": [{"text": '```json\\n{"a": 1}\\n```'}]}}
        >>> parse_zai_proxy_response(response)
        {'a': 1}
    """
    try:
        # Step 1: Unwrap ZAI proxy response
        unwrapped = unwrap_zai_response(response_dict)

        # Step 2: Extract text from content structure
        if extract_text:
            text = extract_text_from_response(unwrapped)
        else:
            # Return the unwrapped payload as-is
            return unwrapped

        # Step 3 & 4: Strip fences and parse JSON using the main parser
        return parse_llm_response(
            text,
            strip_fences=strip_fences,
            expect_json=expect_json,
        )

    except ParseLLMError:
        raise
    except Exception as e:
        raise ParseLLMError(
            f"Failed to parse ZAI proxy response: {e}",
            raw_response=str(response_dict)[:500],
        ) from e
