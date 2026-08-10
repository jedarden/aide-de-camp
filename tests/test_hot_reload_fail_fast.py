"""Fail-fast regression tests for synchronous hot-reload operations.

The production API is synchronous because it is also used by request
handlers and worker threads.  These tests simulate a blocked filesystem call
and assert that each operation returns before the configured four-second
budget, with enough context to fix the underlying problem.

Common failure examples documented here:

* ``open()`` can block on a stalled network mount while reading a prompt.
* ``Path.stat()`` can block while checking a disconnected filesystem.
* A parser can stall while processing unexpectedly large or adversarial input.

In all three cases the caller must receive ``HotReloadTimeoutError`` instead
of waiting indefinitely or receiving a generic error without a file path.
"""

import builtins
import time
from pathlib import Path

import pytest

from src.components.hot_reload import HotReloadManager, HotReloadTimeoutError
from src.monitoring.config_loader import ConfigLoader


def _assert_fail_fast(error: HotReloadTimeoutError, path: Path, operation: str) -> None:
    """Verify timeout messages contain diagnosis and remediation context."""
    message = str(error)
    assert operation in message
    assert str(path) in message
    assert "Reason:" in message
    assert "Action:" in message
    assert error.timeout < 5


def test_blocked_file_read_times_out_during_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A prompt read blocked by a filesystem returns a contextual timeout quickly."""
    path = tmp_path / "blocked-prompt.md"
    path.write_text("prompt")
    manager = HotReloadManager()
    manager.FILE_OPERATION_TIMEOUT = 0.05
    real_open = builtins.open

    def blocked_open(candidate, *args, **kwargs):
        if Path(candidate) == path:
            time.sleep(10)
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", blocked_open)
    started = time.monotonic()

    with pytest.raises(HotReloadTimeoutError) as raised:
        manager.register_prompt("blocked", str(path))

    assert time.monotonic() - started < 1
    _assert_fail_fast(raised.value, path, "register_prompt('blocked')")


def test_blocked_mtime_check_times_out_before_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A stalled mtime lookup fails before registration can wait on the disk."""
    path = tmp_path / "blocked-mtime.md"
    path.write_text("prompt")
    manager = HotReloadManager()
    manager.FILE_OPERATION_TIMEOUT = 0.05
    real_stat = Path.stat

    def blocked_stat(candidate, *args, **kwargs):
        if candidate == path:
            time.sleep(10)
        return real_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", blocked_stat)
    started = time.monotonic()

    with pytest.raises(HotReloadTimeoutError) as raised:
        manager.register_prompt("blocked-mtime", str(path))

    assert time.monotonic() - started < 1
    _assert_fail_fast(raised.value, path, "register_prompt('blocked-mtime')")


def test_blocked_parser_times_out_during_config_registration(tmp_path: Path):
    """A parser that never completes cannot hang configuration registration."""
    path = tmp_path / "blocked-parser.yaml"
    path.write_text("key: value\n")
    manager = HotReloadManager()
    manager.FILE_OPERATION_TIMEOUT = 0.05

    def blocked_parser(content: str):
        del content
        time.sleep(10)
        return {"unreachable": True}

    manager._parsers[".yaml"] = blocked_parser
    started = time.monotonic()

    with pytest.raises(HotReloadTimeoutError) as raised:
        manager.register_config("blocked-parser", str(path))

    assert time.monotonic() - started < 1
    _assert_fail_fast(raised.value, path, "register_config('blocked-parser')")


def test_force_reload_timeout_preserves_last_known_good_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A force reload timeout is actionable and does not discard cached content."""
    path = tmp_path / "force-reload.md"
    path.write_text("known good")
    manager = HotReloadManager()
    manager.register_prompt("force", str(path))
    manager.FILE_OPERATION_TIMEOUT = 0.05
    real_open = builtins.open

    def blocked_open(candidate, *args, **kwargs):
        if Path(candidate) == path:
            time.sleep(10)
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", blocked_open)
    started = time.monotonic()

    with pytest.raises(HotReloadTimeoutError) as raised:
        manager.force_reload("force")

    assert time.monotonic() - started < 1
    _assert_fail_fast(raised.value, path, "force_reload('force')")
    assert manager._cache["force"] == "known good"


@pytest.mark.asyncio
async def test_async_config_loader_blocked_read_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The async monitoring loader also bounds a blocked synchronous read."""
    path = tmp_path / "monitoring.yaml"
    path.write_text("tick_interval_seconds: 1\n")
    loader = ConfigLoader(path)
    loader.FILE_OPERATION_TIMEOUT = 0.05
    real_open = builtins.open

    def blocked_open(candidate, *args, **kwargs):
        if Path(candidate) == path:
            time.sleep(10)
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", blocked_open)
    started = time.monotonic()

    with pytest.raises(HotReloadTimeoutError) as raised:
        await loader.get_config()

    assert time.monotonic() - started < 1
    _assert_fail_fast(raised.value, path, "load monitoring configuration")


@pytest.mark.asyncio
async def test_async_config_loader_blocked_mtime_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A monitoring mtime check cannot hang after the initial config load."""
    path = tmp_path / "monitoring.yaml"
    path.write_text("tick_interval_seconds: 1\n")
    loader = ConfigLoader(path)
    await loader.get_config()
    loader.FILE_OPERATION_TIMEOUT = 0.05
    real_stat = Path.stat

    def blocked_stat(candidate, *args, **kwargs):
        if candidate == path:
            time.sleep(10)
        return real_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", blocked_stat)
    started = time.monotonic()

    with pytest.raises(HotReloadTimeoutError) as raised:
        await loader.get_config()

    assert time.monotonic() - started < 1
    _assert_fail_fast(raised.value, path, "check monitoring configuration mtime")
