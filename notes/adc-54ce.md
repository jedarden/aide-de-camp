# adc-54ce — Fix deployment section and README LLM config claims

**Status:** Verified already satisfied in committed code. No file changes
required beyond this note.

## Outcome

All four acceptance criteria for `adc-54ce` are **already present** in the
committed, pushed codebase. The work landed in commit `0e66cc5`
("feat: add telegram bridge reachability warning and status indicator",
2026-07-02) — the same day this bead was split off from the umbrella
reconciliation bead `adc-388`. The bead was never closed afterward.

Confirmed `0e66cc5` is on `origin/main`, and `README.md` / `docs/plan/plan.md`
are clean (no uncommitted changes).

## Acceptance-criteria verification

### PART 1 — plan.md Deployment section (`docs/plan/plan.md`, lines 497–619)

| Criterion | Where it is satisfied |
|-----------|----------------------|
| Reflect Phase 0 reality: local process on port 8000, no CI build | §"Current Deployment: Phase 0" — L512 "runs as a process on the Hetzner server", L518 `uvicorn src.main:app --host 0.0.0.0 --port 8000`, L520 "No container, no CI, no ArgoCD" |
| Document version-bump + git tag release flow | §"Release flow (Phase 0)" — L522–526: "version in `pyproject.toml` only … bump → commit → `git tag vX.Y.Z` → push" (mirrors README "Versioning") |
| Phase 1+ items marked as future, not built | "Status: NOT BUILT ❌" on all three: containerization (L528–542), Traefik SSE/WebSocket (L546–582), CI/CD Argo template (L610–619) |

### PART 2 — README.md Configuration section (`README.md`, lines 135–167)

| Criterion | Where it is satisfied |
|-----------|----------------------|
| Remove claim that LLM backend is configurable via `config/registry.yaml` | No such claim exists. `registry.yaml` is referenced only for project/alias definitions (L69, L76, L162, L187) — verified `config/registry.yaml` has no LLM section |
| Add `ZAI_PROXY_URL` to env var table | L142: row with purpose "ZAI proxy endpoint for LLM calls (routing and synthesis)" and the default URL |
| Document backend is set via `ZAI_PROXY_URL` env var | L147: "The LLM backend for intent routing and synthesis is configured via the `ZAI_PROXY_URL` environment variable. All LLM calls route through the ZAI proxy." |

### Cross-check: documented default matches the code

`README.md:142` documents the `ZAI_PROXY_URL` default as
`https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages`.
`src/escalate/llm.py:24` uses the identical default — docs and code agree.

## Out-of-scope finding (flagged for umbrella `adc-388`)

While verifying, I found two stale ZAI-proxy hostnames in plan.md that are
**outside this bead's scope** (they are in the Technology Stack table and the
Relationship-to-Infrastructure section, not the Deployment section, and not in
README.md). They do not match the code default above:

- `docs/plan/plan.md:630` — Technology Stack: `ZAI proxy (`llm-proxy.ardenone.com`)`
- `docs/plan/plan.md:778` — Relationship to Existing Infrastructure: "route through `llm-proxy.ardenone.com`"

The historical research corpus (`docs/research/resource-reuse.md` etc.) repeats
the same `llm-proxy.ardenone.com` hostname. Left untouched here to keep
`adc-54ce` tightly scoped to its two named sections; `adc-388`'s broader
docs-reconciliation pass should correct these.
