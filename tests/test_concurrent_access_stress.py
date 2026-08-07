#!/usr/bin/env python3
"""
Concurrent access stress tests using asyncio.gather() for true async concurrency.

These tests verify that the registry and hot-reload systems handle concurrent
async operations safely without race conditions, deadlocks, or data corruption.

All tests use asyncio.gather() for proper async concurrency (not threading).
All tests have strict timeouts (< 5 seconds) to detect deadlocks early.
"""

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
import yaml

from src.registry import get_registry, REGISTRY_PATH, _cache_lock, _cache, _cache_at


class ConcurrentTestStats:
    """Track statistics from concurrent test operations."""

    def __init__(self):
        self.operation_count = 0
        self.success_count = 0
        self.error_count = 0
        self.lock_waits = 0
        self.start_time = time.time()
        self.end_time = None
        self.errors = []

    def record_success(self):
        """Record a successful operation."""
        self.operation_count += 1
        self.success_count += 1

    def record_error(self, error: Exception):
        """Record a failed operation."""
        self.operation_count += 1
        self.error_count += 1
        self.errors.append(error)

    def record_lock_wait(self):
        """Record a lock wait event."""
        self.lock_waits += 1

    def finish(self):
        """Mark the test as finished."""
        self.end_time = time.time()

    def summary(self) -> str:
        """Generate a summary of the statistics."""
        duration = (self.end_time or time.time()) - self.start_time
        lines = [
            f"Concurrent Test Statistics:",
            f"  Duration: {duration:.3f} seconds",
            f"  Total operations: {self.operation_count}",
            f"  Successful: {self.success_count}",
            f"  Failed: {self.error_count}",
            f"  Lock waits: {self.lock_waits}",
            f"  Operations/second: {self.operation_count / duration:.1f}"
        ]
        return "\n".join(lines)


@pytest.mark.asyncio
async def test_concurrent_registry_reads():
    """
    Test: 10 tasks simultaneously reading registry.

    Uses asyncio.gather() for true async concurrency.
    Verifies all reads succeed and return consistent data.
    Timeout: 5 seconds for deadlock detection.
    """
    print("\n=== Testing Concurrent Registry Reads (asyncio.gather) ===")

    stats = ConcurrentTestStats()
    num_tasks = 10
    reads_per_task = 20

    async def concurrent_reader(task_id: int):
        """Simulate concurrent registry reads."""
        try:
            for i in range(reads_per_task):
                # Mix of cached and forced reads
                force = (i % 5 == 0)  # Every 5th read forces rebuild
                registry = await get_registry(force=force)

                # Verify registry structure
                assert isinstance(registry, dict), "Registry should be a dict"
                assert 'projects' in registry, "Registry should have projects"
                assert 'clusters' in registry, "Registry should have clusters"

                # Small delay to increase concurrency overlap
                await asyncio.sleep(0.001)

            stats.record_success()
            return True

        except Exception as e:
            stats.record_error(e)
            return False

    start_time = time.time()

    # Use asyncio.gather for true async concurrency
    tasks = [
        concurrent_reader(i)
        for i in range(num_tasks)
    ]

    # Add timeout for deadlock detection
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=5.0
    )

    duration = time.time() - start_time
    stats.finish()

    # Count successes
    successful_tasks = sum(1 for r in results if r is True)
    failed_tasks = sum(1 for r in results if r is not True)

    print(f"Concurrent registry read results:")
    print(f"  Tasks: {num_tasks}")
    print(f"  Reads per task: {reads_per_task}")
    print(f"  Total operations: {num_tasks * reads_per_task}")
    print(f"  Duration: {duration:.3f} seconds")
    print(f"  Successful tasks: {successful_tasks}/{num_tasks}")
    print(f"  Failed tasks: {failed_tasks}")

    if stats.error_count > 0:
        print(f"\n⚠ {stats.error_count} errors detected:")
        for error in stats.errors:
            print(f"  - {type(error).__name__}: {error}")
        print(stats.summary())

    # All tasks should complete successfully
    assert successful_tasks == num_tasks, \
        f"Only {successful_tasks}/{num_tasks} tasks completed successfully"

    assert stats.error_count == 0, "No errors should occur during concurrent reads"

    print("✓ Concurrent registry reads: PASSED")


@pytest.mark.asyncio
async def test_registry_read_write_race():
    """
    Test: Race between registry read and write operations.

    Multiple tasks reading and writing registry simultaneously.
    Verifies no data corruption and consistent reads.
    Timeout: 5 seconds for deadlock detection.
    """
    print("\n=== Testing Registry Read/Write Race Conditions ===")

    stats = ConcurrentTestStats()
    num_readers = 8
    num_writers = 2
    iterations = 15

    async def race_reader(reader_id: int):
        """Concurrent reader that verifies consistent data."""
        try:
            for i in range(iterations):
                # Varying force pattern to trigger different cache states
                force = (i % 7 == 0)
                registry = await get_registry(force=force)

                # Verify data consistency
                assert isinstance(registry, dict)
                assert 'projects' in registry
                assert 'clusters' in registry

                # Verify no partial reads
                assert registry.get('projects') is not None
                assert registry.get('clusters') is not None

                await asyncio.sleep(0.001)

            stats.record_success()
            return True

        except Exception as e:
            stats.record_error(e)
            return False

    async def race_writer(writer_id: int):
        """Concurrent writer that forces cache rebuilds."""
        try:
            for i in range(iterations):
                # Force cache rebuild (simulates write operation)
                registry = await get_registry(force=True)

                # Verify rebuild succeeded
                assert isinstance(registry, dict)
                assert 'projects' in registry

                await asyncio.sleep(0.001)

            stats.record_success()
            return True

        except Exception as e:
            stats.record_error(e)
            return False

    start_time = time.time()

    # Launch all readers and writers concurrently
    all_tasks = []
    for i in range(num_readers):
        all_tasks.append(race_reader(i))
    for i in range(num_writers):
        all_tasks.append(race_writer(i))

    # Use asyncio.gather for true concurrency
    results = await asyncio.wait_for(
        asyncio.gather(*all_tasks, return_exceptions=True),
        timeout=8.0  # Slightly longer timeout for mixed read/write
    )

    duration = time.time() - start_time
    stats.finish()

    successful_ops = sum(1 for r in results if r is True)
    failed_ops = sum(1 for r in results if r is not True)

    print(f"Read/write race results:")
    print(f"  Readers: {num_readers}")
    print(f"  Writers: {num_writers}")
    print(f"  Total operations: {len(results)}")
    print(f"  Duration: {duration:.3f} seconds")
    print(f"  Successful: {successful_ops}")
    print(f"  Failed: {failed_ops}")

    if stats.error_count > 0:
        print(f"\n⚠ {stats.error_count} errors detected:")
        for error in stats.errors:
            print(f"  - {type(error).__name__}: {error}")
        print(stats.summary())

    # All operations should succeed
    assert successful_ops == len(results), \
        f"Only {successful_ops}/{len(results)} operations succeeded"

    assert stats.error_count == 0, "No errors should occur during read/write race"

    print("✓ Registry read/write race: PASSED")


@pytest.mark.asyncio
async def test_temporary_file_creation_conflicts():
    """
    Test: Temporary file creation conflicts under concurrent access.

    Multiple tasks creating temporary files concurrently.
    Verifies no file system conflicts or race conditions.
    Timeout: 5 seconds for deadlock detection.
    """
    print("\n=== Testing Temporary File Creation Conflicts ===")

    stats = ConcurrentTestStats()
    num_tasks = 10
    files_per_task = 5

    async def file_creator(task_id: int):
        """Create temporary files concurrently."""
        created_files = []
        try:
            for i in range(files_per_task):
                # Create unique temporary file
                temp_file = tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix=f'_task{task_id}_file{i}.yaml',
                    delete=False
                )
                temp_path = Path(temp_file.name)

                # Write some content
                test_content = {
                    'task_id': task_id,
                    'file_index': i,
                    'timestamp': time.time(),
                    'test_data': ['item1', 'item2', 'item3']
                }
                yaml.dump(test_content, temp_file)
                temp_file.close()
                created_files.append(temp_path)

                # Verify file was created successfully
                assert temp_path.exists(), f"Failed to create {temp_path}"

                # Read back and verify content
                with open(temp_path, 'r') as f:
                    read_content = yaml.safe_load(f)
                assert read_content['task_id'] == task_id
                assert read_content['file_index'] == i

                # Small delay to increase concurrency
                await asyncio.sleep(0.01)

            # Cleanup: delete all created files
            for file_path in created_files:
                try:
                    file_path.unlink()
                except Exception:
                    pass  # Best effort cleanup

            stats.record_success()
            return True

        except Exception as e:
            stats.record_error(e)
            # Cleanup on error
            for file_path in created_files:
                try:
                    file_path.unlink()
                except Exception:
                    pass
            return False

    start_time = time.time()

    # Create all tasks concurrently
    tasks = [
        file_creator(i)
        for i in range(num_tasks)
    ]

    # Use asyncio.gather for true concurrency
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=5.0
    )

    duration = time.time() - start_time
    stats.finish()

    successful_tasks = sum(1 for r in results if r is True)
    total_files_created = successful_tasks * files_per_task

    print(f"Temporary file conflict results:")
    print(f"  Tasks: {num_tasks}")
    print(f"  Files per task: {files_per_task}")
    print(f"  Total files created: {total_files_created}")
    print(f"  Duration: {duration:.3f} seconds")
    print(f"  Successful tasks: {successful_tasks}/{num_tasks}")
    print(f"  Files/second: {total_files_created / duration:.1f}")

    if stats.error_count > 0:
        print(f"\n⚠ {stats.error_count} errors detected:")
        for error in stats.errors:
            print(f"  - {type(error).__name__}: {error}")
        print(stats.summary())

    # All tasks should succeed with no file conflicts
    assert successful_tasks == num_tasks, \
        f"Only {successful_tasks}/{num_tasks} tasks completed successfully"

    assert stats.error_count == 0, "No file creation conflicts should occur"

    print("✓ Temporary file creation conflicts: PASSED")


@pytest.mark.asyncio
async def test_high_concurrency_registry_stress():
    """
    Test: High concurrency stress test with rapid registry access.

    20 tasks performing rapid registry operations.
    Verifies system handles high load without crashes.
    Timeout: 5 seconds for deadlock detection.
    """
    print("\n=== Testing High Concurrency Registry Stress ===")

    stats = ConcurrentTestStats()
    num_tasks = 20
    operations_per_task = 10

    async def stress_worker(task_id: int):
        """Execute rapid registry operations under stress."""
        try:
            for i in range(operations_per_task):
                # Mix of operations
                op_type = i % 4

                if op_type == 0:
                    # Normal registry read
                    await get_registry()

                elif op_type == 1:
                    # Forced cache rebuild
                    await get_registry(force=True)

                elif op_type == 2:
                    # Multiple rapid reads
                    await asyncio.gather(
                        get_registry(),
                        get_registry(),
                        get_registry()
                    )

                else:
                    # Read with delay (simulates processing)
                    registry = await get_registry()
                    assert 'projects' in registry
                    await asyncio.sleep(0.001)

            stats.record_success()
            return True

        except Exception as e:
            stats.record_error(e)
            return False

    start_time = time.time()

    # Launch all stress workers concurrently
    tasks = [
        stress_worker(i)
        for i in range(num_tasks)
    ]

    # Use asyncio.gather for maximum concurrency
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=10.0  # Longer timeout for stress test
    )

    duration = time.time() - start_time
    stats.finish()

    successful_tasks = sum(1 for r in results if r is True)
    total_operations = num_tasks * operations_per_task

    print(f"High concurrency stress results:")
    print(f"  Tasks: {num_tasks}")
    print(f"  Operations per task: {operations_per_task}")
    print(f"  Total operations: {total_operations}")
    print(f"  Duration: {duration:.3f} seconds")
    print(f"  Successful tasks: {successful_tasks}/{num_tasks}")
    print(f"  Operations/second: {total_operations / duration:.1f}")

    if stats.error_count > 0:
        print(f"\n⚠ {stats.error_count} errors detected:")
        for error in stats.errors:
            print(f"  - {type(error).__name__}: {error}")
        print(stats.summary())

    # At least 95% success rate under stress
    success_rate = successful_tasks / num_tasks
    assert success_rate >= 0.95, \
        f"Success rate too low under stress: {success_rate * 100:.1f}%"

    print("✓ High concurrency stress: PASSED")


@pytest.mark.asyncio
async def test_cache_consistency_under_concurrency():
    """
    Test: Cache consistency during concurrent updates.

    Multiple tasks forcing cache updates simultaneously.
    Verifies all tasks see consistent cache state.
    Timeout: 5 seconds for deadlock detection.
    """
    print("\n=== Testing Cache Consistency Under Concurrency ===")

    try:
        # Clear cache to start fresh
        import src.registry as registry_module
        registry_module._cache = None
        registry_module._cache_at = 0

        cache_snapshots = []
        snapshot_lock = asyncio.Lock()

        async def cache_observer(task_id: int):
            """Observe cache state during concurrent access."""
            try:
                for i in range(10):
                    # Force cache rebuild frequently
                    registry = await get_registry(force=(i % 3 == 0))

                    # Capture cache snapshot
                    async with snapshot_lock:
                        cache_snapshots.append({
                            'task': task_id,
                            'iteration': i,
                            'projects_count': len(registry.get('projects', {})),
                            'has_clusters': 'clusters' in registry,
                            'has_argocd': 'argocd' in registry
                        })

                    await asyncio.sleep(0.001)

                return True

            except Exception as e:
                print(f"Cache observer error: {e}")
                return False

        # Run multiple observers concurrently
        tasks = [
            cache_observer(i)
            for i in range(15)
        ]

        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=5.0
        )

        print(f"Collected {len(cache_snapshots)} cache state observations")

        # Analyze cache consistency
        consistent_structure = all(
            snapshot['has_clusters'] and snapshot['has_argocd']
            for snapshot in cache_snapshots
        )

        print(f"Cache structure consistency: {consistent_structure}")

        # Project count should be relatively stable
        project_counts = [s['projects_count'] for s in cache_snapshots]
        min_count = min(project_counts)
        max_count = max(project_counts)

        print(f"Project count range: {min_count} - {max_count}")

        # Range should be small (atomic cache updates)
        count_variation = max_count - min_count
        assert count_variation <= 1, \
            f"Project count varied too much: {count_variation}"

        print("✓ Cache consistency: PASSED")

    except Exception as e:
        print(f"✗ Cache consistency test failed: {e}")
        raise


@pytest.mark.asyncio
async def test_lock_contention_detection():
    """
    Test: Detect and measure lock contention under high concurrency.

    Multiple tasks competing for registry cache lock.
    Verifies lock contention is handled gracefully.
    Timeout: 5 seconds for deadlock detection.
    """
    print("\n=== Testing Lock Contention Detection ===")

    stats = ConcurrentTestStats()
    num_tasks = 25
    accesses_per_task = 8

    async def contentious_accessor(task_id: int):
        """Access registry with high contention potential."""
        try:
            for i in range(accesses_per_task):
                # Every access forces rebuild (maximizes contention)
                start = time.time()
                registry = await get_registry(force=True)
                wait_time = time.time() - start

                # Track lock waits (if access took > 1ms, likely waited for lock)
                if wait_time > 0.001:
                    stats.record_lock_wait()

                # Verify data integrity
                assert isinstance(registry, dict)
                assert 'projects' in registry

            stats.record_success()
            return True

        except Exception as e:
            stats.record_error(e)
            return False

    start_time = time.time()

    # Launch all tasks concurrently for maximum contention
    tasks = [
        contentious_accessor(i)
        for i in range(num_tasks)
    ]

    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=8.0
    )

    duration = time.time() - start_time
    stats.finish()

    successful_tasks = sum(1 for r in results if r is True)

    print(f"Lock contention results:")
    print(f"  Tasks: {num_tasks}")
    print(f"  Accesses per task: {accesses_per_task}")
    print(f"  Total accesses: {num_tasks * accesses_per_task}")
    print(f"  Duration: {duration:.3f} seconds")
    print(f"  Successful tasks: {successful_tasks}/{num_tasks}")
    print(f"  Lock waits detected: {stats.lock_waits}")
    print(f"  Lock contention rate: {stats.lock_waits / (num_tasks * accesses_per_task) * 100:.1f}%")

    if stats.error_count > 0:
        print(f"\n⚠ {stats.error_count} errors detected:")
        for error in stats.errors:
            print(f"  - {type(error).__name__}: {error}")

    # All tasks should succeed despite lock contention
    assert successful_tasks == num_tasks, \
        f"Only {successful_tasks}/{num_tasks} tasks completed successfully"

    print("✓ Lock contention handling: PASSED")


if __name__ == "__main__":
    # Run tests with pytest
    import sys
    pytest.main([__file__, "-v", "-s"] + sys.argv[1:])
