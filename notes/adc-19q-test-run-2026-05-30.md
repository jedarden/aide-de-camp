# Test Run Results for Bead adc-19q

**Date:** 2026-05-30

## Summary

All 14 escalate handler tests passed successfully.

## Test Results

| Test | Status |
|------|--------|
| LLM Request payload serialization | ✅ |
| LLM Response total tokens | ✅ |
| Escalate Request serialization | ✅ |
| Escalate Result serialization | ✅ |
| ZAI Client call | ✅ |
| ZAI Client rate limit handling | ✅ |
| Escalate Handler formulate bead body | ✅ |
| Escalate Handler generate bead title | ✅ |
| Escalate Handler extract bead ID | ✅ |
| Escalate Handler build pending card | ✅ |
| Escalate Handler full flow | ✅ |
| Global singleton functions | ✅ |
| Escalate with real session store | ✅ |
| escalate_intent convenience function | ✅ |
| Escalate Handler bead creation failure | ✅ |

## Context

This test run verifies that the escalate strand (task-profile intent → NEEDLE bead creation) is functioning correctly after previous fixes to subprocess mock patch paths.
