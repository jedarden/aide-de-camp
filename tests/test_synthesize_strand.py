"""
Synthesize strand structured-result unit tests (bead adc-1mzt).

Hermetic, network-free tests for src/synthesize/strand.py — the SynthesizeStrand
that turns a fetched FetchResult into a structured SynthesizeResult
(data dict + audio-mode summary + Urgency classification).

The ZAI/LLM client is mocked, so no live model is called and synthesis is
deterministic. The fixture strand reads its prompt from a temp file and its
urgency rules from a stubbed reload manager, leaving the real hot-reload
system untouched.

What this suite locks down (the "synthesis produces structured results" contract):

1. **Structured output** — synthesize() returns a SynthesizeResult whose
   `data` is a dict, `summary` is a str, and `urgency` is a Urgency enum —
   the three fields the component library / audio mode consume.
2. **Markdown-fence stripping** — GLM wraps JSON in ```json fences; the strand
   must strip them before json.loads. Both fenced and bare JSON must parse.
3. **Urgency mapping** — every valid urgency string maps to its enum; an
   unrecognized value falls back to Urgency.NORMAL (never raises).
4. **Coverage + caveats passthrough** — the FetchResult's coverage/caveats are
   surfaced on SynthesizeResult; absent context leaves them None.
5. **Malformed-response resilience** — a non-JSON LLM reply yields a
   well-formed error SynthesizeResult (does NOT raise); a genuine transport
   error re-raises so the caller can decide.
6. **Message building** — _build_user_message embeds every fetched source's
   data (success) or its error (failure), so the model sees all context.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.fetch.commands import (
    FetchCoverage,
    FetchResult,
    FetchSource,
    IntentType,
    SourceResult,
)
from src.synthesize.strand import (
    SynthesizeRequest,
    SynthesizeResult,
    SynthesizeStrand,
    Urgency,
)

# --- fixtures --------------------------------------------------------------


@pytest.fixture
def prompt_file(tmp_path: Path) -> Path:
    """A temp synthesize prompt so the strand never reads the real artifact."""
    p = tmp_path / "synthesize.md"
    p.write_text("You are the synthesize strand. Return JSON.")
    return p


@pytest.fixture
def strand(prompt_file: Path) -> SynthesizeStrand:
    """
    A SynthesizeStrand that reads the temp prompt and a stubbed reload manager
    (urgency rules = ""), so the real hot-reload system is never touched.
    """
    s = SynthesizeStrand(prompt_path=prompt_file)
    # Stub the reload manager so _load_urgency_prompt() returns "" without
    # instantiating the real HotReloadManager (which watches the filesystem).
    s._reload_manager = MagicMock()
    s._reload_manager.get_prompt.return_value = ""
    return s


def _mock_client(raw_response: str) -> MagicMock:
    """A fake ZAI client whose call_simple returns `raw_response`."""
    client = MagicMock()
    client.call_simple = AsyncMock(return_value=raw_response)
    return client


def _fetched_context(
    sources: dict[FetchSource, SourceResult] | None = None,
    caveats: list[str] | None = None,
) -> FetchResult:
    """
    Build a FetchResult carrying the given per-source outcomes (defaults to a
    single successful pod-status source) plus optional caveats.
    """
    if sources is None:
        sources = {
            FetchSource.KUBECTL_PODS: SourceResult(
                source=FetchSource.KUBECTL_PODS,
                status="success",
                data={"pods": [{"name": "web-0", "phase": "Running"}]},
            )
        }
    succeeded = [s for s, r in sources.items() if r.status == "success"]
    failed = [s for s, r in sources.items() if r.status == "error"]
    timed_out = [s for s, r in sources.items() if r.status == "timeout"]
    coverage = FetchCoverage(
        total_sources=len(sources),
        succeeded=succeeded,
        timed_out=timed_out,
        failed=failed,
        skipped=[],
    )
    return FetchResult(
        intent_id="intent-synth-test",
        intent_type=IntentType.STATUS,
        sources=sources,
        coverage=coverage,
        total_duration_ms=42,
        caveats=caveats,
    )


def _request(fetched: FetchResult | None = None, urgency: str = "normal") -> SynthesizeRequest:
    return SynthesizeRequest(
        intent_id="intent-synth-test",
        intent_type=IntentType.STATUS,
        utterance="how are the pods doing?",
        project_slug="my-proj",
        fetched_context=fetched,
        urgency=urgency,
    )


def _fence(payload: dict | str) -> str:
    """Wrap a payload in the ```json fences GLM emits."""
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return f"```json\n{body}\n```"


# --- 1. structured output --------------------------------------------------


class TestStructuredOutput:
    """synthesize() must return a fully-formed SynthesizeResult."""

    @pytest.mark.asyncio
    async def test_returns_synthesize_result_with_three_fields(self, strand):
        payload = {
            "data": {"type": "pod-status", "items": [], "summary_fields": {"total": 0}},
            "summary": "All pods are running normally.",
            "urgency": "normal",
        }
        strand._zai_client = _mock_client(json.dumps(payload))
        fetched = _fetched_context()

        result = await strand.synthesize(_request(fetched))

        assert isinstance(result, SynthesizeResult)
        assert isinstance(result.data, dict)
        assert isinstance(result.summary, str)
        assert isinstance(result.urgency, Urgency)
        assert result.data == payload["data"]
        assert result.summary == payload["summary"]
        assert result.urgency is Urgency.NORMAL

    @pytest.mark.asyncio
    async def test_preserves_intent_id(self, strand):
        payload = {"data": {"type": "x"}, "summary": "s", "urgency": "low"}
        strand._zai_client = _mock_client(json.dumps(payload))
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.intent_id == "intent-synth-test"

    @pytest.mark.asyncio
    async def test_missing_data_key_defaults_to_empty_dict(self, strand):
        """A response with no `data` key must not crash — data defaults to {}."""
        strand._zai_client = _mock_client(json.dumps({"summary": "s", "urgency": "normal"}))
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.data == {}
        assert result.summary == "s"

    @pytest.mark.asyncio
    async def test_missing_summary_key_defaults_to_empty(self, strand):
        strand._zai_client = _mock_client(json.dumps({"data": {"type": "x"}, "urgency": "normal"}))
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.summary == ""


# --- 2. markdown-fence stripping ------------------------------------------


class TestFenceStripping:
    """GLM wraps JSON in ```json fences; the strand must strip them."""

    @pytest.mark.asyncio
    async def test_fenced_json_parses(self, strand):
        payload = {"data": {"type": "git-log"}, "summary": "behind by 3", "urgency": "high"}
        strand._zai_client = _mock_client(_fence(payload))
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.data == payload["data"]
        assert result.summary == "behind by 3"
        assert result.urgency is Urgency.HIGH

    @pytest.mark.asyncio
    async def test_bare_json_parses(self, strand):
        payload = {"data": {"type": "git-log"}, "summary": "s", "urgency": "normal"}
        strand._zai_client = _mock_client(json.dumps(payload))
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.data == payload["data"]

    @pytest.mark.asyncio
    async def test_plain_fence_without_language_tag(self, strand):
        """A bare ``` fence (no `json` label) must still be stripped."""
        body = json.dumps({"data": {"type": "x"}, "summary": "s", "urgency": "low"})
        strand._zai_client = _mock_client(f"```\n{body}\n```")
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.urgency is Urgency.LOW
        assert result.data == {"type": "x"}


# --- 3. urgency mapping ---------------------------------------------------


class TestUrgencyMapping:
    """Valid urgency strings map to enums; garbage falls back to NORMAL."""

    @pytest.mark.parametrize(
        ("urgency_str", "expected"),
        [
            ("critical", Urgency.CRITICAL),
            ("high", Urgency.HIGH),
            ("normal", Urgency.NORMAL),
            ("low", Urgency.LOW),
        ],
    )
    @pytest.mark.asyncio
    async def test_valid_urgency_maps_to_enum(self, strand, urgency_str, expected):
        strand._zai_client = _mock_client(
            json.dumps({"data": {}, "summary": "s", "urgency": urgency_str})
        )
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.urgency is expected

    @pytest.mark.asyncio
    async def test_unrecognized_urgency_falls_back_to_normal(self, strand):
        strand._zai_client = _mock_client(
            json.dumps({"data": {}, "summary": "s", "urgency": "on-fire"})
        )
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.urgency is Urgency.NORMAL

    @pytest.mark.asyncio
    async def test_missing_urgency_falls_back_to_request_urgency(self, strand):
        """No urgency in the response → the request's urgency string is used."""
        strand._zai_client = _mock_client(json.dumps({"data": {}, "summary": "s"}))
        # request urgency "high" is not a valid Urgency value, so it maps to NORMAL
        result = await strand.synthesize(_request(_fetched_context(), urgency="high"))
        assert result.urgency is Urgency.HIGH


# --- 4. coverage + caveats passthrough ------------------------------------


class TestCoveragePassthrough:
    """FetchResult coverage/caveats are surfaced on the synthesized result."""

    @pytest.mark.asyncio
    async def test_coverage_reflects_fetched_context(self, strand):
        strand._zai_client = _mock_client(
            json.dumps({"data": {}, "summary": "s", "urgency": "normal"})
        )
        sources = {
            FetchSource.KUBECTL_PODS: SourceResult(
                source=FetchSource.KUBECTL_PODS, status="success", data={}
            ),
            FetchSource.ARGOCD_APP: SourceResult(
                source=FetchSource.ARGOCD_APP, status="timeout", data={}, error="slow"
            ),
            FetchSource.GIT_LOG: SourceResult(
                source=FetchSource.GIT_LOG, status="error", data={}, error="boom"
            ),
        }
        fetched = _fetched_context(sources=sources, caveats=["argo timed out"])
        result = await strand.synthesize(_request(fetched))

        assert result.coverage == {
            "total_sources": 3,
            "succeeded": 1,
            "timed_out": 1,
            "failed": 1,
        }

    @pytest.mark.asyncio
    async def test_caveats_reflect_fetched_context(self, strand):
        strand._zai_client = _mock_client(
            json.dumps({"data": {}, "summary": "s", "urgency": "normal"})
        )
        caveats = ["Required source kubectl_deployments failed", "argo timed out"]
        fetched = _fetched_context(caveats=caveats)
        result = await strand.synthesize(_request(fetched))
        assert result.caveats == caveats

    @pytest.mark.asyncio
    async def test_no_fetched_context_leaves_coverage_and_caveats_none(self, strand):
        strand._zai_client = _mock_client(
            json.dumps({"data": {"type": "x"}, "summary": "s", "urgency": "normal"})
        )
        result = await strand.synthesize(_request(fetched=None))
        assert result.coverage is None
        assert result.caveats is None


# --- 5. malformed-response resilience -------------------------------------


class TestMalformedResponse:
    """Non-JSON replies yield an error result; transport errors re-raise."""

    @pytest.mark.asyncio
    async def test_unparseable_json_returns_error_result_without_raising(self, strand):
        strand._zai_client = _mock_client("this is not json at all")
        result = await strand.synthesize(_request(_fetched_context()))

        assert isinstance(result, SynthesizeResult)
        assert result.data["type"] == "error"
        assert "parse" in result.data["error"].lower()
        assert result.urgency is Urgency.NORMAL

    @pytest.mark.asyncio
    async def test_fenced_garbage_returns_error_result(self, strand):
        """Fence stripping must not mask a JSONDecodeError — it surfaces as an error result."""
        strand._zai_client = _mock_client("```json\n{not valid json\n```")
        result = await strand.synthesize(_request(_fetched_context()))
        assert result.data["type"] == "error"

    @pytest.mark.asyncio
    async def test_transport_error_reraises(self, strand):
        """A genuine client failure (not bad JSON) propagates to the caller."""
        client = MagicMock()
        client.call_simple = AsyncMock(side_effect=RuntimeError("proxy down"))
        strand._zai_client = client

        with pytest.raises(RuntimeError, match="proxy down"):
            await strand.synthesize(_request(_fetched_context()))


# --- 6. message building --------------------------------------------------


class TestBuildUserMessage:
    """_build_user_message embeds every source's data or error for the model."""

    def test_includes_intent_spec_and_utterance(self, strand):
        msg = strand._build_user_message(_request(_fetched_context()))
        assert "Intent Type: status" in msg
        assert "Project: my-proj" in msg
        assert "how are the pods doing?" in msg

    def test_includes_successful_source_data(self, strand):
        sources = {
            FetchSource.KUBECTL_PODS: SourceResult(
                source=FetchSource.KUBECTL_PODS,
                status="success",
                data={"pods": [{"name": "web-0"}], "pod_count": 1},
            ),
            FetchSource.GIT_LOG: SourceResult(
                source=FetchSource.GIT_LOG,
                status="success",
                data={"commits": [{"hash": "abc", "message": "fix"}]},
            ),
        }
        msg = strand._build_user_message(_request(_fetched_context(sources=sources)))
        # Both source headings present, with their pretty-printed JSON data.
        assert "kubectl_pods" in msg
        assert "git_log" in msg
        assert "web-0" in msg
        assert "abc" in msg

    def test_includes_failed_source_status_and_error(self, strand):
        sources = {
            FetchSource.ARGOCD_APP: SourceResult(
                source=FetchSource.ARGOCD_APP,
                status="error",
                data={},
                error="connection refused",
            ),
        }
        msg = strand._build_user_message(_request(_fetched_context(sources=sources)))
        assert "argo_cd_app" in msg or "argocd_app" in msg
        assert "Status: error" in msg
        assert "connection refused" in msg

    def test_includes_caveats_section_when_present(self, strand):
        caveats = ["Required source kubectl_deployments failed", "argo timed out"]
        msg = strand._build_user_message(_request(_fetched_context(caveats=caveats)))
        assert "## Caveats" in msg
        assert "Required source kubectl_deployments failed" in msg

    def test_no_caveats_section_when_absent(self, strand):
        msg = strand._build_user_message(_request(_fetched_context(caveats=None)))
        assert "## Caveats" not in msg

    def test_no_fetched_context_omits_sources_section(self, strand):
        msg = strand._build_user_message(_request(fetched=None))
        assert "## Fetched Context" not in msg
        assert "synthesize this into a structured result" in msg


# --- 7. prompt + urgency splicing, and convenience wiring -----------------


class TestPromptAndWiring:
    """System-prompt construction (urgency splicing) and call parameters."""

    @pytest.mark.asyncio
    async def test_urgency_rules_spliced_into_system_prompt_when_present(self, prompt_file):
        """When urgency rules load, they're appended to the system prompt."""
        s = SynthesizeStrand(prompt_path=prompt_file)
        s._reload_manager = MagicMock()
        s._reload_manager.get_prompt.return_value = "CRITICAL = pager fires"
        captured = {}

        async def fake_call(system_prompt, user_message, model, max_tokens, temperature):
            captured["system"] = system_prompt
            captured["model"] = model
            captured["temperature"] = temperature
            return json.dumps({"data": {}, "summary": "s", "urgency": "normal"})

        client = MagicMock()
        client.call_simple = fake_call
        s._zai_client = client

        await s.synthesize(_request(_fetched_context()))
        assert "Urgency Classification Rules" in captured["system"]
        assert "CRITICAL = pager fires" in captured["system"]

    @pytest.mark.asyncio
    async def test_no_urgency_rules_leaves_plain_prompt(self, strand, prompt_file):
        """Empty urgency prompt → no splicing; system prompt is just the file."""
        captured = {}

        async def fake_call(system_prompt, user_message, model, max_tokens, temperature):
            captured["system"] = system_prompt
            return json.dumps({"data": {}, "summary": "s", "urgency": "normal"})

        strand._zai_client = MagicMock()
        strand._zai_client.call_simple = fake_call
        await strand.synthesize(_request(_fetched_context()))
        assert captured["system"] == "You are the synthesize strand. Return JSON."

    @pytest.mark.asyncio
    async def test_model_and_temperature_are_pinned(self, strand):
        """Synthesis uses SONNET at temperature 0.5 for consistent output."""
        captured = {}

        async def fake_call(system_prompt, user_message, model, max_tokens, temperature):
            captured.update(model=model, temperature=temperature, max_tokens=max_tokens)
            return json.dumps({"data": {}, "summary": "s", "urgency": "normal"})

        strand._zai_client = MagicMock()
        strand._zai_client.call_simple = fake_call
        await strand.synthesize(_request(_fetched_context()))
        assert captured["model"] == "claude-sonnet-4-20250514"
        assert captured["temperature"] == 0.5
        assert captured["max_tokens"] == 4096
