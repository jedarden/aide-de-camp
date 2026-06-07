# Task adc-1i71: Identify Project Root

## Goal
Locate the working directory where the `src/` folder lives.

## Findings

**Project Root:** `/home/coding/aide-de-camp`

**Verification:**
- Confirmed via `pwd` and `ls -la`
- `src/` exists as a child directory with 23 module subdirectories
- Project is a Python application (contains `pyproject.toml`, `requirements.txt`)

**src/ contents:**
- agents, canvas, cli, components, context, conversation
- diff, escalate, feedback, fetch, intent
- main.py (42,695 bytes - main application entry point)
- monitoring, realtime, registry.py, session, sse
- surface, synthesize, telegram, topic, watcher
