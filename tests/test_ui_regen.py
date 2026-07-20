"""
Unit tests for the LLM-driven UIRegenAgent.

These verify that component *generation* (``_generate_template`` /
``_generate_component``) and *iteration* (``_improve_template`` /
``iterate_component``) make real ZAI proxy calls (via the injected client)
instead of returning the old fixed list/summary/generic string templates, and
that an unusual (tabular) result shape yields a purpose-built template
distinguishable from those three fixed strings.

The ZAI client is mocked so the tests are deterministic and network-free; the
component library is pointed at a throwaway SQLite DB so the real
``data/components.db`` singleton is never touched.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.agents.ui_regen import ComponentRequest, UIRegenAgent
from src.components.library import ComponentLibrary
from src.escalate.llm import ModelClass

# A result shape that none of the three fixed templates fit well: a flat header
# plus a homogeneous list of records under ``pods`` (not ``items``), with no
# ``summary_fields``. The old heuristic generator would force this into the
# generic key/value template; a real generator should produce a <table>.
POD_TABLE_DATA = {
    "cluster": "apexalgo-iad",
    "captured_at": "2026-07-19T12:00:00Z",
    "pods": [
        {"name": "api-7c2", "ready": "1/1", "status": "Running", "restarts": 0},
        {"name": "worker-1", "ready": "0/1", "status": "CrashLoopBackOff", "restarts": 12},
        {"name": "cache-aa", "ready": "1/1", "status": "Running", "restarts": 2},
    ],
}

# What a purpose-built generator returns for POD_TABLE_DATA: a <table>, which
# none of the three fixed list/summary/generic templates ever emit, speaking the
# flat {{field.path}} substitution contract.
LLM_TABLE_TEMPLATE = """<div class="pod-status-card">
  <div class="ps-head">{{cluster}} <span class="ps-ts">{{captured_at}}</span></div>
  <table class="pod-table">
    <thead><tr><th>Pod</th><th>Ready</th><th>Status</th><th>Restarts</th></tr></thead>
    <tbody>
      <tr><td>{{pods.0.name}}</td><td>{{pods.0.ready}}</td><td>{{pods.0.status}}</td><td class="restarts">{{pods.0.restarts}}</td></tr>
      <tr><td>{{pods.1.name}}</td><td>{{pods.1.ready}}</td><td>{{pods.1.status}}</td><td class="restarts">{{pods.1.restarts}}</td></tr>
      <tr><td>{{pods.2.name}}</td><td>{{pods.2.ready}}</td><td>{{pods.2.status}}</td><td class="restarts">{{pods.2.restarts}}</td></tr>
    </tbody>
  </table>
</div>"""

# A simple seed template for the iteration tests.
BASE_TEMPLATE = """<div class='card card-pod-status'>
  <div class='card-header'><h3>Pod Status</h3></div>
  <div class='card-body'>
    <div class='card-row'><span>Name:</span><span>{{pods.0.name}}</span></div>
    <div class='card-row'><span>Status:</span><span>{{pods.0.status}}</span></div>
  </div>
</div>"""


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """A UIRegenAgent wired to an isolated component library.

    ``get_library`` is patched so construction never touches the real
    ``data/components.db`` singleton. ``_zai_client`` is left None so each test
    injects its own mock; ``_get_zai_client`` returns ``self._zai_client``
    directly when it is set.
    """
    lib = ComponentLibrary(str(tmp_path / "components.db"))
    monkeypatch.setattr("src.agents.ui_regen.get_library", lambda *a, **k: lib)
    a = UIRegenAgent()
    a._zai_client = None
    return a


def _fenced_json(obj) -> str:
    """Wrap a JSON object in ```json fences, the way GLM-4.7 does."""
    return "```json\n" + json.dumps(obj) + "\n```"


class TestGenerateComponent:
    """``_generate_component`` / ``_generate_template`` must call the LLM."""

    @pytest.mark.asyncio
    async def test_tabular_shape_yields_table_not_fixed_template(self, agent):
        captured = {}

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            captured["model"] = kwargs.get("model")
            captured["user_message"] = user_message
            captured["system_prompt"] = system_prompt
            # Return fenced JSON to exercise the GLM fence-stripping path.
            return _fenced_json({
                "html_template": LLM_TABLE_TEMPLATE,
                "rationale": "Tabular pod list renders best as a table",
            })

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        request = ComponentRequest(
            result_id="res-1",
            result_type="pod-status",
            result_data=POD_TABLE_DATA,
            layout_bucket="normal",
        )
        component = await agent._generate_component(request)

        # A real LLM call was made, on SONNET, carrying the data shape.
        assert captured["model"] == ModelClass.SONNET.value
        assert "pod-status" in captured["user_message"]
        assert "pods" in captured["user_message"]
        assert "restarts" in captured["user_message"]
        assert captured["system_prompt"]  # generate prompt was loaded

        tpl = component.html_template

        # Defining regression check: distinguishable from ALL three fixed
        # templates (list/summary/generic) for this same data shape.
        assert tpl != agent._degradation_list_template(POD_TABLE_DATA, "pod-status")
        assert tpl != agent._degradation_summary_template(POD_TABLE_DATA, "pod-status")
        assert tpl != agent._degradation_generic_template(POD_TABLE_DATA, "pod-status")

        # Structurally novel: a <table>, which none of the fixed templates emit,
        # and no fixed-template `card card-<type>` signature.
        assert "<table" in tpl
        assert "card card-pod-status'" not in tpl

        # Round-trips through _apply_template: placeholders resolve to real values.
        rendered = agent._apply_template(component, POD_TABLE_DATA)
        assert "{{" not in rendered  # every placeholder substituted
        assert "api-7c2" in rendered
        assert "CrashLoopBackOff" in rendered
        assert "12" in rendered  # worker-1 restarts

    @pytest.mark.asyncio
    async def test_render_result_end_to_end_uses_generated_template(self, agent):
        """The public render_result path must generate (empty library), cache,
        and return substituted HTML — exercising the async refactor."""
        async def fake_call_simple(system_prompt, user_message, **kwargs):
            return _fenced_json({"html_template": LLM_TABLE_TEMPLATE, "rationale": "table"})

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        request = ComponentRequest(
            result_id="res-2",
            result_type="pod-status",
            result_data=POD_TABLE_DATA,
            layout_bucket="normal",
        )
        rendered = await agent.render_result(request)

        assert "<table" in rendered
        assert "{{" not in rendered
        assert "apexalgo-iad" in rendered

    @pytest.mark.asyncio
    async def test_empty_llm_template_degrades_to_heuristic(self, agent):
        async def fake_call_simple(system_prompt, user_message, **kwargs):
            return json.dumps({"html_template": "", "rationale": "n/a"})

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        tpl = await agent._generate_template(POD_TABLE_DATA, "pod-status")
        # Falls back to the heuristic generic template for this shape.
        assert tpl == agent._degradation_generic_template(POD_TABLE_DATA, "pod-status")
        assert "card card-pod-status'" in tpl  # fixed-template signature

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_to_heuristic(self, agent):
        async def fake_call_simple(system_prompt, user_message, **kwargs):
            raise RuntimeError("proxy unreachable")

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        tpl = await agent._generate_template(POD_TABLE_DATA, "pod-status")
        # Safety net: card still renders via the heuristic template, no raise.
        assert tpl == agent._degradation_generic_template(POD_TABLE_DATA, "pod-status")


class TestIterateComponent:
    """``iterate_component`` / ``_improve_template`` must call the LLM."""

    @pytest.mark.asyncio
    async def test_iterate_uses_llm_and_bumps_version(self, agent):
        seed = agent.library.create_component(
            name="pod-status",
            description="Renders pod-status results",
            html_template=BASE_TEMPLATE,
            change_note="seed",
        )

        improved = BASE_TEMPLATE.replace(
            "{{pods.0.status}}</span></div>",
            "{{pods.0.status}}</span></div>\n    "
            "<div class='card-row restarts-row'><span>Restarts:</span>"
            "<span class='restart-count'>{{pods.0.restarts}}</span></div>",
        )
        captured = {}

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            captured["model"] = kwargs.get("model")
            captured["user_message"] = user_message
            return _fenced_json({
                "html_template": improved,
                "change_summary": "Elevated restart count",
            })

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        updated = await agent.iterate_component(
            seed.id, "show restart count more prominently", POD_TABLE_DATA
        )

        # Real LLM call carrying feedback + current template + data shape.
        assert captured["model"] == ModelClass.SONNET.value
        assert "show restart count more prominently" in captured["user_message"]
        assert BASE_TEMPLATE in captured["user_message"]
        assert "restarts" in captured["user_message"]

        # Applied: version bumped, template changed, restarts now prominent.
        assert updated.version == 2
        assert updated.html_template == improved
        assert "restart-count" in updated.html_template

    @pytest.mark.asyncio
    async def test_iterate_no_change_keeps_version(self, agent):
        seed = agent.library.create_component(
            name="pod-status", description="x", html_template=BASE_TEMPLATE, change_note="seed"
        )

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            # LLM returns the template unchanged.
            return json.dumps({"html_template": BASE_TEMPLATE, "change_summary": "no-op"})

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        updated = await agent.iterate_component(seed.id, "do nothing", None)

        assert updated.version == 1  # no version bump for a no-op
        assert updated.html_template == BASE_TEMPLATE

    @pytest.mark.asyncio
    async def test_iterate_llm_failure_leaves_component_unchanged(self, agent):
        seed = agent.library.create_component(
            name="pod-status", description="x", html_template=BASE_TEMPLATE, change_note="seed"
        )

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            raise RuntimeError("proxy unreachable")

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        updated = await agent.iterate_component(seed.id, "make it better", None)

        assert updated.version == 1  # untouched
        assert updated.html_template == BASE_TEMPLATE

    @pytest.mark.asyncio
    async def test_iterate_unknown_component_returns_none(self, agent):
        updated = await agent.iterate_component("comp-doesnotexist", "feedback", None)
        assert updated is None
