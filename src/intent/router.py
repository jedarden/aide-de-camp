"""
Intent Router - classifies utterances and routes to appropriate strands.

Uses LLM to classify intents by type and project, then routes:
- task-profile intents → escalate strand (bead creation)
- other intents → fetch + synthesize strands
"""
import asyncio
import json
import time
import uuid
import re
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Any, Optional
from functools import lru_cache

import httpx

from ..components.hot_reload import get_reload_manager
from ..escalate.handler import EscalateRequest, escalate_intent
from ..escalate.llm import get_zai_client, ModelClass, LLMTimeoutError, LLMRateLimitError, LLMError
from ..errors.degraded_state import get_degraded_state_handler
from ..instrument.timings import DispatchTimings
from ..llm.response_parser import parse_llm_response, ParseLLMError
from ..render.hot_path import derive_result_type, get_renderer
from ..session.store import get_store
from ..fetch.commands import FetchRequest, FetchContext, IntentType as FetchIntentType, get_fetch_commands
from ..fetch.orchestrator import execute_fetch
from ..synthesize.strand import SynthesizeRequest, synthesize_intent
from ..sse.broadcaster import get_broadcaster, SSEEvent, EventType, broadcast_fetch_progress


logger = getLogger(__name__)


# --- Intent Cache with TTL ----------------------------------------------------
class IntentCache:
    """
    In-memory cache store for intent classifications with TTL support.

    Storage format: {cache_key -> (intent_mapping, expiry_timestamp)}
    - cache_key: SHA256 hash of utterance + optional context
    - intent_mapping: list[IntentClassification] to return on cache hit
    - expiry_timestamp: Unix timestamp when entry expires (now + ttl_seconds)

    Automatic cleanup:
    - Expired entries are removed on get() when cache size > 1000
    - Oldest entry is evicted when cache reaches capacity

    Thread-safety: Not thread-safe - assumes single-threaded async execution.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        """
        Initialize the cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 300 = 5 minutes)
            max_size: Maximum number of entries before eviction (default: 1000)
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: dict[str, tuple[list, float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._stats_log_interval = 50  # Log stats every N operations

    def get(self, key: str) -> list | None:
        """
        Retrieve cached intent mapping if exists and not expired.

        Args:
            key: Cache key (SHA256 hash)

        Returns:
            Cached intent mapping if exists and not expired, None otherwise
        """
        # Automatic cleanup: if cache size > 1000, remove all expired entries first
        # This prevents memory leaks from accumulating expired entries
        if len(self._cache) > 1000:
            removed = self._cleanup_expired()
            if removed > 0:
                logger.debug(f"Auto-cleanup removed {removed} expired entries (size: {len(self._cache)})")

        if key in self._cache:
            intent_mapping, expiry_timestamp = self._cache[key]

            # Check if entry has expired
            if time.time() < expiry_timestamp:
                self._cache_hits += 1
                age = time.time() - (expiry_timestamp - self.ttl_seconds)
                logger.debug(f"Cache HIT for key {key[:8]} (age: {age:.1f}s)")
                return intent_mapping
            else:
                # Remove expired entry
                del self._cache[key]
                logger.debug(f"Cache EXPIRED for key {key[:8]}")

        # Cache miss or expired
        self._cache_misses += 1
        return None

    def set(self, key: str, value: list) -> None:
        """
        Store intent mapping with expiry timestamp.

        Args:
            key: Cache key (SHA256 hash)
            value: Intent mapping to cache (list[IntentClassification])
        """
        # Prune cache if at capacity (evict oldest entry - first in dict)
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"Cache pruned oldest entry (size: {len(self._cache)})")

        # Store with expiry timestamp
        expiry_timestamp = time.time() + self.ttl_seconds
        self._cache[key] = (value, expiry_timestamp)
        logger.debug(f"Cache STORED key {key[:8]} (cache size: {len(self._cache)})")

    def _cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if expiry < current_time
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cache cleanup removed {len(expired_keys)} expired entries")

        return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, size
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": hit_rate,
            "size": len(self._cache),
        }

    def clear(self) -> None:
        """Clear the cache and reset statistics."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.debug("Cache cleared")

    def should_log_stats(self) -> bool:
        """
        Check if stats should be logged based on operation interval.

        Returns:
            True if stats should be logged, False otherwise
        """
        total_requests = self._cache_hits + self._cache_misses
        return total_requests > 0 and total_requests % self._stats_log_interval == 0


# Router error types for degraded-state handling
class RouterError(Exception):
    """Base exception for router errors."""
    pass


class RouterTimeoutError(RouterError):
    """Router LLM call timed out."""
    pass


class RouterQuotaError(RouterError):
    """Router LLM call quota exhausted."""
    pass


class RouterProxyError(RouterError):
    """Router LLM proxy unreachable."""
    pass


class RouterMalformedError(RouterError):
    """Router returned malformed JSON (after corrective retry)."""

    def __init__(self, parse_error: str, raw_output: str, retry_count: int = 0):
        self.parse_error = parse_error
        self.raw_output = raw_output
        self.retry_count = retry_count
        super().__init__(f"Malformed router output (retry {retry_count}): {parse_error}")


class IntentType(Enum):
    """Intent types that the router can classify."""
    STATUS = "status"
    ACTION = "action"
    BRAINSTORM = "brainstorm"
    LOOKUP = "lookup"
    REMINDER = "reminder"
    SELF_MODIFICATION = "self-modification"
    MONITORING_CONFIG = "monitoring-config"
    TASK_PROFILE = "task-profile"  # Escalate to NEEDLE bead
    CLARIFICATION = "clarification"  # Needs user input
    STUCK = "stuck"  # Stuck intent - task blocked by circuit breaker


@dataclass
class IntentClassification:
    """Result of intent classification."""
    intent_type: IntentType
    project_slug: str | None = None
    confidence: float = 1.0
    utterance_fragment: str = ""
    reasoning: str = ""
    urgency: str = "normal"  # critical, high, normal, low
    lookup_kind: str | None = None  # lookup intents only: 'logs' | 'config' | 'docs'


@dataclass
class RoutedIntent:
    """A routed intent ready for processing."""
    intent_id: str
    classification: IntentClassification
    session_id: str
    utterance: str
    # router_ms is measured once around classify_utterance() in route_utterance
    # (one LLM call per utterance) and shared across every intent thread from
    # that utterance — see Latency Budget & Instrumentation in docs/plan/plan.md.
    router_ms: int | None = None
    # json_parse_ms is the JSON parsing time from the router response (optional,
    # None for cached responses where no actual parsing occurred)
    json_parse_ms: int | None = None


# Path to the router segmentation prompt. Read from disk on each classify_utterance()
# call so edits to prompts/router.md take effect without a server restart (hot-reload),
# matching the pattern in src/synthesize/strand.py (SYNTHESIZE_PROMPT_PATH).
ROUTER_PROMPT_PATH = Path("/home/coding/aide-de-camp/prompts/router.md")

# Fallback used only if the prompt file cannot be read at runtime.
_ROUTER_PROMPT_FALLBACK = (
    "You are the Intent Router for aide-de-camp. Segment the utterance into "
    "distinct intent threads, classify each, and return ONLY a JSON array of "
    "intent objects."
)


class IntentRouter:
    """
    Intent Router classifies utterances and routes to appropriate strands.

    For task-profile intents, routes to escalate strand for bead creation.
    For other intents, routes to fetch + synthesize strands (TODO).

    Latency optimizations (adc-1kp7n):
    - LRU cache for repeated utterances (5-minute TTL)
    - Simplified prompt (removed confidence field/redundant rules)
    - Reduced max_tokens (80 vs 96) for faster generation
    - Temperature 0.0 for deterministic sampling
    - Dedicated 8s timeout for fail-fast behavior
    """

    def __init__(self, store=None, prompt_path: Optional[Path] = None, cache_ttl: int = 300):
        self.store = store
        self.prompt_path = prompt_path or ROUTER_PROMPT_PATH
        self._zai_client = None
        self._router_zai_client = None  # Dedicated client with 10s timeout
        self._reload_manager = None
        self._cache = IntentCache(ttl_seconds=cache_ttl)

    async def _get_zai_client(self):
        """Get or create ZAI client."""
        if self._zai_client is None:
            self._zai_client = get_zai_client()
        return self._zai_client

    async def _get_router_zai_client(self):
        """Get or create dedicated ZAI client for router with optimized settings for low latency."""
        if self._router_zai_client is None:
            from ..escalate.llm import get_router_zai_client
            # Router needs fail-fast behavior with aggressive timeout
            # 8-second timeout allows: ~2s connection + ~4-5s inference + ~1s parsing
            self._router_zai_client = get_router_zai_client(timeout=8.0)
        return self._router_zai_client

    def _get_utterance_hash(self, utterance: str) -> str:
        """Generate hash key for utterance caching."""
        import hashlib
        return hashlib.md5(utterance.encode()).hexdigest()

    def generate_cache_key(self, utterance: str, intent_type_context: str | None = None) -> str:
        """
        Generate a SHA256 hash key for caching based on utterance and optional context.

        Args:
            utterance: The user utterance to hash
            intent_type_context: Optional context string (e.g., intent type, session state)

        Returns:
            SHA256 hex digest (32 characters) of the combined utterance and context

        Examples:
            >>> generate_cache_key("check pods", "status")
            'a1b2c3d4e5f6...'  # 32-character hex string
            >>> generate_cache_key("check pods", None)  # Same as no context
            'differenthashvalue...'  # Different hash without context
        """
        import hashlib

        # Handle None/empty context gracefully - treat as empty string
        context = intent_type_context or ""

        # Combine utterance and context with a delimiter to avoid collisions
        # e.g., "test" + "status" vs "teststatus" + ""
        combined = f"{utterance}|{context}"

        # Generate SHA256 hash and return hex digest (32 characters)
        return hashlib.sha256(combined.encode()).hexdigest()

    def _get_cached_classification(self, utterance: str, session_id: str) -> list[IntentClassification] | None:
        """Check cache for existing classification."""
        cache_key = self.generate_cache_key(utterance, session_id)
        return self._cache.get(cache_key)

    def _cache_classification(self, utterance: str, session_id: str, classifications: list[IntentClassification]) -> None:
        """Cache classification result."""
        cache_key = self.generate_cache_key(utterance, session_id)
        self._cache.set(cache_key, classifications)

    def _get_cache_stats_string(self) -> str:
        """
        Get formatted cache statistics string for logging.

        Returns:
            Formatted string with cache hit rate and entries count
        """
        stats = self._cache.get_stats()
        return f"cache_hit_rate={stats['hit_rate']:.2f}% entries={stats['size']}"

    def _log_cache_stats_if_needed(self) -> None:
        """Log cache hit rate statistics periodically."""
        if self._cache.should_log_stats():
            stats = self._cache.get_stats()
            logger.info(
                f"Router cache statistics: "
                f"hits={stats['hits']} misses={stats['misses']} "
                f"hit_rate={stats['hit_rate']:.1f}% "
                f"total_requests={stats['hits'] + stats['misses']} "
                f"cache_size={stats['size']}"
            )

    def _clear_cache(self) -> None:
        """Clear the router cache. Used primarily for testing and diagnostics."""
        self._cache.clear()

    async def _get_store(self):
        """Get or create session store."""
        if self.store is None:
            self.store = get_store()
        return self.store

    def _get_reload_manager(self):
        """Get or create the hot-reload manager (lazy singleton)."""
        if self._reload_manager is None:
            self._reload_manager = get_reload_manager()
        return self._reload_manager

    def _load_router_prompt(self) -> str:
        """
        Load the router segmentation prompt via hot-reload manager.

        Uses the cached prompt from the hot-reload manager, which only reloads
        when the file mtime changes. This avoids disk I/O on every classification.
        """
        try:
            return self._get_reload_manager().get_prompt("router")
        except Exception as e:
            logger.error(f"Failed to load router prompt: {e}")
            return _ROUTER_PROMPT_FALLBACK

    def _build_system_prompt(self) -> str:
        """Build the system prompt from the router segmentation prompt.

        Latency optimization: Removed urgency prompt splicing from hot path.
        The router still classifies urgency based on core intent patterns,
        without the extra token overhead of separate urgency rules.
        """
        return self._load_router_prompt()

    async def classify_utterance(
        self,
        utterance: str,
        session_id: str,
        retry_on_malformed: bool = True,
    ) -> tuple[list[IntentClassification], dict]:
        """
        Classify an utterance into intents.

        Uses LLM to segment and classify the utterance.

        Args:
            utterance: The user utterance
            session_id: Session ID for context
            retry_on_malformed: If True, perform one corrective retry on JSON parse failure

        Returns:
            Tuple of (classifications list, timing_breakdown dict)

        Raises:
            RouterTimeoutError: LLM call timed out
            RouterQuotaError: LLM quota exhausted
            RouterProxyError: LLM proxy unreachable
            RouterMalformedError: Malformed JSON after corrective retry
        """
        # OPTIMIZATION 1: Check cache first (eliminates redundant LLM calls)
        cache_check_start = time.perf_counter()
        cached_result = self._get_cached_classification(utterance, session_id)
        cache_check_ms = (time.perf_counter() - cache_check_start) * 1000

        if cached_result is not None:
            # Log cache statistics periodically
            self._log_cache_stats_if_needed()

            # Log cache hit with cache statistics in structured timing format
            cache_stats = self._get_cache_stats_string()
            logger.debug(
                f"router_timing phase=cache_check duration_ms={cache_check_ms:.2f} "
                f"cached=True intents={len(cached_result)} {cache_stats}"
            )
            logger.info(
                f"Cache HIT: {len(cached_result)} intents ({cache_check_ms:.0f}ms)"
            )

            # Return empty timing breakdown for cached results (no actual LLM call was made)
            empty_breakdown = {
                "cached": True,
                "prompt_construction_ms": 0,
                "proxy_call_ms": 0,
                "proxy_network_ms": 0,
                "proxy_inference_ms": 0,
                "json_parse_ms": 0,
                "process_ms": 0,
                "total_ms": 0,
                "intents_count": len(cached_result),
                "json_parse_ms": 0,  # No parsing occurred for cached results
            }
            return cached_result, empty_breakdown

        # Track retry attempt for malformed JSON
        retry_count = 0
        raw_response = None

        try:
            # Measure total classification time
            classify_start = time.perf_counter()

            # Use dedicated router client with 10s timeout for fail-fast behavior
            client = await self._get_router_zai_client()

            # Measure prompt construction time (template rendering, message formatting)
            # This isolates client-side preparation cost from network and inference time
            prompt_start = time.perf_counter()

            # Build user message
            user_message = f"Classify this utterance:\n\n{utterance}"

            logger.info(f"Classifying utterance for session {session_id}")

            # Build system prompt from prompts/router.md
            # (hot-reload enabled via reload manager)
            system_prompt = self._build_system_prompt()

            prompt_ms = (time.perf_counter() - prompt_start) * 1000

            # Measure ZAI proxy call time (network + model inference)
            # The LLM client now returns timing breakdown separating network latency from model inference
            proxy_start = time.perf_counter()
            response_data = await client.call_simple(
                system_prompt=system_prompt,
                user_message=user_message,
                model=ModelClass.SONNET.value,
                max_tokens=128,  # OPTIMIZATION 2: Increased from 80 to 128 - supports multi-intent responses (typically 100-120 tokens for 2-3 intents)
                temperature=0.0,
                return_timing=True,  # Request timing breakdown from LLM client
            )
            proxy_ms = (time.perf_counter() - proxy_start) * 1000

            # Extract content and timing from response
            # response_data is now a dict with content and timing breakdown
            response = response_data.get("content", "")
            timing_network_ms = response_data.get("timing_network_ms")
            timing_inference_ms = response_data.get("timing_inference_ms")

            # Store raw response for error reporting
            raw_response = response

            # Calculate model inference time: proxy response time - network time
            # This gives us the actual model inference duration by subtracting network RTT
            calculated_inference_ms = None
            if timing_network_ms is not None:
                calculated_inference_ms = proxy_ms - timing_network_ms

            # Measure JSON parsing time
            parse_start = time.perf_counter()
            try:
                # Fast-path optimized JSON parsing:
                # - Early fence detection skips processing for clean JSON (common case)
                # - orjson provides 2-3x faster parsing than standard json
                # - Single-pass fence stripping with position-based search
                # See src/llm/response_parser.py for implementation details
                intents_data = parse_llm_response(response, strip_fences=True, expect_json=True)
            except ParseLLMError as e:
                # Already has raw_response attached; just re-raise
                raise e
            parse_ms = (time.perf_counter() - parse_start) * 1000

            # Store json_parse_ms in RoutedIntent for downstream instrumentation
            # This allows tracking parsing time separately from router_ms
            json_parse_ms = parse_ms

            # Measure classification processing time
            process_start = time.perf_counter()
            classifications = []

            for intent_data in intents_data:
                # Map string to IntentType enum
                intent_type_str = intent_data.get("intent_type", "status")
                try:
                    intent_type = IntentType(intent_type_str)
                except ValueError:
                    logger.warning(f"Unknown intent type: {intent_type_str}")
                    intent_type = IntentType.STATUS

                classification = IntentClassification(
                    intent_type=intent_type,
                    project_slug=intent_data.get("project_slug"),
                    confidence=float(intent_data.get("confidence", 0.8)),
                    utterance_fragment=intent_data.get("utterance_fragment", utterance),
                    reasoning=intent_data.get("reasoning", ""),
                    urgency=intent_data.get("urgency", "normal"),
                    lookup_kind=intent_data.get("lookup_kind") if intent_type == IntentType.LOOKUP else None,
                )
                classifications.append(classification)
            process_ms = (time.perf_counter() - process_start) * 1000

            total_ms = (time.perf_counter() - classify_start) * 1000

            # Log detailed timing breakdown for latency profiling at DEBUG level
            # Structured format: phase=duration_ms for easy parsing
            network_str = f"{timing_network_ms:.2f}" if timing_network_ms is not None else "N/A"
            calculated_inference_str = f"{calculated_inference_ms:.2f}" if calculated_inference_ms is not None else "N/A"
            cache_stats = self._get_cache_stats_string()
            logger.debug(
                f"router_timing phase=prompt_construction duration_ms={prompt_ms:.2f} "
                f"phase=proxy_call duration_ms={proxy_ms:.2f} "
                f"phase=proxy_network duration_ms={network_str} "
                f"phase=proxy_inference duration_ms={calculated_inference_str} "
                f"phase=json_parse duration_ms={parse_ms:.2f} "
                f"phase=process duration_ms={process_ms:.2f} "
                f"phase=total duration_ms={total_ms:.2f} "
                f"intents_count={len(classifications)} {cache_stats}"
            )
            logger.info(
                f"Classified {len(classifications)} intents from utterance ({total_ms:.0f}ms total)"
            )

            logger.info(f"Classified {len(classifications)} intents from utterance")

            # Build timing breakdown for storage
            # Now includes separate network and inference timing measured by LLM client
            timing_breakdown = {
                "cached": False,  # Cache miss - result from fresh ZAI proxy call
                "prompt_construction_ms": round(prompt_ms, 2),
                "proxy_call_ms": round(proxy_ms, 2),  # Total round-trip time (network + inference)
                "proxy_network_ms": round(timing_network_ms, 2) if timing_network_ms is not None else None,
                "proxy_inference_ms": round(calculated_inference_ms, 2) if calculated_inference_ms is not None else None,
                "json_parse_ms": round(parse_ms, 2),
                "process_ms": round(process_ms, 2),
                "total_ms": round(total_ms, 2),
                "intents_count": len(classifications),
            }

            # OPTIMIZATION 1 (cont): Cache successful classifications
            self._cache_classification(utterance, session_id, classifications)

            # Log cache statistics periodically (including this cache miss)
            self._log_cache_stats_if_needed()

            return classifications, timing_breakdown

        except ParseLLMError as e:
            """
            First parsing attempt failed - implement corrective retry.

            Router uses corrective retry because it's the first step in the pipeline.
            A malformed router response cascades to everything downstream.
            One retry is justified because it's cheap (same prompt, 2048 tokens).
            """
            logger.error(f"Failed to parse router response: {e}")
            raw_output = e.raw_response or raw_response  # Preserve for error reporting

            # Implement one corrective retry on malformed JSON
            if retry_on_malformed and retry_count == 0:
                logger.info("Malformed JSON detected, attempting corrective retry...")
                retry_count += 1
                try:
                    # Retry once with same parameters
                    classifications, _ = await self.classify_utterance(
                        utterance=utterance,
                        session_id=session_id,
                        retry_on_malformed=False,  # Prevent infinite retry
                    )
                    return classifications, _
                except ParseLLMError as retry_e:
                    # Retry also failed - raise RouterMalformedError
                    raise RouterMalformedError(
                        parse_error=str(retry_e),
                        raw_output=retry_e.raw_response or raw_response,
                        retry_count=retry_count,
                    ) from retry_e

            # No retry allowed or retry failed - raise RouterMalformedError
            raise RouterMalformedError(
                parse_error=str(e),
                raw_output=raw_output,
                retry_count=retry_count,
            ) from e

        except (LLMTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Router LLM call timed out: {e}")
            raise RouterTimeoutError(f"Router LLM call timed out: {e}") from e

        except (LLMRateLimitError,) as e:
            logger.error(f"Router LLM call quota exhausted: {e}")
            raise RouterQuotaError(f"Router LLM call quota exhausted: {e}") from e

        except (LLMError, httpx.HTTPError) as e:
            logger.error(f"Router LLM proxy unreachable: {e}")
            raise RouterProxyError(f"Router LLM proxy unreachable: {e}") from e

        except Exception as e:
            logger.error(f"Classification failed with unexpected error: {e}")
            # Wrap unknown errors as RouterProxyError for graceful degradation
            raise RouterProxyError(f"Router LLM call failed: {e}") from e

    async def route_utterance(
        self,
        utterance: str,
        utterance_id: str,
        session_id: str,
    ) -> list[RoutedIntent]:
        """
        Route an utterance to appropriate strands.

        Classifies the utterance and routes each intent to the correct strand.

        Args:
            utterance: The user utterance
            utterance_id: Unique ID for this utterance
            session_id: Session ID

        Returns:
            List of RoutedIntent objects

        Raises:
            RouterError: If router fails and broadcasts error event
        """
        # Generate a fallback intent_id for error reporting
        error_intent_id = str(uuid.uuid4())

        try:
            # Classify the utterance (one LLM call per utterance — the router stage
            # is shared across every intent thread it produces, so its duration is
            # measured once here and stamped onto each RoutedIntent).
            classify_start = time.monotonic()
            classifications, timing_breakdown = await self.classify_utterance(utterance, session_id)
            router_ms = int((time.monotonic() - classify_start) * 1000)

            # Store router timing breakdown in utterance record
            try:
                store = await self._get_store()
                await store.update_utterance_router_timing(utterance_id, timing_breakdown)
                logger.info(f"Stored router timing breakdown for utterance {utterance_id[:8]}")
            except Exception as e:
                logger.warning(f"Failed to store router timing breakdown: {e}")
                # Non-fatal: continue with routing

            # Extract json_parse_ms from timing breakdown (0 for cache hits, actual ms for cache misses)
            json_parse_ms = timing_breakdown.get("json_parse_ms", 0)

            routed_intents = []
            for classification in classifications:
                # Create intent ID
                intent_id = str(uuid.uuid4())

                routed_intent = RoutedIntent(
                    intent_id=intent_id,
                    classification=classification,
                    session_id=session_id,
                    utterance=classification.utterance_fragment,
                    router_ms=router_ms,
                    json_parse_ms=json_parse_ms,  # Track parsing time for this intent thread (0 if cached)
                )
                routed_intents.append(routed_intent)

            return routed_intents

        except RouterMalformedError as e:
            # Malformed JSON after corrective retry - broadcast clarification card
            logger.error(f"Router malformed after retry: {e.parse_error}")
            handler = get_degraded_state_handler()
            await handler.broadcast_clarification_card(
                utterance=utterance,
                intent_id=error_intent_id,
                session_id=session_id,
                parse_error=e.parse_error,
                retry_count=e.retry_count,
                raw_output_snippet=e.raw_output[:200] if e.raw_output else None,
            )
            raise  # Re-raise so caller knows routing failed

        except RouterTimeoutError as e:
            # Router LLM timeout - broadcast router_unavailable
            logger.error(f"Router timeout: {e}")
            handler = get_degraded_state_handler()
            await handler.broadcast_router_unavailable(
                utterance=utterance,
                intent_id=error_intent_id,
                session_id=session_id,
                error_reason="timeout",
            )
            raise  # Re-raise so caller knows routing failed

        except RouterQuotaError as e:
            # Router quota exhausted - broadcast router_unavailable
            logger.error(f"Router quota exhausted: {e}")
            handler = get_degraded_state_handler()
            await handler.broadcast_router_unavailable(
                utterance=utterance,
                intent_id=error_intent_id,
                session_id=session_id,
                error_reason="quota_exhausted",
            )
            raise  # Re-raise so caller knows routing failed

        except RouterProxyError as e:
            # Router proxy unreachable - broadcast router_unavailable
            logger.error(f"Router proxy error: {e}")
            handler = get_degraded_state_handler()
            await handler.broadcast_router_unavailable(
                utterance=utterance,
                intent_id=error_intent_id,
                session_id=session_id,
                error_reason="proxy_down",
            )
            raise  # Re-raise so caller knows routing failed

    async def process_intent(
        self,
        routed_intent: RoutedIntent,
    ) -> dict:
        """
        Process a routed intent by dispatching to the appropriate strand.

        Args:
            routed_intent: The routed intent to process

        Returns:
            Result dictionary with status and data
        """
        classification = routed_intent.classification

        # Capture per-stage timings for this dispatch and persist one
        # dispatch_timings row (see Latency Budget & Instrumentation). Each
        # branch records the stages it measures; router_ms is shared across
        # the utterance's threads and was stamped on the RoutedIntent. Capture
        # is non-fatal: a persistence failure logs and moves on, never breaking
        # the dispatch itself.
        timings = DispatchTimings()
        timings.record("router_ms", routed_intent.router_ms)
        timings.record("json_parse_ms", routed_intent.json_parse_ms)  # Track JSON parsing time

        # Honesty guards for unimplemented intents
        if classification.intent_type == IntentType.ACTION:
            # Action executor is NOT BUILT — broadcast design-only card
            handler = get_degraded_state_handler()
            await handler.broadcast_action_design_only(
                utterance=routed_intent.utterance,
                intent_id=routed_intent.intent_id,
                session_id=routed_intent.session_id,
                project_slug=classification.project_slug,
            )

            # Update intent status to reflect the design-only state
            store = await self._get_store()
            await store.update_intent_status(
                routed_intent.intent_id,
                "resolved",
                "Action execution is design-only — executor not built",
            )

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "design_only",
                "message": "Action execution is not yet available",
            }

        if classification.intent_type == IntentType.REMINDER:
            # Reminders are NOT YET IMPLEMENTED — broadcast clarification card
            handler = get_degraded_state_handler()
            await handler.broadcast_reminder_unavailable(
                utterance=routed_intent.utterance,
                intent_id=routed_intent.intent_id,
                session_id=routed_intent.session_id,
            )

            # Update intent status to reflect that reminders are unavailable
            store = await self._get_store()
            await store.update_intent_status(
                routed_intent.intent_id,
                "resolved",
                "Reminders are not available yet",
            )

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "unavailable",
                "message": "Reminders are not available yet",
            }

        try:
            # For task-profile intents, escalate to bead
            if classification.intent_type == IntentType.TASK_PROFILE:
                result = await self._escalate_to_bead(routed_intent, timings)
            else:
                # For other intents, fetch then synthesize
                result = await self._fetch_and_synthesize(routed_intent, timings)
        except Exception:
            # Persist whatever was captured before the failure, then re-raise.
            await self._persist_timings(routed_intent.intent_id, timings)
            raise

        await self._persist_timings(routed_intent.intent_id, timings)
        return result

    async def _persist_timings(
        self,
        intent_id: str,
        timings: DispatchTimings,
    ) -> None:
        """Persist the captured dispatch timings. Non-fatal on error."""
        try:
            store = await self._get_store()
            await store.record_dispatch_timings(intent_id, **timings.to_fields())
        except Exception as e:
            logger.warning(f"dispatch timings not recorded for {intent_id}: {e}")

    async def _fetch_and_synthesize(
        self,
        routed_intent: RoutedIntent,
        timings: DispatchTimings,
    ) -> dict:
        """
        Fetch context then synthesize into structured result.

        Args:
            routed_intent: The routed intent to process
            timings: Per-stage timing collector; records fetch_first_source_ms,
                fetch_total_ms, and synthesize_total_ms.

        Returns:
            Result dictionary with synthesized data
        """
        classification = routed_intent.classification

        logger.info(
            f"Fetching and synthesizing intent {routed_intent.intent_id} "
            f"(type: {classification.intent_type.value})"
        )

        try:
            # Step 1: Fetch context — resolve project slug to local repo path
            fetch_intent_type = self._map_intent_type(
                classification.intent_type,
                classification.lookup_kind
            )

            from ..environment.discovery import get_registry
            from ..registry import get_project
            repo_path = None
            ssh_target = None
            host_alias = None
            registry = get_registry()
            if registry and classification.project_slug:
                entry = registry.lookup(classification.project_slug)
                if entry:
                    repo_path = str(entry.path)
                    ssh_target = entry.ssh_target
                    host_alias = entry.host
                    location = entry.display_path
                    logger.info(f"Resolved '{classification.project_slug}' → {location}")
                else:
                    logger.info(f"No repo found for slug '{classification.project_slug}'")

            # YAML registry entry carries cluster/namespace/argocd_app — cluster
            # drives ArgoCD endpoint resolution (bead adc-1ejh: the fetch strand
            # resolves {argocd_api} from `cluster` via config/clusters.yaml).
            # argocd_app defaults to the slug when omitted (see _fetch_argocd_app).
            project_cfg = (
                get_project(classification.project_slug)
                if classification.project_slug else None
            )

            fetch_request = FetchRequest(
                intent_id=routed_intent.intent_id,
                intent_type=fetch_intent_type,
                session_id=routed_intent.session_id,
                context=FetchContext(
                    project_slug=classification.project_slug,
                    session_id=routed_intent.session_id,
                    repo_path=repo_path,
                    ssh_target=ssh_target,
                    host_alias=host_alias,
                    cluster=project_cfg.get("cluster") if project_cfg else None,
                    namespace=project_cfg.get("namespace") if project_cfg else None,
                    app_name=project_cfg.get("argocd_app") if project_cfg else None,
                ),
            )

            # fetch_first_source_ms = time from fetch start to the first source
            # resolving (success/fail/timeout — the first progress state on the
            # pending card). fetch_total_ms = the fetch window close.
            fetch_start = timings.clock()
            first_source_at: list[float | None] = [None]
            total_sources = len(get_fetch_commands(fetch_intent_type))
            completed_sources: list[int] = [0]

            def _on_fetch_progress(source, result) -> None:
                """Track fetch timing and broadcast progress events to pending card."""
                # Track first source timing for fetch_first_source_ms metric
                if first_source_at[0] is None:
                    first_source_at[0] = timings.clock()

                # Increment completed count
                completed_sources[0] += 1

                # Broadcast progress event to canvas ('3/5 sources in')
                asyncio.create_task(broadcast_fetch_progress(
                    intent_id=routed_intent.intent_id,
                    session_id=routed_intent.session_id,
                    completed=completed_sources[0],
                    total=total_sources,
                    source_name=source.value,
                    source_status=result.status,
                ))

            fetch_result = await execute_fetch(fetch_request, _on_fetch_progress)
            timings.record("fetch_total_ms", fetch_result.total_duration_ms)
            if first_source_at[0] is not None:
                timings.record(
                    "fetch_first_source_ms",
                    timings.elapsed_ms(fetch_start, first_source_at[0]),
                )

            # Check for terminal failure: ALL sources failed (Degraded-State UX)
            if fetch_result.terminal_failure == "all_sources_failed":
                logger.error(
                    f"All fetch sources failed for intent {routed_intent.intent_id}: "
                    f"{len(fetch_result.coverage.failed)} failed, "
                    f"{len(fetch_result.coverage.timed_out)} timed out"
                )

                # Build failed sources list for error event
                failed_sources = []
                for source, result in fetch_result.sources.items():
                    failed_sources.append({
                        "source": source.value,
                        "status": result.status,
                        "error": result.error,
                    })

                # Broadcast all_sources_failed error event
                handler = get_degraded_state_handler()
                await handler.broadcast_all_sources_failed(
                    intent_id=routed_intent.intent_id,
                    intent_type=classification.intent_type.value,
                    session_id=routed_intent.session_id,
                    utterance=routed_intent.utterance,
                    failed_sources=failed_sources,
                )

                # Update intent status to failed
                store = get_store()
                await store.update_intent_status(
                    routed_intent.intent_id,
                    "failed",
                    "All fetch sources failed",
                )

                return {
                    "intent_id": routed_intent.intent_id,
                    "intent_type": classification.intent_type.value,
                    "status": "failed",
                    "error": "all_sources_failed",
                    "message": "No data — all required sources failed",
                    "terminal_failure": "all_sources_failed",
                }

            # Check for required source failures (terminal condition)
            required_sources_failed = [
                s for s in fetch_result.coverage.failed
                if any(cmd.source == s and cmd.required
                       for cmd in get_fetch_commands(fetch_result.intent_type))
            ]

            if required_sources_failed:
                failure_reason = f"Required data sources failed: {', '.join(s.value for s in required_sources_failed)}"
                logger.error(f"Required sources failed for intent {routed_intent.intent_id}: {failure_reason}")

                # Handle terminal failure
                await self._handle_terminal_failure_for_intent(
                    routed_intent=routed_intent,
                    failure_reason=failure_reason,
                    error_type="required_source_failure",
                )

                return {
                    "intent_id": routed_intent.intent_id,
                    "intent_type": classification.intent_type.value,
                    "status": "failed",
                    "error": failure_reason,
                    "message": "Required sources failed - cannot proceed",
                }

            # Step 2: Synthesize result
            synthesize_request = SynthesizeRequest(
                intent_id=routed_intent.intent_id,
                intent_type=fetch_intent_type,
                utterance=routed_intent.utterance,
                project_slug=classification.project_slug,
                fetched_context=fetch_result,
                urgency=classification.urgency,
            )

            synth_start = timings.clock()
            try:
                synthesize_result = await synthesize_intent(synthesize_request)
            except Exception as synth_e:
                # ZAI failure at synthesize stage - broadcast degraded_raw_data
                # (Degraded-State UX: fetched data is never discarded)
                logger.error(
                    f"Synthesize failed for intent {routed_intent.intent_id}: {synth_e}"
                )

                handler = get_degraded_state_handler()
                await handler.broadcast_degraded_raw_data(
                    intent_id=routed_intent.intent_id,
                    intent_type=classification.intent_type.value,
                    session_id=routed_intent.session_id,
                    utterance=routed_intent.utterance,
                    fetched_context=fetch_result,
                    error_reason=str(synth_e),
                )

                # Update intent status to failed
                store = get_store()
                await store.update_intent_status(
                    routed_intent.intent_id,
                    "failed",
                    f"Synthesize failed: {synth_e}",
                )

                return {
                    "intent_id": routed_intent.intent_id,
                    "intent_type": classification.intent_type.value,
                    "status": "failed",
                    "error": "synthesize_failed",
                    "message": "Summary unavailable — showing raw fetch data",
                    "degraded": True,
                }

            timings.record("synthesize_total_ms", timings.elapsed_ms(synth_start))
            # synthesize_first_token_ms is not measurable on the current
            # call_simple path (no token stream) and is left NULL until the
            # synthesize strand streams — see src/instrument/timings.py.

            # Persist result to session store so loadTopics() can display it
            store = get_store()
            _topic_type_map = {
                IntentType.ACTION: "project",
                IntentType.TASK_PROFILE: "project",
            }
            topic_type = _topic_type_map.get(classification.intent_type, "research")
            topic_id, _ = await store.find_or_create_topic(
                label=classification.utterance_fragment or routed_intent.utterance[:80],
                topic_type=topic_type,
                project_slugs=[classification.project_slug] if classification.project_slug else [],
                session_id=routed_intent.session_id,
            )
            await store.link_intent_to_topic(routed_intent.intent_id, topic_id)

            # Derive result_type from intent classification (includes lookup_kind for lookups)
            result_type = derive_result_type(
                intent_type=classification.intent_type.value,
                project_slug=classification.project_slug,
                lookup_kind=classification.lookup_kind,
            )

            result_id = await store.create_result(
                intent_id=routed_intent.intent_id,
                topic_id=topic_id,
                session_id=routed_intent.session_id,
                summary=synthesize_result.summary,
                data=synthesize_result.data,
                urgency=synthesize_result.urgency.value,
                result_type=result_type,
            )

            # Render card via hot-path selector (deterministic, no LLM)
            renderer = get_renderer()
            render_outcome = renderer.render(
                result_id=result_id,
                result_type=result_type,
                result_data=synthesize_result.data,
                summary=synthesize_result.summary,
                urgency=synthesize_result.urgency.value,
            )

            # Update result's card_fallback flag so client knows which path to take
            await store.update_result_card_fallback(result_id, render_outcome.card_fallback)

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "resolved",
                "topic_id": topic_id,
                "result_id": result_id,
                "data": synthesize_result.data,
                "summary": synthesize_result.summary,
                "urgency": synthesize_result.urgency.value,
                "coverage": synthesize_result.coverage,
                "caveats": synthesize_result.caveats,
                "card_fallback": render_outcome.card_fallback,
                "rendered_html": render_outcome.rendered_html,
                "component_id": render_outcome.component_id,
                "message": "Intent synthesized successfully",
            }

        except Exception as e:
            logger.error(f"Fetch/synthesize failed for intent {routed_intent.intent_id}: {e}")

            # Detect terminal failure and handle appropriately
            await self._handle_terminal_failure_for_intent(
                routed_intent=routed_intent,
                failure_reason=str(e),
                error_type="worker_crash",
            )

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "failed",
                "error": str(e),
                "message": "Fetch/synthesize failed - terminal error",
            }

    async def _handle_terminal_failure_for_intent(
        self,
        routed_intent: RoutedIntent,
        failure_reason: str,
        error_type: str,
        bead_ref: str | None = None,
    ) -> None:
        """
        Handle terminal failure for a routed intent.

        Args:
            routed_intent: The intent that failed
            failure_reason: Human-readable failure reason
            error_type: Type of error (worker_crash, invalid_input, required_source_failure)
            bead_ref: Associated bead reference (if applicable)
        """
        from ..escalate.handler import handle_terminal_failure

        # Get or create topic for failed card
        try:
            store = await self._get_store()
            topic_id, _ = await store.find_or_create_topic(
                label=f"Failed: {routed_intent.utterance[:80]}",
                session_id=routed_intent.session_id,
                topic_type="exception",
            )
        except Exception as e:
            logger.warning(f"Failed to create topic for failed card: {e}")
            topic_id = None

        # Handle terminal failure (updates intent status, stores in bead_watch, broadcasts SSE)
        await handle_terminal_failure(
            intent_id=routed_intent.intent_id,
            session_id=routed_intent.session_id,
            topic_id=topic_id,
            failure_reason=failure_reason,
            error_type=error_type,
            bead_ref=bead_ref,
        )

    def _map_intent_type(self, intent_type: IntentType, lookup_kind: str | None = None) -> FetchIntentType:
        """Map router IntentType to fetch IntentType.

        For lookup intents, route to the subtype-specific fetch matrix based on lookup_kind.
        """
        # Map enum values by string
        type_map = {
            IntentType.STATUS: FetchIntentType.STATUS,
            IntentType.ACTION: FetchIntentType.ACTION,
            IntentType.BRAINSTORM: FetchIntentType.BRAINSTORM,
            IntentType.LOOKUP: FetchIntentType.LOOKUP,
            IntentType.REMINDER: FetchIntentType.REMINDER,
            IntentType.SELF_MODIFICATION: FetchIntentType.SELF_MODIFICATION,
            IntentType.MONITORING_CONFIG: FetchIntentType.MONITORING_CONFIG,
            IntentType.STUCK: FetchIntentType.STUCK,
        }

        # For lookup intents with lookup_kind, route to the subtype-specific matrix
        if intent_type == IntentType.LOOKUP and lookup_kind:
            if lookup_kind == "logs":
                return FetchIntentType.LOOKUP_LOGS
            elif lookup_kind == "config":
                return FetchIntentType.LOOKUP_CONFIG
            elif lookup_kind == "docs":
                return FetchIntentType.LOOKUP_DOCS

        return type_map.get(intent_type, FetchIntentType.STATUS)

    async def _check_fence_for_bead(
        self,
        bead_ref: str,
    ) -> dict | None:
        """
        Check if a bead has been fenced (has last_refusal_reason or fenced_at set).

        Args:
            bead_ref: The bead reference to check

        Returns:
            Fence context dict with bead_id, refusal_reason, refusal_count, fenced_at
            if fenced, None otherwise.
        """
        try:
            store = await self._get_store()
            bead_watch = await store.get_bead_watch(bead_ref)

            if not bead_watch:
                return None

            # Check if bead is fenced (has last_refusal_reason or fenced_at)
            last_refusal_reason = bead_watch.get("last_refusal_reason")
            fenced_at = bead_watch.get("fenced_at")
            refusal_count = bead_watch.get("refusal_count", 0)

            if last_refusal_reason or fenced_at:
                # Bead is fenced - extract fence context
                return {
                    "bead_id": bead_ref,
                    "refusal_reason": last_refusal_reason or "Fenced (no reason provided)",
                    "refusal_count": refusal_count,
                    "fenced_at": fenced_at,
                }

            return None

        except Exception as e:
            logger.warning(f"Error checking fence status for bead {bead_ref}: {e}")
            return None

    async def _create_stuck_card_from_fence(
        self,
        routed_intent: RoutedIntent,
        fence_context: dict,
    ) -> dict:
        """
        Create a stuck card when a fenced bead is detected during intent routing.

        Args:
            routed_intent: The routed intent
            fence_context: Fence context from _check_fence_for_bead

        Returns:
            Result dictionary with stuck card details
        """
        from datetime import datetime

        bead_id = fence_context["bead_id"]
        refusal_reason = fence_context["refusal_reason"]
        refusal_count = fence_context["refusal_count"]

        logger.info(
            f"Creating stuck card for fenced bead {bead_id} "
            f"(intent {routed_intent.intent_id})"
        )

        try:
            store = await self._get_store()

            # Update intent type to 'stuck' and status to 'stuck'
            await store.update_intent_type_and_status(
                intent_id=routed_intent.intent_id,
                intent_type="stuck",
                status="stuck",
            )

            # Get or create topic for this stuck card
            topic_type = "project" if routed_intent.classification.project_slug else "research"
            topic_id, _ = await store.find_or_create_topic(
                label=f"Fenced: {routed_intent.utterance[:80]}",
                topic_type=topic_type,
                project_slugs=[routed_intent.classification.project_slug] if routed_intent.classification.project_slug else [],
                session_id=routed_intent.session_id,
            )

            # Link intent to topic
            await store.link_intent_to_topic(routed_intent.intent_id, topic_id)

            # Create stuck result
            summary = f"Task stuck — needs your input"
            data = {
                "bead_id": bead_id,
                "stuck_reason": refusal_reason,
                "refusal_count": refusal_count,
                "message": f"This task has been blocked after {refusal_count} refusals.",
                "action_hint": "Review the bead and provide the missing information or context needed to proceed.",
                "fence_detected_during": "intent_routing",
            }

            # Derive result_type from original intent classification (not "stuck" state, includes lookup_kind)
            result_type = derive_result_type(
                intent_type=routed_intent.classification.intent_type.value,
                project_slug=routed_intent.classification.project_slug,
                lookup_kind=routed_intent.classification.lookup_kind,
            )

            result_id = await store.create_result(
                intent_id=routed_intent.intent_id,
                topic_id=topic_id,
                session_id=routed_intent.session_id,
                summary=summary,
                data=data,
                urgency="high",
                result_type=result_type,
            )

            # Render stuck card via hot-path selector (deterministic, no LLM)
            renderer = get_renderer()
            render_outcome = renderer.render(
                result_id=result_id,
                result_type=result_type,
                result_data=data,
                summary=summary,
                urgency="high",
            )

            # Update result's card_fallback flag
            await store.update_result_card_fallback(result_id, render_outcome.card_fallback)

            logger.info(f"Created stuck card {result_id} for fenced bead {bead_id}")

            # Broadcast task_stuck event via SSE
            broadcaster = get_broadcaster()
            await broadcaster.broadcast(
                SSEEvent(
                    event_type=EventType.TASK_STUCK,
                    data={
                        "bead_id": bead_id,
                        "stuck_reason": refusal_reason,
                        "refusal_count": refusal_count,
                        "intent_id": routed_intent.intent_id,
                        "session_id": routed_intent.session_id,
                        "topic_id": topic_id,
                        "timestamp": int(datetime.now().timestamp()),
                    },
                    target_session_id=routed_intent.session_id,
                )
            )

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": "stuck",
                "status": "stuck",
                "bead_id": bead_id,
                "topic_id": topic_id,
                "result_id": result_id,
                "stuck_reason": refusal_reason,
                "refusal_count": refusal_count,
                "message": "Fenced bead detected during intent routing",
            }

        except Exception as e:
            logger.error(f"Failed to create stuck card from fence: {e}")
            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": "stuck",
                "status": "error",
                "error": str(e),
                "message": "Failed to create stuck card from fence context",
            }

    async def _escalate_to_bead(
        self,
        routed_intent: RoutedIntent,
        timings: DispatchTimings,
    ) -> dict:
        """
        Escalate a task-profile intent to a NEEDLESS bead.

        Args:
            routed_intent: The routed intent to escalate
            timings: Per-stage timing collector; records escalate_ms.

        Returns:
            Result dictionary with pending card or stuck card if fence detected
        """
        classification = routed_intent.classification

        # Step 1: Check for existing fenced beads in the session before escalating
        # This detects fence events when last_refusal_reason is set on existing beads
        try:
            store = await self._get_store()
            fenced_beads = await store.get_fenced_beads_for_session(
                routed_intent.session_id
            )

            # If there are fenced beads, extract fence context and create stuck card
            if fenced_beads:
                # Get the most recently fenced bead
                most_recent_fenced = fenced_beads[0]
                bead_ref = most_recent_fenced["bead_ref"]
                refusal_reason = most_recent_fenced.get("last_refusal_reason", "Fenced (no reason provided)")
                refusal_count = most_recent_fenced.get("refusal_count", 0)

                fence_context = {
                    "bead_id": bead_ref,
                    "refusal_reason": refusal_reason,
                    "refusal_count": refusal_count,
                    "fenced_at": most_recent_fenced.get("fenced_at"),
                }

                logger.info(
                    f"Detected fenced bead {bead_ref} for session {routed_intent.session_id} "
                    f"(intent {routed_intent.intent_id})"
                )

                # Create stuck card with fence context
                return await self._create_stuck_card_from_fence(
                    routed_intent, fence_context
                )

        except Exception as e:
            logger.warning(f"Error checking for fenced beads: {e}")
            # Continue to escalation if fence check fails

        # Step 2: No fenced beads detected - proceed with escalation
        # Build escalate request
        escalate_request = EscalateRequest(
            intent_id=routed_intent.intent_id,
            session_id=routed_intent.session_id,
            utterance=routed_intent.utterance,
            intent_type=classification.intent_type.value,
            project_slug=classification.project_slug,
            context={
                "reasoning": classification.reasoning,
                "urgency": classification.urgency,
            },
            metadata={
                "urgency": classification.urgency,
                "confidence": classification.confidence,
            },
        )

        try:
            # Escalate to bead — escalate_ms budgets formulation + validation +
            # bf create (task-profile dispatches only; NULL for hot-path rows).
            esc_start = timings.clock()
            result = await escalate_intent(escalate_request)
            timings.record("escalate_ms", timings.elapsed_ms(esc_start))

            # Check if the created bead is immediately fenced (race condition:
            # watcher may have fenced it between escalate request and now)
            if result.bead_id:
                fence_context = await self._check_fence_for_bead(result.bead_id)
                if fence_context:
                    logger.info(
                        f"Detected immediate fence for bead {result.bead_id} "
                        f"(intent {routed_intent.intent_id})"
                    )
                    # Return stuck card instead of pending card
                    return await self._create_stuck_card_from_fence(
                        routed_intent, fence_context
                    )

            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "escalated",
                "bead_id": result.bead_id,
                "pending_card": result.pending_card,
                "message": f"Escalated to bead {result.bead_id}",
            }

        except Exception as e:
            logger.error(f"Escalation failed for intent {routed_intent.intent_id}: {e}")
            return {
                "intent_id": routed_intent.intent_id,
                "intent_type": classification.intent_type.value,
                "status": "error",
                "error": str(e),
                "message": "Failed to escalate to bead",
            }


# Global router instance
_router: Optional[IntentRouter] = None


def get_router(store=None) -> IntentRouter:
    """Get or create the global intent router instance."""
    global _router
    if _router is None:
        _router = IntentRouter(store=store)
    return _router


def clear_router_cache() -> None:
    """
    Clear the global router cache.

    This function resets the in-memory classification cache and statistics.
    Primarily used for testing to ensure test isolation.

    Example:
        >>> clear_router_cache()
        >>> router = get_router()
        >>> classifications, timing = await router.classify_utterance("test", "session-1")
        >>> assert timing["cached"] is False  # Fresh call after cache clear
    """
    global _router
    if _router is not None:
        _router._cache.clear()
