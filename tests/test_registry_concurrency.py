"""Focused regression tests for concurrent hot-reload registry access.

These tests intentionally use both independent event-loop threads and ordinary
worker threads.  An ``asyncio.Lock`` protects only one event loop; the registry
must also remain safe when synchronous application code and test workers race.
Every future has a three-second deadline so a lock regression fails fast.
"""

import asyncio
import builtins
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

import src.components.hot_reload as hot_reload_module
import src.registry as registry_module
from src.components.hot_reload import HotReloadManager
from src.utils.atomic_write import atomic_write


def _registry_document(marker: str) -> str:
    """Return a complete, schema-valid registry document."""
    return yaml.safe_dump(
        {
            "projects": {
                "demo": {
                    "description": f"demo {marker}",
                    "aliases": ["demo"],
                    "intent_support": ["status"],
                }
            },
            "clusters": {},
            "argocd": {},
            "global_aliases": {},
        },
        sort_keys=False,
    )


@pytest.fixture
def isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Give registry cache tests an isolated file and discovery root."""
    registry_path = tmp_path / "registry.yaml"
    discovery_root = tmp_path / "discovery"
    discovery_root.mkdir()
    atomic_write(registry_path, _registry_document("initial"))

    with registry_module._cache_lock:
        previous_cache = registry_module._cache
        previous_cache_at = registry_module._cache_at
        registry_module._cache = None
        registry_module._cache_at = 0

    monkeypatch.setattr(registry_module, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(registry_module, "DISCOVERY_ROOT", discovery_root)

    yield registry_path

    with registry_module._cache_lock:
        registry_module._cache = previous_cache
        registry_module._cache_at = previous_cache_at


def test_registry_reads_and_rebuilds_across_event_loop_threads(isolated_registry):
    """Separate event loops can force reloads without cache corruption/deadlock."""
    worker_count = 8
    start = threading.Barrier(worker_count)
    errors = []
    errors_lock = threading.Lock()

    async def read_registry(force: bool):
        snapshot = await registry_module.get_registry(force=force)
        assert snapshot["projects"]["demo"]["description"].startswith("demo ")
        assert set(snapshot) == {"projects", "clusters", "argocd", "global_aliases"}

    def worker(worker_id: int):
        try:
            start.wait(timeout=2)
            for iteration in range(12):
                asyncio.run(read_registry(force=(iteration % 2 == 0)))
        except Exception as error:  # surfaced by the assertion below
            with errors_lock:
                errors.append(error)

    executor = ThreadPoolExecutor(max_workers=worker_count)
    futures = [executor.submit(worker, worker_id) for worker_id in range(worker_count)]
    try:
        for future in futures:
            future.result(timeout=3)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    assert errors == []


def test_hot_reload_read_write_race_publishes_complete_documents(tmp_path: Path):
    """Readers see only complete old/new configs while writers replace atomically."""
    config_path = tmp_path / "monitoring.yaml"
    atomic_write(config_path, _registry_document("initial"))
    manager = HotReloadManager()
    manager.register_config("monitoring", str(config_path))

    start = threading.Barrier(8)
    errors = []
    errors_lock = threading.Lock()

    def record_error(error):
        with errors_lock:
            errors.append(error)

    def reader():
        try:
            start.wait(timeout=2)
            for _ in range(20):
                config = manager.get_config("monitoring")
                assert config["projects"]["demo"]["description"].startswith("demo ")
        except Exception as error:
            record_error(error)

    def writer(writer_id: int):
        try:
            start.wait(timeout=2)
            for iteration in range(10):
                atomic_write(config_path, _registry_document(f"writer-{writer_id}-{iteration}"))
                manager.force_reload("monitoring")
        except Exception as error:
            record_error(error)

    executor = ThreadPoolExecutor(max_workers=8)
    futures = [executor.submit(reader) for _ in range(6)]
    futures.extend(executor.submit(writer, writer_id) for writer_id in range(2))
    try:
        for future in futures:
            future.result(timeout=3)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    assert errors == []


def test_atomic_registry_writers_do_not_leave_temporary_conflicts(tmp_path: Path):
    """Concurrent registry writes leave one valid document and no staging files."""
    registry_path = tmp_path / "registry.yaml"
    atomic_write(registry_path, _registry_document("initial"))
    errors = []
    errors_lock = threading.Lock()

    def writer(writer_id: int):
        try:
            for iteration in range(12):
                atomic_write(registry_path, _registry_document(f"{writer_id}-{iteration}"))
        except Exception as error:
            with errors_lock:
                errors.append(error)

    executor = ThreadPoolExecutor(max_workers=6)
    futures = [executor.submit(writer, writer_id) for writer_id in range(6)]
    try:
        for future in futures:
            future.result(timeout=3)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    assert errors == []
    parsed = yaml.safe_load(registry_path.read_text())
    assert parsed["projects"]["demo"]["description"].startswith("demo ")
    assert list(tmp_path.glob(f".{registry_path.name}.tmp_*.tmp")) == []


def test_hot_reload_retries_transient_reads_with_exponential_backoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """File reads get three retries with 100/200/400 ms backoff delays."""
    path = tmp_path / "prompt.md"
    path.write_text("complete prompt")
    manager = HotReloadManager()
    attempts = 0
    delays = []
    real_open = builtins.open

    def flaky_open(candidate, *args, **kwargs):
        nonlocal attempts
        if Path(candidate) == path and attempts < 3:
            attempts += 1
            raise OSError("temporary read conflict")
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)
    monkeypatch.setattr(hot_reload_module.time, "sleep", delays.append)

    assert manager._read_file_with_retry(path) == "complete prompt"
    assert attempts == 3
    assert delays == [0.1, 0.2, 0.4]
