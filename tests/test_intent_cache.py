"""
Unit tests for IntentCache class (bead adc-3aa19).

Tests TTL-based caching behavior:
- Cache hit when entry exists and not expired
- Cache miss when entry doesn't exist
- Cache miss when entry exists but expired
- Automatic cleanup of expired entries
- Cache size limits and eviction
"""

import time
import pytest

from src.intent.router import IntentCache, IntentType, IntentClassification


class TestIntentCache:
    """Test suite for IntentCache TTL and eviction behavior."""

    def test_cache_hit_on_valid_entry(self):
        """Cache should return value when entry exists and not expired."""
        cache = IntentCache(ttl_seconds=300)

        # Create a test classification
        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
            utterance_fragment="test utterance",
            reasoning="test reasoning",
            urgency="normal",
        )

        # Store in cache
        cache_key = "test_key_123"
        cache.set(cache_key, [classification])

        # Should get cache hit
        result = cache.get(cache_key)
        assert result is not None
        assert len(result) == 1
        assert result[0].intent_type == IntentType.STATUS
        assert result[0].project_slug == "test-project"

    def test_cache_miss_on_nonexistent_entry(self):
        """Cache should return None when key doesn't exist."""
        cache = IntentCache(ttl_seconds=300)

        result = cache.get("nonexistent_key")
        assert result is None

    def test_cache_miss_after_ttl_expiry(self):
        """Cache should return None after TTL expires."""
        # Use very short TTL for testing
        cache = IntentCache(ttl_seconds=1)

        classification = IntentClassification(
            intent_type=IntentType.ACTION,
            project_slug="test-project",
            confidence=0.8,
            utterance_fragment="test action",
            reasoning="test reasoning",
            urgency="high",
        )

        cache_key = "expiring_key"
        cache.set(cache_key, [classification])

        # Should get cache hit immediately
        result = cache.get(cache_key)
        assert result is not None

        # Wait for TTL to expire
        time.sleep(1.5)

        # Should get cache miss after expiry
        result = cache.get(cache_key)
        assert result is None

    def test_cache_expiry_removes_entry(self):
        """Expired entries should be removed from cache storage."""
        cache = IntentCache(ttl_seconds=1)

        classification = IntentClassification(
            intent_type=IntentType.BRAINSTORM,
            project_slug="test-project",
            confidence=0.7,
        )

        cache_key = "to_be_removed"
        cache.set(cache_key, [classification])

        # Verify entry exists
        stats_before = cache.get_stats()
        assert stats_before["size"] == 1

        # Wait for expiry
        time.sleep(1.5)

        # Trigger cleanup by accessing the expired entry
        cache.get(cache_key)

        # Verify entry was removed
        stats_after = cache.get_stats()
        assert stats_after["size"] == 0

    def test_cache_max_size_eviction(self):
        """Cache should evict oldest entry when max size is reached."""
        cache = IntentCache(ttl_seconds=300, max_size=3)

        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
        )

        # Fill cache to max capacity
        for i in range(3):
            cache.set(f"key_{i}", [classification])

        stats = cache.get_stats()
        assert stats["size"] == 3

        # Add one more entry - should evict oldest
        cache.set("key_3", [classification])

        stats = cache.get_stats()
        assert stats["size"] == 3  # Size should remain at max

        # Oldest entry (key_0) should be evicted
        result = cache.get("key_0")
        assert result is None

        # Other entries should still be accessible
        result = cache.get("key_1")
        assert result is not None

        result = cache.get("key_2")
        assert result is not None

        result = cache.get("key_3")
        assert result is not None

    def test_cache_statistics_tracking(self):
        """Cache should accurately track hit rate statistics."""
        cache = IntentCache(ttl_seconds=300)

        classification = IntentClassification(
            intent_type=IntentType.LOOKUP,
            project_slug="test-project",
            confidence=0.85,
            lookup_kind="logs",
        )

        cache.set("existing_key", [classification])

        # Generate 10 hits
        for _ in range(10):
            cache.get("existing_key")

        # Generate 5 misses
        for _ in range(5):
            cache.get("nonexistent_key")

        stats = cache.get_stats()
        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert stats["hit_rate"] == 66.66666666666666  # 10/15 = 66.67%

    def test_cache_clear(self):
        """Cache clear should remove all entries and reset statistics."""
        cache = IntentCache(ttl_seconds=300)

        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
        )

        # Add some entries
        for i in range(5):
            cache.set(f"key_{i}", [classification])

        # Generate some hits/misses
        cache.get("key_0")  # hit
        cache.get("nonexistent")  # miss

        stats_before = cache.get_stats()
        assert stats_before["size"] == 5
        assert stats_before["hits"] == 1
        assert stats_before["misses"] == 1

        # Clear cache
        cache.clear()

        stats_after = cache.get_stats()
        assert stats_after["size"] == 0
        assert stats_after["hits"] == 0
        assert stats_after["misses"] == 0

    def test_cache_with_custom_ttl(self):
        """Cache should respect custom TTL values."""
        # Test with 2-second TTL
        cache = IntentCache(ttl_seconds=2)

        classification = IntentClassification(
            intent_type=IntentType.REMINDER,
            project_slug="test-project",
            confidence=0.8,
        )

        cache_key = "custom_ttl_key"
        cache.set(cache_key, [classification])

        # Should be accessible immediately
        result = cache.get(cache_key)
        assert result is not None

        # Should still be accessible after 1 second
        time.sleep(1)
        result = cache.get(cache_key)
        assert result is not None

        # Should be expired after 2.5 seconds
        time.sleep(1.5)
        result = cache.get(cache_key)
        assert result is None

    def test_cache_cleanup_multiple_expired(self):
        """Cache cleanup should remove all expired entries when accessed individually."""
        # Use small max_size for faster testing
        cache = IntentCache(ttl_seconds=1, max_size=10)

        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
        )

        # Add exactly max_size entries (no eviction)
        for i in range(10):
            cache.set(f"expiring_key_{i}", [classification])

        stats_before = cache.get_stats()
        assert stats_before["size"] == 10  # Should be at max_size

        # Wait for all entries to expire
        time.sleep(1.5)

        # Trigger cleanup by accessing one expired entry
        # (cleanup only happens when size > 1000, so this won't trigger bulk cleanup)
        result = cache.get("expiring_key_0")
        assert result is None  # Should return None for expired entry

        stats_after = cache.get_stats()
        # The specific accessed entry is removed, but others remain until individually accessed
        assert stats_after["size"] == 9

        # Access all remaining expired entries to remove them one by one
        for i in range(1, 10):
            result = cache.get(f"expiring_key_{i}")
            assert result is None  # All should be expired

        final_stats = cache.get_stats()
        assert final_stats["size"] == 0

    def test_automatic_cleanup_on_large_cache(self):
        """Cache should automatically clean expired entries when size > 1000."""
        # Create cache with large max_size to test auto-cleanup at threshold
        cache = IntentCache(ttl_seconds=1, max_size=2000)

        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
        )

        # Add 1500 entries (exceeds 1000 threshold for auto-cleanup)
        for i in range(1500):
            cache.set(f"key_{i}", [classification])

        stats_before = cache.get_stats()
        assert stats_before["size"] == 1500

        # Wait for entries to expire
        time.sleep(1.5)

        # Trigger automatic cleanup by accessing any entry
        # Since size > 1000, this should clean ALL expired entries
        cache.get("key_0")

        stats_after = cache.get_stats()
        # All expired entries should be removed by automatic cleanup
        assert stats_after["size"] == 0

    def test_cache_stats_logging_interval(self):
        """Cache should log stats at configured intervals."""
        cache = IntentCache(ttl_seconds=300)

        # Initially should not log stats
        assert cache.should_log_stats() is False

        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
        )

        cache.set("key", [classification])

        # Generate 49 operations (should not trigger logging)
        for _ in range(49):
            cache.get("key")

        assert cache.should_log_stats() is False

        # 50th operation should trigger logging
        cache.get("key")
        assert cache.should_log_stats() is True

        # 51st should not
        cache.get("key")
        assert cache.should_log_stats() is False

        # 100th should trigger again
        for _ in range(49):
            cache.get("key")
        assert cache.should_log_stats() is True

    def test_cache_stores_list_of_classifications(self):
        """Cache should properly store and retrieve lists of classifications."""
        cache = IntentCache(ttl_seconds=300)

        # Create multiple classifications (e.g., from segmented utterance)
        classifications = [
            IntentClassification(
                intent_type=IntentType.STATUS,
                project_slug="project-a",
                confidence=0.9,
                utterance_fragment="check pods in project-a",
            ),
            IntentClassification(
                intent_type=IntentType.STATUS,
                project_slug="project-b",
                confidence=0.85,
                utterance_fragment="check pods in project-b",
            ),
        ]

        cache_key = "multiple_intents"
        cache.set(cache_key, classifications)

        # Retrieve and verify
        result = cache.get(cache_key)
        assert result is not None
        assert len(result) == 2
        assert result[0].project_slug == "project-a"
        assert result[1].project_slug == "project-b"

    def test_cache_ttl_default_value(self):
        """Cache should use 300 seconds (5 minutes) as default TTL."""
        cache = IntentCache()  # No ttl_seconds parameter

        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
        )

        cache_key = "default_ttl_test"
        cache.set(cache_key, [classification])

        # Should be accessible immediately
        result = cache.get(cache_key)
        assert result is not None

        # Should still be accessible after 4 minutes
        time.sleep(240)
        result = cache.get(cache_key)
        assert result is not None

        # Note: We don't test full 5-minute expiry in unit tests to keep them fast
        # The 1-second TTL tests above verify the expiry mechanism works

    def test_cache_max_size_default_value(self):
        """Cache should use 1000 as default max size."""
        cache = IntentCache()  # No max_size parameter

        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
        )

        # Add 1000 entries
        for i in range(1000):
            cache.set(f"key_{i}", [classification])

        stats = cache.get_stats()
        assert stats["size"] == 1000

        # Adding 1001st should evict one entry
        cache.set("key_1000", [classification])
        stats = cache.get_stats()
        assert stats["size"] == 1000
