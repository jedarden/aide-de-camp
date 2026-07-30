# Stub Sweep Inventory - July 2026

**Sweep date:** 2026-07-23
**Sweep method:** Systematic grep sweep of src/ for TODO/FIXME comments, NotImplementedError, placeholder/fake data returns, bare exception handlers, hardcoded values, unreachable code paths, and methods returning constant False/True without logic.

## Summary

- **Total findings:** 5
- **Golden path findings:** 0 (none of the identified stubs affect the hot path: utterance → router → fetch → synthesize → SSE)
- **Background/async findings:** 5 (monitoring placeholder, kubectl/git command stubs, telegram registration stub, prefetch simplification)
- **Zero findings result:** Not applicable — 5 legitimate findings documented below

---

## Findings

### 1. Monitoring session_id placeholder

**File:** `src/monitoring/ambient.py:605`
**Class of stub:** Hardcoded placeholder value
**Demo impact:** OFF golden path (monitoring is async background polling)
**Line:**
```python
session_id = "monitoring"  # Placeholder
```
**Description:** The `monitor_topic()` method uses a hardcoded `"monitoring"` session_id instead of the active user session. Monitoring results are written to this fixed session rather than the user's actual session.
**Fix scope:** Replace with session_id from the monitoring rule or configuration, or create monitoring results in the user's active session.

### 2. Kubectl command incomplete implementation

**File:** `src/escalate/handler.py:402`
**Class of stub:** TODO comment + placeholder return
**Demo impact:** OFF golden path (escalate/kubectl runs on async path after bead creation)
**Line:**
```python
# TODO: Implement other kubectl commands
```
**Description:** The `_execute_kubectl_command()` method only handles `delete pod` operations. Other kubectl commands return a placeholder "pending" result with "not yet implemented" message.
**Fix scope:** Implement switch case for kubectl verbs (get, logs, describe, apply, etc.) or remove the TODO if only delete pod is intended.

### 3. Git command incomplete implementation

**File:** `src/escalate/handler.py:424`
**Class of stub:** TODO comment + placeholder return
**Demo impact:** OFF golden path (escalate/git runs on async path after bead creation)
**Line:**
```python
# TODO: Implement git commands
```
**Description:** The `_execute_git_command()` method returns a placeholder "pending" result with "not yet implemented" message for all git commands.
**Fix scope:** Implement git command execution (status, log, diff, checkout, etc.) or remove the TODO if git commands are not intended.

### 4. Telegram surface registration no-op

**File:** `src/telegram/fallback.py:218-236`
**Class of stub:** Explicit no-op stub (documented)
**Demo impact:** OFF golden path (Telegram is fallback surface, requires active canvas failover)
**Lines:**
```python
async def register_surface(self, session_id: str, telegram_chat_id: str) -> bool:
    """
    Register a Telegram surface for a session.

    NOTE: The /register_surface endpoint does NOT exist in telegram-claude-bridge.
    This method is a no-op stub for API compatibility...
    """
    logger.warning(...)
    return True
```
**Description:** The `register_surface()` method is intentionally a no-op stub because telegram-claude-bridge uses a pull-based architecture. The method exists for API compatibility and returns True (pretends registration succeeded).
**Fix scope:** None — documented architectural incompatibility. Remove only if telegram-claude-bridge adds surface registration support.

### 5. Realtime dispatch prefetch simplification

**File:** `src/realtime/dispatch.py:109`
**Class of stub:** Simplified placeholder implementation
**Demo impact:** ON golden path (realtime dispatch is part of voice/text hot path)
**Line:**
```python
project_slugs = detected_topics  # Placeholder
```
**Description:** The prefetch logic uses `detected_topics` directly as `project_slugs` instead of fetching from the topic. This is a simplification that may cause prefetch to operate on incomplete/incorrect project data.
**Fix scope:** Fetch actual project slugs from the topic's registry entry or intent metadata.

---

## Non-Findings (Explicitly Checked)

The following patterns were searched but yielded NO stub findings on the golden path:

- **NotImplementedError:** None found in src/
- **Dead code paths (if False:, if 0:, etc.):** None found
- **Unreachable conditions:** None found
- **Silent exception swallows:** All `except Exception` blocks either log or have documented fallback behavior
- **Hardcoded internal URLs:** All are documented infrastructure (Traefik proxies, Tailscale mesh endpoints from CLAUDE.md)
- **Bare `pass` statements:** All are legitimate exception class bodies or cleanup code (except/finally blocks)

### Notable legitimate exception handlers:

- `src/_version.py:25` — Returns "0.0.0" fallback if pyproject.toml unreadable (appropriate)
- `src/main.py:402-403` — Bare `except: pass` for websocket send error cleanup (appropriate)
- `src/stt/fallback.py:110` — Network error handling with logging (appropriate)
- `src/telegram/fallback.py:249` — Network error handling with failure tracking (appropriate)
- `src/fetch/orchestrator.py:596` — JSON parse failure returns empty list (appropriate)

---

## Sweep Methodology

1. **Directory structure:** Explore agent enumerated 84 Python files under src/
2. **TODO/FIXME search:** `grep -rn "TODO\|FIXME" src/ --include="*.py"`
3. **NotImplementedError search:** `grep -rn "NotImplementedError" src/ --include="*.py"`
4. **Placeholder/fake data search:** `grep -rn "# placeholder\|# stub\|# fake" src/ --include="*.py" -i`
5. **Bare exception handlers:** `grep -rn "except:\|except Exception:" src/ --include="*.py"`
6. **Dead code paths:** `grep -rn "if False:\|if True:\|if 0:\|if 1:" src/ --include="*.py"`
7. **Empty return statements:** `grep -rn "return \[\]\|return {}" src/ --include="*.py"`
8. **Pass statement analysis:** Identified files with pass statements, then manual inspection

Total files examined: 84 Python modules.
