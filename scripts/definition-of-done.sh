#!/usr/bin/env bash
# Repository definition of done for aide-de-camp.
#
# Validation gates and close-evidence re-runs for this workspace execute in a
# clean `git archive` extraction of committed main, which carries no `.venv`
# and no installed dependencies (see .needle.yaml). The only interpreter on
# PATH there is the NixOS system python, whose user-site packages are an
# unrelated partial install — currently an incompatible fastapi 0.115 +
# starlette 1.6 pairing on which `APIRouter()` itself raises
# `TypeError: Router.__init__() got an unexpected keyword argument
# 'on_startup'`, so no FastAPI suite can even collect — and `hvac` is absent
# entirely. The definition of done therefore bootstraps its own venv from
# pyproject.toml before running pytest, mirroring the documented manual setup
# in CLAUDE.md, so the gate is reproducible from committed state alone.
#
# Usage:
#   scripts/definition-of-done.sh           # full suite: pytest -q
#   scripts/definition-of-done.sh --fast    # validation/utility contract suites
#
# Extra arguments are passed through to pytest. `uv` is used for the install
# when available (warm-cache installs take seconds instead of minutes) and
# pip is the fallback.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAST=0
if [ "${1:-}" = "--fast" ]; then
  FAST=1
  shift
fi

VENV="$ROOT/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$VENV/bin/python" -e ".[dev]"
  else
    "$VENV/bin/python" -m pip install --quiet -e ".[dev]"
  fi
fi

if [ "$FAST" -eq 1 ]; then
  # The fast gate covers the pure validation and utility contract suites
  # (bead aidedeca-dadfd697): JSON fence stripping, completeness validation,
  # the validation runner, dispatch request validation, demo seeding, and the
  # bead ready-query regression. The full suite remains the no-argument mode.
  exec "$VENV/bin/python" -m pytest -q \
    tests/unit/test_json_parsing.py \
    tests/unit/test_validate_completeness.py \
    tests/unit/test_validation_runner.py \
    tests/validation/test_dispatch_request_validation.py \
    tests/test_demo_seed.py \
    tests/verification/test_bead_ready_query_regression.py "$@"
fi

exec "$VENV/bin/python" -m pytest -q "$@"
