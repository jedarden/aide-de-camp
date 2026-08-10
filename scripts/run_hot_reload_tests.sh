#!/usr/bin/env bash
set -euo pipefail

# Stable CI entry point for hot-reload coverage. The tests are run in one
# process and one pytest invocation so repository-file backup/restore fixtures
# cannot race one another. The external dispatch smoke test is opt-in because
# it requires a running aide-de-camp server.

python_command="${PYTHON:-python3}"
suite_timeout="${HOT_RELOAD_SUITE_TIMEOUT:-120}"

test_files=(
    tests/test_config_hot_reload.py
    tests/test_hot_reload.py
    tests/test_hot_reload_edge_cases.py
    tests/test_hot_reload_fail_fast.py
    tests/test_hot_reload_fast.py
    tests/test_hot_reload_idempotency.py
    tests/test_registry_hot_reload.py
    tests/test_registry_hot_reload_new_infrastructure.py
    tests/test_registry_hot_reload_routing.py
    tests/test_router_prompt_hotreload.py
    tests/test_urgency_hotreload.py
    tests/test_monitoring_config_hotreload.py
    tests/intent/test_hot_reload.py
)

if [[ "${RUN_DISPATCH_E2E:-0}" == "1" ]]; then
    test_files+=(tests/test_hot_reload_dispatch.py)
fi

exec timeout --signal=TERM "${suite_timeout}s" \
    "${python_command}" -m pytest -q "${test_files[@]}"
