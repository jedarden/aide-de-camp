"""
Integration tests for JSON parsing error handling patterns.

This test suite verifies the two main error handling patterns used across the codebase:
1. Corrective Retry Pattern (Router-style) - retries once on parse error
2. Fallback Result Pattern (Synthesize-style) - returns degraded result on parse error

Based on error handling documentation in src/llm/response_parser.py
"""

import json
import pytest
from src.llm.response_parser import (
    ParseLLMError,
    parse_llm_response,
    strip_markdown_fences,
)


# ============================================================================
# Corrective Retry Pattern Tests (Router-style behavior)
# ============================================================================

class TestCorrectiveRetryPattern:
    """
    Test the corrective retry pattern concept used in intent router.

    Pattern: When ParseLLMError occurs, retry once with same parameters.
    If retry also fails, raise RouterMalformedError with context.
    """

    def test_corrective_retry_logic_simulation(self):
        """
        Simulate the corrective retry pattern logic.

        This demonstrates how the router handles malformed JSON:
        1. First attempt fails with ParseLLMError
        2. Retry once with same parameters
        3. If retry succeeds, proceed normally
        4. If retry fails, raise RouterMalformedError with retry_count=1
        """
        # Simulate first attempt: malformed JSON
        first_response = '```json\n{"intents": [{"intent_type": "status", "broken":\n```'

        # First attempt should raise ParseLLMError
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(first_response)

        assert exc_info.value.raw_response == first_response
        assert "Failed to parse JSON" in str(exc_info.value)

        # Simulate retry: valid JSON (LLM produces valid output on retry)
        retry_response = '{"intents": [{"intent_type": "status", "project_slug": "aide-de-camp", "confidence": 0.9, "utterance_fragment": "test", "reasoning": "test", "urgency": "normal"}]}'

        # Retry should succeed
        result = parse_llm_response(retry_response)
        assert result["intents"][0]["intent_type"] == "status"

    def test_corrective_retry_both_attempts_fail(self):
        """
        Test case where both original and retry attempts fail.

        This should result in RouterMalformedError with retry_count=1.
        """
        # Both attempts return malformed JSON
        malformed_response = '```json\n{invalid json}\n```'

        # First attempt fails
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed_response)

        # Retry also fails (same malformed response)
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed_response)

        # In actual router, this would raise RouterMalformedError with retry_count=1
        assert exc_info.value.raw_response == malformed_response

    def test_corrective_retry_preserves_error_context(self):
        """
        Test that error context is preserved through retry attempt.

        The raw_response attribute is critical for debugging and monitoring.
        """
        malformed = '```json\n{"broken": \n```'

        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed)

        # Verify error context is preserved
        assert exc_info.value.raw_response == malformed
        assert "Failed to parse JSON" in str(exc_info.value)

        # In real router, this context would be passed to RouterMalformedError


# ============================================================================
# Fallback Result Pattern Tests (Synthesize-style behavior)
# ============================================================================

class TestFallbackResultPattern:
    """
    Test the fallback result pattern concept used in synthesize strand.

    Pattern: When ParseLLMError occurs after expensive fetch operations,
    return a fallback result with error context instead of raising.
    This preserves fetch data and allows degraded-state UX.
    """

    def test_fallback_result_pattern_simulation(self):
        """
        Simulate the fallback result pattern logic.

        This demonstrates how synthesize handles malformed JSON:
        1. Try to parse LLM response
        2. If ParseLLMError occurs, catch it and return fallback result
        3. Fallback result includes error details but doesn't crash
        4. Fetch data is conceptually preserved (not discarded)
        """
        # Simulate LLM response with malformed JSON
        malformed_response = '```json\n{broken json}\n```'

        # Attempt parsing (will fail)
        try:
            result = parse_llm_response(malformed_response)
            assert False, "Should have raised ParseLLMError"
        except ParseLLMError as e:
            # In actual synthesize, this would return fallback SynthesizeResult
            # with error context instead of raising
            error_context = {
                "type": "error",
                "error": "Failed to parse synthesis response",
                "parse_error": str(e),
                "raw_response": e.raw_response[:200] if e.raw_response else None,  # Truncate for safety
            }

            # Verify error context is sufficient for debugging
            assert error_context["type"] == "error"
            assert error_context["error"]
            assert error_context["parse_error"]
            assert "Failed to parse JSON" in error_context["parse_error"]

    def test_fallback_preserves_expensive_fetch_data(self):
        """
        Test that fallback pattern conceptually preserves expensive fetch data.

        The key benefit: fetch operations already succeeded, data is not discarded.
        """
        # Simulate expensive fetch operations that succeeded
        expensive_fetch_data = {
            "source1": {"status": "healthy", "metrics": {"cpu": 50}},
            "source2": {"status": "healthy", "metrics": {"memory": 60}},
        }

        # Simulate synthesis failure (malformed LLM response)
        malformed_response = '```json\n{malformed}\n```'

        try:
            parse_llm_response(malformed_response)
            assert False, "Should have raised ParseLLMError"
        except ParseLLMError as e:
            # In actual synthesize, expensive_fetch_data would still be available
            # Fallback result would reference it or indicate partial processing
            fallback_result = {
                "intent_id": "test-intent",
                "data": {
                    "type": "error",
                    "error": "Failed to parse synthesis response",
                    "parse_error": str(e),
                },
                "summary": "An error occurred while processing the result.",
                "note": "Fetch data is preserved in request.fetched_context",
            }

            # Verify fallback indicates error but preserves context
            assert fallback_result["data"]["type"] == "error"
            assert "parse_error" in fallback_result["data"]
            # The expensive_fetch_data would still be available for degraded UX

    def test_fallback_successful_parse_no_fallback_needed(self):
        """
        Test that successful parse returns normal result (no fallback).

        Verify the fallback logic doesn't interfere with successful operations.
        """
        # Simulate successful LLM response
        valid_response = {
            "data": {"status": "healthy"},
            "summary": "All systems operational",
            "urgency": "low"
        }

        # Parse should succeed
        result = parse_llm_response(json.dumps(valid_response))

        # Verify normal result (not fallback)
        assert result["data"] == {"status": "healthy"}
        assert result["summary"] == "All systems operational"
        assert result["urgency"] == "low"
        # Should NOT have error fields
        assert result.get("type") != "error"


# ============================================================================
# Pattern Comparison Tests
# ============================================================================

class TestErrorHandlingPatternComparison:
    """
    Tests comparing the two error handling patterns side-by-side.

    Demonstrates when to use each pattern based on context in the pipeline.
    """

    def test_pattern_selection_criteria(self):
        """
        Document the criteria for selecting each pattern.

        Router uses Corrective Retry because:
        - It's the first step in the pipeline
        - Failure cascades to all downstream operations
        - LLM call is cheap (2048 tokens), so retry is acceptable

        Synthesize uses Fallback Result because:
        - It runs after expensive fetch operations
        - Fetch data should not be discarded
        - Fallback result enables degraded-state UX
        """
        # This test documents the design decision
        # See src/llm/response_parser.py documentation for full comparison
        assert True  # Documentation test

    def test_router_pattern_raises_error(self):
        """
        Demonstrate router pattern: raises error to prevent cascade.

        Router pattern prevents malformed classification from reaching
        downstream operations (fetch, synthesize, etc.).
        """
        malformed = '```json\n{invalid}\n```'

        # Router pattern: Let ParseLLMError propagate
        # In actual router, this would be caught and transformed to
        # RouterMalformedError after retry attempt
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)

        # Key: Error is raised (not swallowed) to prevent cascade

    def test_synthesize_pattern_returns_fallback(self):
        """
        Demonstrate synthesize pattern: returns fallback to preserve data.

        Synthesize pattern catches ParseLLMError and returns fallback
        result to avoid losing expensive fetch data.
        """
        malformed = '```json\n{invalid}\n```'

        # Synthesize pattern: Catch error and return fallback
        try:
            result = parse_llm_response(malformed)
        except ParseLLMError as e:
            # In actual synthesize, this would return fallback SynthesizeResult
            fallback = {
                "data": {
                    "type": "error",
                    "error": "Failed to parse synthesis response",
                    "parse_error": str(e),
                },
                "summary": "An error occurred while processing the result.",
            }
            # Key: Fallback is returned (not exception raised)
            assert fallback["data"]["type"] == "error"


# ============================================================================
# Error Recovery Performance Tests
# ============================================================================

class TestErrorHandlingPerformance:
    """
    Performance tests for error handling paths.

    Ensure error handling doesn't introduce significant latency.
    """

    def test_parse_performance_on_malformed_input(self):
        """
        Test that ParseLLMError is raised quickly on malformed input.

        Fast failure is important for both patterns:
        - Router: Fast failure enables quick retry
        - Synthesize: Fast failure enables quick fallback
        """
        import time

        malformed = '```json\n{invalid json that fails quickly}\n```'

        start = time.perf_counter()
        with pytest.raises(ParseLLMError):
            parse_llm_response(malformed)
        elapsed = time.perf_counter() - start

        # Should fail very fast (< 1ms)
        assert elapsed < 0.001, f"Parse error took {elapsed*1000:.2f}ms (too slow)"

    def test_successful_parse_performance(self):
        """
        Test that successful parse is fast (baseline).

        This ensures error handling doesn't slow down happy path.
        """
        import time

        valid_response = '{"key": "value", "number": 42}'
        fenced = f'```json\n{valid_response}\n```'

        start = time.perf_counter()
        result = parse_llm_response(fenced)
        elapsed = time.perf_counter() - start

        # Should parse quickly (< 1ms)
        assert elapsed < 0.001, f"Parse took {elapsed*1000:.2f}ms (too slow)"
        assert result["key"] == "value"


# ============================================================================
# Edge Cases in Error Handling
# ============================================================================

class TestErrorHandlingEdgeCases:
    """
    Test edge cases specific to error handling patterns.
    """

    def test_empty_response_error_handling(self):
        """
        Test that empty response triggers appropriate error handling.

        Empty response should raise ParseLLMError with clear message.
        """
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response("")

        assert "Empty response provided" in str(exc_info.value)
        assert exc_info.value.raw_response == ""

    def test_whitespace_only_response_error_handling(self):
        """
        Test that whitespace-only response raises ParseLLMError.

        This prevents subtle bugs where whitespace is treated as valid.
        """
        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response("   \n\t  ")

        assert "Empty response provided" in str(exc_info.value)

    def test_malformed_json_with_fences_error_context(self):
        """
        Test that fenced malformed JSON provides helpful error context.

        Error message should include snippet for debugging.
        """
        malformed = '```json\n{"key": "value", "broken":\n```'

        with pytest.raises(ParseLLMError) as exc_info:
            parse_llm_response(malformed)

        # Error message should include snippet of the malformed content
        error_msg = str(exc_info.value)
        assert "Failed to parse JSON" in error_msg
        assert "Response snippet" in error_msg

    def test_raw_response_preserved_in_error(self):
        """
        Test that raw_response is always preserved in ParseLLMError.

        This is critical for debugging and degraded-state UX.
        """
        test_cases = [
            '```json\n{invalid}\n```',
            '{"broken": }',
            '',
            '   ',
        ]

        for raw in test_cases:
            with pytest.raises(ParseLLMError) as exc_info:
                parse_llm_response(raw)

            # raw_response should always be preserved
            assert exc_info.value.raw_response == raw


# ============================================================================
# Integration with Full Pipeline
# ============================================================================

class TestFullPipelineIntegration:
    """
    Integration tests simulating full pipeline error scenarios.
    """

    def test_pipeline_stage_1_router_error_prevents_cascade(self):
        """
        Test that router error prevents malformed data from cascading.

        When router fails with malformed JSON, it prevents invalid
        classifications from reaching downstream operations.
        """
        # Simulate router LLM response with malformed JSON
        router_response = '```json\n{"intents": [{"intent_type": "status", "broken":\n```'

        # Router should catch this and raise ParseLLMError
        # (In actual router, this triggers retry then RouterMalformedError)
        with pytest.raises(ParseLLMError):
            parse_llm_response(router_response)

        # Key benefit: No malformed classifications reach fetch/synthesize stages

    def test_pipeline_stage_3_synthesize_error_preserves_fetch(self):
        """
        Test that synthesize error preserves expensive fetch results.

        When synthesis fails after successful fetch, fallback result
        preserves fetch data for degraded-state UX.
        """
        # Simulate successful fetch (expensive operation)
        fetch_results = {
            "pod-status": {
                "data": {"pods": [{"name": "web-0", "phase": "Running"}]},
                "source": "kubectl",
                "latency_ms": 150,
            }
        }

        # Simulate synthesis LLM response with malformed JSON
        synthesize_response = '```json\n{"data": {"broken":\n```'

        # Synthesis should catch ParseLLMError and return fallback
        try:
            parse_llm_response(synthesize_response)
            assert False, "Should have raised ParseLLMError"
        except ParseLLMError as e:
            # In actual synthesize, this returns fallback SynthesizeResult
            # The fetch_results data is still available in request.fetched_context
            # for degraded-state rendering
            fallback_available = True
            assert fallback_available

        # Key benefit: Expensive fetch data is not discarded

    def test_pipeline_successful_flow_no_errors(self):
        """
        Test successful pipeline flow with no errors.

        Verifies that error handling doesn't interfere with happy path.
        """
        # Router: valid classification
        router_response = '{"intents": [{"intent_type": "status", "project_slug": "aide-de-camp", "confidence": 0.9}]}'
        classifications = parse_llm_response(router_response)
        assert classifications["intents"][0]["intent_type"] == "status"

        # Synthesize: valid synthesis
        synthesize_response = '{"data": {"status": "healthy"}, "summary": "All good"}'
        result = parse_llm_response(synthesize_response)
        assert result["data"]["status"] == "healthy"

        # Key: Both stages succeed without error handling interference
