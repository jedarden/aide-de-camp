# Task: Fix incorrect router path in plan.md

## Task ID
adc-erbxl

## Finding
No `src/router/` reference exists in plan.md. The file already correctly documents the filesystem structure.

## Actual State

### Filesystem
The actual `src/` directory contains:
```
src/intent/
├── __init__.py
├── router.py
└── deterministic_router.py
```

### plan.md Documentation
The File System Layout section (lines 703-704) correctly shows:
```
├── intent/              ← intent router (LLM classification)
│   ├── router.py            ← intent segmentation and routing
│   ├── deterministic_router.py ← fast-path deterministic routing (70-80% of requests)
```

## Acceptance Criteria Status
- ✓ No references to `src/router/` remain in plan.md (none existed)
- ✓ `src/intent/` appears in the File System Layout (correctly documented)
- N/A Change is committed (no change needed)

## Conclusion
The task was based on an outdated assumption. The plan.md file already correctly reflects the actual filesystem structure with `src/intent/` as the intent router directory.
