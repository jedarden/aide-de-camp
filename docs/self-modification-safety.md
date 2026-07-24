# Self-Modification Safety Model

This document describes the three-layer freeze mechanism, git-based rollback, and break-glass procedures for aide-de-camp's self-modification system.

## Overview

Every self-modification write to `prompts/` or `config/` creates a git commit with a machine-generated message. This provides:
- **One-instruction rollback**: `adc restore-artifacts` reverts the last N self-mod commits
- **Audit trail**: Git history shows exactly what changed and when
- **Freeze protection**: Three independent signals can block all self-modification writes

## Three-Layer Freeze Mechanism

Self-modification writes are blocked when **any** of these three signals are active:

### 1. Environment Variable
```bash
export ADC_SELFMOD_FREEZE=1
```
- **Scope**: Server process only
- **Use case**: Temporary freeze during server restart or debugging
- **Clear by**: `unset ADC_SELFMOD_FREEZE` or restart server without the env var

### 2. Sentinel File
```bash
touch data/FREEZE
```
- **Scope**: Persistent across server restarts
- **Location**: `/home/coding/aide-de-camp/data/FREEZE`
- **Use case**: Manual freeze while investigating issues
- **Clear by**: `rm data/FREEZE` or `adc freeze --toggle`

### 3. CLI Command
```bash
adc freeze --toggle
```
- **Scope**: Toggles the sentinel file
- **Use case**: User-friendly interface to freeze/unfreeze
- **Status check**: `adc freeze` (shows current state and which signal is active)

## Freeze Behavior

When frozen, all self-modification writes are **refused** with a clear error message:

```
RuntimeError: self-mod frozen (env var ADC_SELFMOD_FREEZE=1)
```

The error message indicates which signal is active:
- `env var ADC_SELFMOD_FREEZE=1` — environment variable is set
- `sentinel file /home/coding/aide-de-camp/data/FREEZE` — sentinel file exists

## Auto-Apply Freeze Integration

Background-analysis auto-apply **respects the freeze mechanism**:
- High-confidence proposals are not applied when frozen
- No write occurs, even if confidence exceeds the threshold
- A log entry records the freeze blockage

This ensures auto-applies execute through the same self-modification write path, inheriting:
- Write scope limits (prompts/ and config/ only)
- Git commit per write
- Freeze protection

## Git Commit Convention

Every self-modification write creates a git commit with:

```
auto: self-mod write to <path> [<previous-commit-sha>]
```

Example:
```
auto: self-mod write to prompts/router.md [a1b2c3d]
```

The `<previous-commit-sha>` is the short SHA of the commit we're building on, enabling:
- Precise rollback to the exact pre-modification state
- Clear audit trail of what changed and when
- Easy identification of self-mod commits in `git log`

## Restore Artifacts

The `adc restore-artifacts` command reverts self-modification commits:

```bash
# Show what would be reverted (dry run)
adc restore-artifacts --dry-run

# Revert the last self-mod commit
adc restore-artifacts

# Revert the last 3 self-mod commits
adc restore-artifacts -n 3
```

### How It Works

1. **Clears freeze** (if frozen) — temporarily unfreezes to allow git operations
2. **Finds self-mod commits** — searches git log for `auto: self-mod write to` pattern
3. **Reverts commits** — uses `git revert --no-commit` to undo changes
4. **Creates revert commit** — commits the revert with `adc restore-artifacts: revert N self-mod commit(s)`
5. **Restores freeze** — re-freezes if it was frozen before

### Commit Identification

Self-mod commits are identified by the commit message pattern:
```
auto: self-mod write to ...
```

Only commits matching this pattern are reverted, ensuring manual edits are not affected.

## Break-Glass Caveat

**Important**: The freeze sentinel file and git revert operations are **local filesystem/git operations**.

### Why This Matters

- The `adc` CLI is a thin HTTP client when connecting to a remote server
- From a remote machine, `adc freeze` and `adc restore-artifacts` cannot manipulate the server's local filesystem
- If the server is unresponsive (e.g., bad router prompt breaks routing), you need direct filesystem access

### Break-Glass Procedure

When the server is unponsive and you need to freeze or restore:

1. **SSH into the server host** first:
   ```bash
   ssh <server-host>
   ```

2. **Then run the commands locally**:
   ```bash
   cd /home/coding/aide-de-camp
   ./adc freeze --toggle          # Freeze
   ./adc restore-artifacts -n 1   # Restore
   ```

This bypasses any broken routing or HTTP interface entirely.

## Examples

### Freezing Self-Modification

```bash
# Check current status
./adc freeze
# Output: Status: 🟢 UNFROZEN

# Freeze self-modification
./adc freeze --toggle
# Output: ✓ Self-modification frozen (created data/FREEZE)

# Verify frozen
./adc freeze
# Output: Status: 🔴 FROZEN
#         Reason: sentinel file /home/coding/aide-de-camp/data/FREEZE
```

### Restoring from a Bad Prompt Edit

```bash
# Scenario: A self-mod commit broke the router prompt

# 1. First, freeze to prevent further damage
./adc freeze --toggle

# 2. See what would be reverted
./adc restore-artifacts --dry-run
# Output: Found 1 self-mod commit(s) to revert:
#           1. abc1234 - auto: self-mod write to prompts/router.md [def5678]

# 3. Revert the bad commit
./adc restore-artifacts -n 1
# Output: Successfully reverted 1 self-mod commit(s)
#           Artifacts restored to previous version.

# 4. Restart the server with the restored prompts
# (server automatically hot-reloads from disk)
```

### Environment Variable Freeze

```bash
# Set environment variable before starting server
export ADC_SELFMOD_FREEZE=1
./.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# Or in systemd/supervisor:
Environment="ADC_SELFMOD_FREEZE=1"
```

## Testing

The safety model is fully tested:

```bash
# Run all self-modification tests
.venv/bin/python -m pytest tests/test_self_modification.py -v

# Run specific test classes
.venv/bin/python -m pytest tests/test_self_modification.py::TestFreezeProtection -v
.venv/bin/python -m pytest tests/test_self_modification.py::TestGitCommits -v
.venv/bin/python -m pytest tests/test_self_modification.py::TestRestoreArtifacts -v
.venv/bin/python -m pytest tests/test_self_modification.py::TestBackgroundAnalysisFreezeIntegration -v
```

All 29 tests verify:
- Git commits are created for every write
- Each freeze signal blocks writes with clear errors
- Restore artifacts reverts bad edits
- Background-analysis auto-apply respects freeze

## Architecture

### Self-Modification Write Path

```
User instruction → SelfModificationAgent.process_instruction()
                → Parse instruction (LLM call)
                → Generate update (LLM call)
                → Surface diff to user
                → On approval: apply_diff()
                    → ensure_unfrozen() [RAISES if frozen]
                    → Write artifact to disk
                    → _commit_artifact_write()
                        → git add
                        → git commit (machine-generated message)
                    → Force hot-reload
```

### Freeze Check Points

1. **User-initiated self-mod**: `SelfModificationAgent.apply_diff()` → `ensure_unfrozen()`
2. **Background-analysis auto-apply**: `BackgroundAnalysisProcessor._auto_apply_proposal()` → `check_frozen()`

Both paths refuse writes when frozen, ensuring no bypass exists.

## Implementation Details

### Files

- **Freeze mechanism**: `src/freeze.py`
  - `check_frozen()` — check all three signals
  - `ensure_unfrozen()` — raise RuntimeError if frozen
  - `set_frozen()` — create/remove sentinel file

- **Self-modification agent**: `src/agents/self_modification.py`
  - `_commit_artifact_write()` — git commit per write
  - `apply_diff()` — freeze check → write → commit

- **Background analysis**: `src/feedback/background_analysis.py`
  - `_auto_apply_proposal()` — freeze check before auto-apply

- **CLI commands**: `src/cli/commands.py`
  - `freeze_cmd()` — view/toggle freeze state
  - `restore_artifacts_cmd()` — revert self-mod commits

### Git Utilities

The `src/agents/self_modification.py` module provides structured git subprocess wrappers:
- `run_git_command()` — generic git execution with timeout
- `git_status()`, `git_add()`, `git_commit()` — specific operations
- `git_rev_parse()`, `git_show()` — commit inspection
- `generate_self_mod_commit_message()` — standardized message format

## Summary

The self-modification safety model provides:

1. **Versioning is git** — every write is a commit, rollback is `git revert`
2. **Freeze protection** — three independent signals block writes
3. **Break-glass procedure** — SSH to server, then use CLI commands
4. **Auto-apply integration** — background analysis respects the same write path
5. **Comprehensive testing** — all 29 tests verify the safety guarantees

This ensures self-modification is safe, auditable, and recoverable even when it breaks the very interface used to control it.
