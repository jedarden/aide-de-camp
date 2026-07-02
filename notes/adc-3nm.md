# ADC-3nm: ADC_TELEGRAM_BRIDGE_URL Env Var Configuration - Verification

**Date:** 2026-07-02  
**Status:** ✅ COMPLETE (Implemented in commit b85f0f2)

## Acceptance Criteria Verification

### 1. ✅ BRIDGE_URL configurable via ADC_TELEGRAM_BRIDGE_URL env var

**Implementation:** `src/telegram/fallback.py` lines 31-37
```python
DEFAULT_BRIDGE_URL = "http://telegram-claude-bridge:8000"

def __init__(self, bridge_url: str | None = None):
    import os
    self.bridge_url = bridge_url or os.getenv(
        "ADC_TELEGRAM_BRIDGE_URL", self.DEFAULT_BRIDGE_URL
    )
```

### 2. ✅ Unit test covers env var override behavior

**Tests:** `tests/test_telegram_fallback.py`

- `TestTelegramFallbackEnvConfig::test_default_bridge_url` - Verifies default URL when env var not set
- `TestTelegramFallbackEnvConfig::test_env_var_override` - Verifies ADC_TELEGRAM_BRIDGE_URL overrides default
- `TestTelegramFallbackEnvConfig::test_constructor_override` - Verifies constructor param overrides env var
- `TestGlobalFallbackInstance::test_get_telegram_fallback_uses_env_var` - Verifies global function respects env var

**Test Results:** All 8 tests PASS
```
tests/test_telegram_fallback.py::TestTelegramFallbackEnvConfig::test_default_bridge_url PASSED
tests/test_telegram_fallback.py::TestTelegramFallbackEnvConfig::test_env_var_override PASSED
tests/test_telegram_fallback.py::TestTelegramFallbackEnvConfig::test_constructor_override PASSED
tests/test_telegram_fallback.py::TestGlobalFallbackInstance::test_get_telegram_fallback_uses_env_var PASSED
```

### 3. ✅ Default value documented in code comments

**Documentation:** `src/telegram/fallback.py` line 30
```python
# telegram-claude-bridge endpoint (Tailscale mesh)
# Configurable via ADC_TELEGRAM_BRIDGE_URL env var
DEFAULT_BRIDGE_URL = "http://telegram-claude-bridge:8000"
```

## Summary

All acceptance criteria met. The implementation allows configuring the Telegram bridge URL via the `ADC_TELEGRAM_BRIDGE_URL` environment variable with a secure default value. Unit tests verify:
- Default URL behavior when env var is unset
- Env var override functionality  
- Constructor parameter override (for testing flexibility)
- Global instance singleton pattern respects the env var

**Original Implementation:** Commit `b85f0f2` - "feat: add ADC_TELEGRAM_BRIDGE_URL env var configuration"
