#!/usr/bin/env python3
"""
Validate all test utterances through the test classify endpoint.

This script loads all utterances from the fixtures file and validates
each one through the /test/classify endpoint to ensure they can be
successfully classified.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from logging import getLogger, basicConfig

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.test.helpers import load_test_utterances, get_all_utterances_flat

# Configure logging
basicConfig(level='INFO', format='%(levelname)s: %(message)s')
logger = getLogger(__name__)


async def validate_single_utterance(utterance: dict[str, Any], session_id: str = "test-session") -> dict[str, Any]:
    """
    Validate a single utterance through the test classify endpoint.

    Args:
        utterance: The utterance dictionary from fixtures
        session_id: Session ID for context

    Returns:
        Validation result dictionary
    """
    import httpx

    url = "http://localhost:8000/api/v1/test/classify"

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.post(
                url,
                json={
                    "utterance": utterance["utterance"],
                    "session_id": session_id
                }
            )
            response.raise_for_status()
            data = response.json()

            return {
                "name": utterance.get("name", "unknown"),
                "utterance": utterance["utterance"],
                "success": True,
                "classifications": data.get("classifications", []),
                "message": data.get("message", ""),
                "expected_intent_type": utterance.get("expected_intent_type"),
                "expected_topic_type": utterance.get("expected_topic_type"),
            }

    except Exception as e:
        return {
            "name": utterance.get("name", "unknown"),
            "utterance": utterance["utterance"],
            "success": False,
            "error": str(e),
            "expected_intent_type": utterance.get("expected_intent_type"),
            "expected_topic_type": utterance.get("expected_topic_type"),
        }


async def validate_all_utterances():
    """
    Validate all utterances through the test endpoint.

    Returns summary statistics and detailed results.
    """
    logger.info("Loading test utterances...")
    utterances = get_all_utterances_flat()

    logger.info(f"Found {len(utterances)} utterances to validate")
    logger.info("Testing each utterance through /test/classify endpoint...")

    results = []
    failed = []
    unexpected_results = []

    for utterance in utterances:
        result = await validate_single_utterance(utterance)
        results.append(result)

        if not result["success"]:
            failed.append(result)
            logger.error(f"❌ Failed: {result['name']} - {result.get('error', 'Unknown error')}")
        else:
            # Check if classification matches expected
            classifications = result.get("classifications", [])
            if classifications:
                actual_intent = classifications[0].get("intent_type")
                expected_intent = result.get("expected_intent_type")

                # Skip comparison for edge cases that should fail
                if not utterance.get("should_fail"):
                    if expected_intent and actual_intent != expected_intent:
                        unexpected_results.append({
                            "name": result["name"],
                            "expected": expected_intent,
                            "actual": actual_intent,
                            "utterance": result["utterance"]
                        })
                        logger.warning(f"⚠️  Unexpected classification: {result['name']}")
                        logger.warning(f"    Expected: {expected_intent}, Got: {actual_intent}")
                    else:
                        logger.info(f"✅ Passed: {result['name']}")
                else:
                    logger.info(f"✅ Passed (expected to fail): {result['name']}")
            else:
                logger.warning(f"⚠️  No classifications returned: {result['name']}")

    # Print summary
    total = len(results)
    passed = total - len(failed)

    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    print(f"Total utterances:  {total}")
    print(f"Passed:            {passed}")
    print(f"Failed:            {len(failed)}")
    print(f"Unexpected:        {len(unexpected_results)}")
    print("="*60)

    if failed:
        print(f"\n❌ {len(failed)} utterances failed validation:")
        for result in failed:
            print(f"  - {result['name']}: {result.get('error', 'Unknown error')}")

    if unexpected_results:
        print(f"\n⚠️  {len(unexpected_results)} utterances had unexpected classifications:")
        for result in unexpected_results:
            print(f"  - {result['name']}")
            print(f"    Expected: {result['expected']}, Got: {result['actual']}")
            print(f"    Utterance: {result['utterance'][:80]}...")

    if not failed and not unexpected_results:
        print("\n✅ All utterances validated successfully!")
        return 0
    else:
        print(f"\n❌ Validation completed with {len(failed)} failures and {len(unexpected_results)} unexpected results")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(validate_all_utterances())
    sys.exit(exit_code)