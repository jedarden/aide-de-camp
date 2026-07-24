"""
ADC CLI command implementations.

Each command function handles a specific CLI command and returns an exit code.
"""

import asyncio
import json
import sys
import uuid
from typing import Optional

import httpx

from .config import Config
from . import sse


async def dispatch(
    utterance: str,
    server_url: str,
    session_id: Optional[str],
    stream: bool,
    config: Config,
) -> int:
    """
    Dispatch an utterance to the intent router.

    Sends the utterance to the /dispatch endpoint and optionally streams
    results via SSE to the terminal.

    Args:
        utterance: The user's utterance to dispatch
        server_url: The aide-de-camp server URL
        session_id: The session ID (creates new if None)
        stream: Whether to stream results via SSE
        config: The CLI config object

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    print(f"📤 Dispatching: {utterance[:80]}{'...' if len(utterance) > 80 else ''}")

    async with httpx.AsyncClient() as client:
        # Dispatch the utterance
        response = await client.post(
            f"{server_url}/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
            },
            timeout=30.0,
        )

        if response.status_code != 200:
            print(f"❌ Dispatch failed: {response.text}", file=sys.stderr)
            return 1

        data = response.json()
        utterance_id = data.get("utterance_id")
        session_id = data.get("session_id")
        intent_ids = data.get("intent_ids", [])
        intent_count = data.get("intent_count", 0)

        # Save session ID for future commands
        config.set_session_id(session_id)

        print(f"✓ Dispatched {intent_count} intent(s)")
        print(f"  Utterance ID: {utterance_id[:8]}...")
        print(f"  Session ID: {session_id[:8]}...")

        if not stream:
            return 0

        # Stream results via SSE
        print("\n📡 Streaming results...\n")

        # Register surface for this CLI session
        surface_response = await client.post(
            f"{server_url}/api/v1/surfaces/register",
            json={
                "session_id": session_id,
                "surface_type": "cli",
            },
        )
        if surface_response.status_code == 200:
            surface_data = surface_response.json()
            surface_id = surface_data.get("surface_id")
        else:
            surface_id = None

        try:
            # Connect to SSE stream
            async with client.stream(
                "GET",
                f"{server_url}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "cli",
                },
                timeout=None,
            ) as response:
                if response.status_code != 200:
                    print(f"❌ SSE connection failed: {response.status_code}", file=sys.stderr)
                    return 1

                # Stream events
                async for line in response.aiter_lines():
                    if line:
                        event_type, value = sse.parse_sse_line(line)
                        if event_type and value:
                            # Simple display for now
                            if event_type == "data":
                                try:
                                    data = json.loads(value)
                                    formatted = sse.format_sse_event({"event": "message", "data": data})
                                    sys.stdout.write(formatted)
                                    sys.stdout.flush()
                                except json.JSONDecodeError:
                                    pass
                            elif event_type and event_type not in ("id", "retry"):
                                # Event type line
                                pass

        except KeyboardInterrupt:
            print("\n⏹️  Streaming stopped")

        return 0


async def ask(
    question: str,
    topic_id: Optional[str],
    server_url: str,
    session_id: Optional[str],
    config: Config,
) -> int:
    """
    Ask a question (query a specific topic).

    Similar to dispatch but scoped to a specific topic.

    Args:
        question: The question to ask
        topic_id: The topic ID (uses active topic if None)
        server_url: The aide-de-camp server URL
        session_id: The session ID (creates new if None)
        config: The CLI config object

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # For now, ask is just a dispatch with topic context
    # In a full implementation, this would use a topic-specific endpoint
    utterance = f"about {topic_id}: {question}" if topic_id else question

    return await dispatch(
        utterance=utterance,
        server_url=server_url,
        session_id=session_id,
        stream=True,
        config=config,
    )


async def status(
    server_url: str,
    session_id: Optional[str],
    as_json: bool,
) -> int:
    """
    Show active session status.

    Displays the current session's workload summary and active topics.

    Args:
        server_url: The aide-de-camp server URL
        session_id: The session ID (uses default if None)
        as_json: Whether to output as JSON

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    if not session_id:
        print("No active session. Use 'adc dispatch' to start a session.", file=sys.stderr)
        return 1

    async with httpx.AsyncClient() as client:
        # Get topics for session
        response = await client.get(
            f"{server_url}/api/v1/sessions/{session_id}/topics",
            timeout=10.0,
        )

        if response.status_code != 200:
            print(f"❌ Failed to get status: {response.text}", file=sys.stderr)
            return 1

        data = response.json()
        cards = data.get("cards", [])

        if as_json:
            print(json.dumps(data, indent=2))
        else:
            print(f"\n📊 Session Status: {session_id[:8]}...")
            print(f"📌 Active Topics: {len(cards)}\n")

            for card in cards:
                label = card.get("label", "unknown")
                topic_id = card.get("topic_id", "unknown")[:8]
                staleness = card.get("staleness_hours", 0)
                result_count = card.get("result_count", 0)

                if staleness < 1:
                    staleness_str = "🟢 fresh"
                elif staleness < 24:
                    staleness_str = f"🟡 {int(staleness)}h"
                else:
                    staleness_str = f"🔴 {int(staleness)}h"

                print(f"  [{topic_id}] {label}")
                print(f"    Status: {staleness_str} | Results: {result_count}")

        return 0


async def topics(
    server_url: str,
    session_id: Optional[str],
    as_json: bool,
) -> int:
    """
    List active topics.

    Shows all active topics for the current session with details.

    Args:
        server_url: The aide-de-camp server URL
        session_id: The session ID (uses default if None)
        as_json: Whether to output as JSON

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    if not session_id:
        print("No active session. Use 'adc dispatch' to start a session.", file=sys.stderr)
        return 1

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{server_url}/api/v1/sessions/{session_id}/topics",
            timeout=10.0,
        )

        if response.status_code != 200:
            print(f"❌ Failed to get topics: {response.text}", file=sys.stderr)
            return 1

        data = response.json()
        cards = data.get("cards", [])

        if as_json:
            print(json.dumps(data, indent=2))
        else:
            print(f"\n📌 Active Topics ({len(cards)}):\n")

            for card in cards:
                label = card.get("label", "unknown")
                topic_id = card.get("topic_id", "unknown")
                topic_type = card.get("type", "unknown")
                staleness = card.get("staleness_hours", 0)
                result_count = card.get("result_count", 0)
                last_active = card.get("last_active", "unknown")

                staleness_str = "🟢" if staleness < 1 else (f"🟡 {int(staleness)}h" if staleness < 24 else f"🔴 {int(staleness)}h")

                print(f"  {topic_id}")
                print(f"    Label: {label}")
                print(f"    Type: {topic_type}")
                print(f"    Status: {staleness_str}")
                print(f"    Results: {result_count}")
                print(f"    Last Active: {last_active}")
                print()

        return 0


async def exceptions(
    server_url: str,
    as_json: bool,
) -> int:
    """
    Show exception queue.

    Displays the current exception queue and ambient monitoring status.

    Args:
        server_url: The aide-de-camp server URL
        as_json: Whether to output as JSON

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{server_url}/api/v1/monitoring/status",
            timeout=10.0,
        )

        if response.status_code != 200:
            print(f"❌ Failed to get monitoring status: {response.text}", file=sys.stderr)
            return 1

        data = response.json()

        if as_json:
            print(json.dumps(data, indent=2))
        else:
            running = data.get("running", False)
            active_topics = data.get("active_topics", [])
            exceptions = data.get("exceptions", 0)

            print(f"\n⚠️  Exception Queue\n")
            print(f"  Status: {'🟢 Running' if running else '🔴 Stopped'}")
            print(f"  Queued Exceptions: {exceptions}")
            print(f"  Active Monitored Topics: {len(active_topics)}\n")

            if active_topics:
                print("  Monitored Topics:")
                for topic in active_topics:
                    topic_id = topic.get("topic_id", "unknown")[:8]
                    project = topic.get("project_slug", "unknown")
                    intent_type = topic.get("intent_type", "unknown")
                    urgency = topic.get("urgency", "normal")

                    urgency_symbols = {
                        "critical": "🔴",
                        "high": "🟠",
                        "normal": "🟢",
                        "low": "⚪",
                    }
                    symbol = urgency_symbols.get(urgency, "⚪")

                    print(f"    {symbol} [{topic_id}] {project} ({intent_type})")

        return 0


def config_cmd(
    set_server: Optional[str],
    set_session: Optional[str],
    show: bool,
) -> int:
    """
    Manage CLI configuration.

    Views or updates the CLI configuration file.

    Args:
        set_server: Server URL to set
        set_session: Session ID to set
        show: Whether to show current configuration

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    from .config import get_config

    config = get_config()

    if set_server:
        config.set_server_url(set_server)
        print(f"✓ Server URL set to: {set_server}")

    if set_session:
        config.set_session_id(set_session)
        print(f"✓ Session ID set to: {set_session[:8]}...")

    if show or (not set_server and not set_session):
        server_url = config.get_server_url()
        session_id = config.get_session_id()

        print("\n⚙️  ADC Configuration\n")
        print(f"  Server URL: {server_url}")
        print(f"  Session ID: {f'{session_id[:8]}...' if session_id else 'Not set'}\n")

    return 0


async def rehearsal(
    server: str,
    inject_slow_step: Optional[int],
) -> int:
    """
    Run Phase 5 demo rehearsal.

    Executes the golden path demo script, validates smooth criteria,
    and files defect beads on violations.

    Args:
        server: ADC server URL
        inject_slow_step: Inject a slow step at given step number (for testing)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    import subprocess
    import sys
    from pathlib import Path

    # Path to rehearsal script
    repo_dir = Path(__file__).parent.parent.parent
    rehearsal_script = repo_dir / "scripts" / "rehearsal.py"

    if not rehearsal_script.exists():
        print(f"❌ Rehearsal script not found: {rehearsal_script}", file=sys.stderr)
        return 1

    # Build command
    cmd = [sys.executable, str(rehearsal_script), "--server", server]
    if inject_slow_step:
        cmd.extend(["--inject-slow-step", str(inject_slow_step)])

    print(f"🎬 Running rehearsal: {rehearsal_script}")
    print(f"📋 Server: {server}\n")

    # Run rehearsal script
    result = subprocess.run(cmd, cwd=repo_dir)

    return result.returncode


def freeze_cmd(toggle: bool) -> int:
    """
    Manage self-modification freeze state.

    View or toggle the freeze protection that blocks self-modification writes.

    Args:
        toggle: If True, toggle freeze state (create or remove sentinel file)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    from src.freeze import get_status, set_frozen

    if toggle:
        # Get current state before toggling
        current = get_status()
        new_state = not current["frozen"]
        set_frozen(new_state)

        if new_state:
            print("✓ Self-modification frozen (created data/FREEZE)")
            print("  To unfreeze, run: adc freeze --toggle")
        else:
            print("✓ Self-modification unfrozen (removed data/FREEZE)")
        return 0

    # Show current status
    status = get_status()

    print("\n🔒 Self-Modification Freeze Status\n")

    if status["frozen"]:
        print(f"  Status: 🔴 FROZEN")
        print(f"  Reason: {status['reason']}\n")
        print("  Self-modification writes are blocked.")
        print("  To unfreeze:")
        print("    - If env var: unset ADC_SELFMOD_FREEZE")
        print("    - If sentinel: adc freeze --toggle\n")
    else:
        print(f"  Status: 🟢 UNFROZEN\n")
        print("  Self-modification writes are enabled.")
        print("  To freeze: adc freeze --toggle\n")

    return 0


def restore_artifacts_cmd(commits: int = 1, dry_run: bool = False) -> int:
    """
    Restore artifacts from git history by reverting self-mod commits.

    Reverts the specified number of self-modification commits, automatically
    clearing any freeze state before reverting. Self-mod commits are identified
    by their commit message pattern: 'auto: self-mod write to ...'

    Args:
        commits: Number of self-mod commits to revert (default: 1)
        dry_run: If True, show what would be reverted without making changes

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    import subprocess
    from pathlib import Path

    from src.freeze import set_frozen, check_frozen

    print("\n🔄 Artifact Restore\n")

    # Check current freeze state
    status = check_frozen()
    was_frozen = status.is_frozen

    if was_frozen:
        print(f"🔓 Unfreezing before restore (was: {status.reason})")
        set_frozen(False)
        print("✓ Unfrozen\n")

    # Get the repo root
    repo_root = Path("/home/coding/aide-de-camp")

    try:
        # Find self-mod commits
        # Git log command to find commits matching the pattern
        # Format: %h for short hash, %s for subject
        result = subprocess.run(
            ['git', 'log', '--oneline', '-n', str(commits * 2)],  # Get extra to filter
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )

        if result.returncode != 0:
            print(f"❌ Failed to get git log: {result.stderr}", file=sys.stderr)
            return 1

        # Parse commits to find self-mod ones
        all_commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split(' ', 1)
            if len(parts) == 2:
                short_hash, subject = parts
                if 'auto: self-mod write to' in subject:
                    all_commits.append((short_hash, subject))

        # Limit to requested number
        self_mod_commits = all_commits[:commits]

        if not self_mod_commits:
            print("ℹ️  No self-modification commits found to revert.")
            if was_frozen:
                print("🔓 Re-freezing (restore state)")
                set_frozen(True)
            return 0

        print(f"Found {len(self_mod_commits)} self-mod commit(s) to revert:\n")
        for i, (short_hash, subject) in enumerate(self_mod_commits, 1):
            print(f"  {i}. {short_hash} - {subject}")

        if dry_run:
            print("\n🏁 Dry run complete - no changes made.")
            if was_frozen:
                print("🔓 Re-freezing (restore state)")
                set_frozen(True)
            return 0

        print("\n🔄 Reverting commits...")

        # Revert each commit in reverse order (oldest first)
        for short_hash, _ in reversed(self_mod_commits):
            print(f"  Reverting {short_hash}...", end=" ")
            result = subprocess.run(
                ['git', 'revert', '--no-commit', short_hash],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=30
            )

            if result.returncode != 0:
                print(f"❌")
                print(f"    Failed: {result.stderr}", file=sys.stderr)
                # Abort the revert on failure
                subprocess.run(['git', 'revert', '--abort'], cwd=repo_root, capture_output=True)
                if was_frozen:
                    print("🔓 Re-freezing (restore state)")
                    set_frozen(True)
                return 1

            print("✓")

        # Commit the revert
        print("\n💾 Committing revert...", end=" ")
        result = subprocess.run(
            ['git', 'commit', '-m', f"adc restore-artifacts: revert {len(self_mod_commits)} self-mod commit(s)"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10
        )

        if result.returncode != 0:
            print(f"❌")
            print(f"    Failed to commit: {result.stderr}", file=sys.stderr)
            if was_frozen:
                print("🔓 Re-freezing (restore state)")
                set_frozen(True)
            return 1

        print("✓")
        print(f"\n✅ Successfully reverted {len(self_mod_commits)} self-mod commit(s)")
        print("   Artifacts restored to previous version.")

        # Re-freeze if it was frozen before
        if was_frozen:
            print("\n🔓 Re-freezing (restore state)")
            set_frozen(True)
            print("✓ Re-frozen")

        return 0

    except subprocess.TimeoutExpired:
        print("❌ Git command timed out", file=sys.stderr)
        if was_frozen:
            print("🔓 Re-freezing (restore state)")
            set_frozen(True)
        return 1
    except Exception as e:
        print(f"❌ Restore failed: {e}", file=sys.stderr)
        if was_frozen:
            print("🔓 Re-freezing (restore state)")
            set_frozen(True)
        return 1
