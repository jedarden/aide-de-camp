#!/usr/bin/env python3
"""Test Synthesize Strand: fetch result → structured {data, summary, urgency}."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the project root is in the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.synthesize.strand import (
    SynthesizeStrand,
    SynthesizeRequest,
    SynthesizeResult,
    Urgency,
    get_synthesize_strand,
    synthesize_intent,
)
from src.fetch.commands import FetchResult, FetchCoverage, SourceResult, FetchSource, IntentType


async def test_synthesize_request_creation():
    """Test synthesize request creation."""
    print("Testing Synthesize Request creation...")

    request = SynthesizeRequest(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        utterance="Test utterance",
        project_slug="test-project",
        urgency="normal",
    )

    assert request.intent_id == "test-intent"
    assert request.intent_type == IntentType.STATUS
    assert request.project_slug == "test-project"

    print("  ✅ Synthesize Request creation works")
    return True


async def test_synthesize_result_creation():
    """Test synthesize result creation."""
    print("Testing Synthesize Result creation...")

    result = SynthesizeResult(
        intent_id="test-intent",
        data={"type": "pod-status", "items": []},
        summary="All systems operational",
        urgency=Urgency.NORMAL,
    )

    assert result.intent_id == "test-intent"
    assert result.summary == "All systems operational"
    assert result.urgency == Urgency.NORMAL

    print("  ✅ Synthesize Result creation works")
    return True


async def test_urgency_enum():
    """Test Urgency enum."""
    print("Testing Urgency enum...")

    assert Urgency.CRITICAL.value == "critical"
    assert Urgency.HIGH.value == "high"
    assert Urgency.NORMAL.value == "normal"
    assert Urgency.LOW.value == "low"

    # Test string to enum conversion
    urgency = Urgency("normal")
    assert urgency == Urgency.NORMAL

    print("  ✅ Urgency enum works")
    return True


async def test_load_prompt():
    """Test prompt loading from disk."""
    print("Testing prompt loading...")

    strand = SynthesizeStrand()
    prompt = strand._load_prompt()

    assert "Synthesize Strand" in prompt
    assert "## Input" in prompt
    assert "## Output Format" in prompt

    print("  ✅ Prompt loading works")
    return True


async def test_build_user_message():
    """Test user message building."""
    print("Testing user message building...")

    strand = SynthesizeStrand()

    # Create mock fetch result
    fetch_result = FetchResult(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        sources={
            FetchSource.KUBECTL_PODS: SourceResult(
                source=FetchSource.KUBECTL_PODS,
                status="success",
                data={"pods": [{"name": "pod-1", "phase": "Running"}]},
                duration_ms=100,
            ),
        },
        coverage=FetchCoverage(
            total_sources=1,
            succeeded=[FetchSource.KUBECTL_PODS],
            timed_out=[],
            failed=[],
            skipped=[],
        ),
        total_duration_ms=100,
    )

    request = SynthesizeRequest(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        utterance="Check the pods",
        project_slug="test-project",
        fetched_context=fetch_result,
        urgency="normal",
    )

    user_message = strand._build_user_message(request)

    assert "## Intent Specification" in user_message
    assert "Intent Type: status" in user_message
    assert "Project: test-project" in user_message
    assert "Check the pods" in user_message
    assert "## Fetched Context" in user_message
    assert "kubectl_pods" in user_message

    print("  ✅ User message building works")
    return True


async def test_synthesize_with_mock_llm():
    """Test synthesize with mocked LLM response."""
    print("Testing synthesize with mocked LLM...")

    strand = SynthesizeStrand()

    # Create mock fetch result
    fetch_result = FetchResult(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        sources={
            FetchSource.KUBECTL_PODS: SourceResult(
                source=FetchSource.KUBECTL_PODS,
                status="success",
                data={"pods": [{"name": "pod-1", "phase": "Running"}]},
                duration_ms=100,
            ),
        },
        coverage=FetchCoverage(
            total_sources=1,
            succeeded=[FetchSource.KUBECTL_PODS],
            timed_out=[],
            failed=[],
            skipped=[],
        ),
        total_duration_ms=100,
    )

    request = SynthesizeRequest(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        utterance="Check the pods",
        project_slug="test-project",
        fetched_context=fetch_result,
        urgency="normal",
    )

    # Mock LLM response
    mock_llm = AsyncMock()
    mock_llm.call_simple.return_value = '''{
  "data": {
    "type": "pod-status",
    "items": [
      {
        "name": "pod-1",
        "status": "Running"
      }
    ],
    "summary_fields": {
      "total": 1,
      "running": 1
    }
  },
  "summary": "1 pod is running. All systems operational.",
  "urgency": "normal"
}'''

    strand._zai_client = mock_llm

    result = await strand.synthesize(request)

    assert result.intent_id == "test-intent"
    assert result.summary == "1 pod is running. All systems operational."
    assert result.urgency == Urgency.NORMAL
    assert result.data["type"] == "pod-status"
    assert len(result.data["items"]) == 1

    print("  ✅ Synthesize with mocked LLM works")
    return True


async def test_synthesize_with_json_parse_error():
    """Test synthesize handles JSON parse errors gracefully."""
    print("Testing synthesize with JSON parse error...")

    strand = SynthesizeStrand()

    request = SynthesizeRequest(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        utterance="Test",
    )

    # Mock LLM response with invalid JSON
    mock_llm = AsyncMock()
    mock_llm.call_simple.return_value = "This is not valid JSON"

    strand._zai_client = mock_llm

    result = await strand.synthesize(request)

    # Should return fallback result
    assert result.intent_id == "test-intent"
    assert "error" in result.data
    assert result.urgency == Urgency.NORMAL

    print("  ✅ Synthesize handles JSON parse errors")
    return True


async def test_synthesize_with_coverage_and_caveats():
    """Test synthesize includes coverage and caveats from fetch result."""
    print("Testing synthesize with coverage and caveats...")

    strand = SynthesizeStrand()

    # Create fetch result with caveats
    fetch_result = FetchResult(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        sources={},
        coverage=FetchCoverage(
            total_sources=2,
            succeeded=[FetchSource.KUBECTL_PODS],
            timed_out=[FetchSource.ARGOCD_APP],
            failed=[],
            skipped=[],
        ),
        total_duration_ms=200,
        caveats=["ArgoCD API timed out"],
    )

    request = SynthesizeRequest(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        utterance="Test",
        fetched_context=fetch_result,
    )

    # Mock LLM response
    mock_llm = AsyncMock()
    mock_llm.call_simple.return_value = '''{
  "data": {},
  "summary": "Test summary",
  "urgency": "normal"
}'''

    strand._zai_client = mock_llm

    result = await strand.synthesize(request)

    assert result.coverage is not None
    assert result.coverage["total_sources"] == 2
    assert result.coverage["succeeded"] == 1
    assert result.coverage["timed_out"] == 1
    assert result.caveats == ["ArgoCD API timed out"]

    print("  ✅ Synthesize includes coverage and caveats")
    return True


async def test_global_singleton():
    """Test global synthesize strand singleton."""
    print("Testing global synthesize strand singleton...")

    strand1 = get_synthesize_strand()
    strand2 = get_synthesize_strand()

    assert strand1 is strand2

    print("  ✅ Global singleton works")
    return True


async def test_convenience_function():
    """Test synthesize_intent convenience function."""
    print("Testing synthesize_intent convenience function...")

    request = SynthesizeRequest(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        utterance="Test",
    )

    # Mock strand
    mock_strand = AsyncMock()
    mock_result = SynthesizeResult(
        intent_id="test-intent",
        data={},
        summary="Test",
        urgency=Urgency.NORMAL,
    )
    mock_strand.synthesize.return_value = mock_result

    with patch("src.synthesize.strand.get_synthesize_strand", return_value=mock_strand):
        result = await synthesize_intent(request)

    assert result.intent_id == "test-intent"
    mock_strand.synthesize.assert_called_once_with(request)

    print("  ✅ Convenience function works")
    return True


async def main():
    """Run all synthesize strand tests."""
    print("="*50)
    print("SYNTHESIZE STRAND TEST SUITE")
    print("="*50)

    tests = [
        test_synthesize_request_creation,
        test_synthesize_result_creation,
        test_urgency_enum,
        test_load_prompt,
        test_build_user_message,
        test_synthesize_with_mock_llm,
        test_synthesize_with_json_parse_error,
        test_synthesize_with_coverage_and_caveats,
        test_global_singleton,
        test_convenience_function,
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "="*50)
    if all(results):
        print("✅ ALL TESTS PASSED")
        print("="*50)
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*50)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
