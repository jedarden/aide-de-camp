"""Unit tests for scripts/diagnose_pluck_starvation.py (bead aidedeca-2a3e09ac).

Covers the `bead list --json` payload parser: the CLI emits compact JSONL,
prints a bare "[]" for an empty result, and has been seen emitting nested
arrays. The starvation scenario this suite exists for is precisely the empty
frontier, so an empty payload must count zero beads — never one — and must
never hand a non-dict to the dict-only consumers downstream.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_pluck_starvation.py"
_spec = importlib.util.spec_from_file_location("diagnose_pluck_starvation", _SCRIPT)
dps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dps)


def test_empty_output_counts_zero():
    assert dps.parse_bead_payload("") == []
    assert dps.parse_bead_payload("\n") == []


def test_bare_empty_array_counts_zero_not_one():
    # A bare "[]" parsed as a single entry would report a starving frontier as
    # size 1 and crash ready_bead_sample's dict access.
    assert dps.parse_bead_payload("[]\n") == []


def test_jsonl_lines_flatten_to_dicts():
    out = '{"id": "a"}\n{"id": "b"}\n'
    assert [b["id"] for b in dps.parse_bead_payload(out)] == ["a", "b"]


def test_nested_arrays_flatten():
    out = '[{"id": "a"}, {"id": "b"}]\n[{"id": "c"}]\n'
    assert [b["id"] for b in dps.parse_bead_payload(out)] == ["a", "b", "c"]


def test_progress_lines_are_skipped_not_fatal():
    out = 'Fetching beads...\n{"id": "a"}\n'
    assert [b["id"] for b in dps.parse_bead_payload(out)] == ["a"]


def test_result_entries_are_always_dicts():
    # check_pluck_query_logic calls .get() on each entry; the crash this
    # guards against was a bare "[]" or nested array surviving as a list.
    for out in ("", "[]\n", '[{"id": "a"}]\n', 'progress\n{"id": "b"}\n'):
        for bead in dps.parse_bead_payload(out):
            assert isinstance(bead, dict)
