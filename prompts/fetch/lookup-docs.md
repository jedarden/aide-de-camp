# Fetch Strand: Lookup Intent - Docs Kind

This document defines the fetch strategy for `intent_type: lookup` with `lookup_kind: docs`.

## What We Fetch

For a docs lookup query, we need documentation and project overview information:

1. **README**: Project README file
2. **File structure**: Directory listing of the project
3. **Documentation files**: Any docs/*.md or similar documentation
4. **Package/service info**: Cargo.toml, package.json, or similar metadata files

## Command Matrix

```bash
# README file
cat ${REPO_PATH}/README.md

# Directory listing (file structure)
ls -la ${REPO_PATH}

# Documentation files (if docs/ directory exists)
find ${REPO_PATH}/docs -name "*.md" 2>/dev/null | head -20

# Package metadata (language-specific)
# For Rust projects:
cat ${REPO_PATH}/Cargo.toml 2>/dev/null
# For Python projects:
cat ${REPO_PATH}/pyproject.toml 2>/dev/null
# For Node projects:
cat ${REPO_PATH}/package.json 2>/dev/null

# Recent activity (for context)
git -C ${REPO_PATH} log -5 --oneline --pretty=format:'%h|%s|%an|%ar'
```

## Parallel Execution

All fetch sources run concurrently.

Timeout per source:
- README: 2 seconds
- Directory listing: 2 seconds
- Documentation files: 3 seconds
- Package metadata: 2 seconds
- Git log: 3 seconds

## Result Structure

```json
{
  "readme": {
    "status": "success|timeout|error",
    "data": {
      "content": "README file content",
      "exists": true
    }
  },
  "file_structure": {
    "status": "success|timeout|error",
    "data": {
      "files": [ /* file/directory listing */ ],
      "total_count": 42
    }
  },
  "documentation": {
    "status": "success|timeout|error",
    "data": [
      /* {
       *   "path": "docs/architecture.md",
       *   "content": "..."
       * }, ...
       */
    ]
  },
  "package_metadata": {
    "status": "success|timeout|error",
    "data": {
      "type": "Cargo.toml|pyproject.toml|package.json",
      "content": { /* parsed metadata */ }
    }
  },
  "git_log": {
    "status": "success|timeout|error",
    "data": [ /* recent commit entries */ ]
  },
  "coverage": {
    "readme": true,
    "file_structure": true,
    "documentation": true,
    "package_metadata": true,
    "git_log": true
  }
}
```

## Context Expansion

For docs lookup queries, include these context fields if available:

- **Project context**: Which project/repository
- **Doc type**: README, API docs, architecture docs
- **Specific file**: If user asks for a specific doc file
- **Scope**: Overview vs detailed documentation

The fetch layer is deterministic. No LLM calls here — just execute the command matrix and return structured data.
