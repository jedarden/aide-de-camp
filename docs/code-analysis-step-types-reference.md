# Code Analysis Step Types - Complete Reference

## Overview

This document provides comprehensive documentation for all 9 code analysis and file manipulation step types implemented in aide-de-camp. Each step type includes field definitions, execution behavior, error handling, and concrete examples for self-modification and code analysis workflows.

## Step Type Classification

### Read-Only Step Types (6)
These steps query code and file systems without mutating any state:

1. **BashRead** - Execute shell commands and capture output (read-only)
2. **Glob** - Find files matching patterns in the codebase
3. **LSPFind** - Find all references to a symbol in code
4. **LSPGoToDef** - Navigate to where a symbol is defined
5. **LSPHover** - Get hover information (docs, type info) for a symbol
6. **LSPDocumentSymbol** - Get all symbols (functions, classes) in a document

### Mutating Step Types (3)
These steps perform state changes on files and systems:

1. **BashMutate** - Execute shell commands that modify state
2. **Edit** - Perform exact string replacements in files
3. **Write** - Create or overwrite files with new content

---

## Read-Only Step Types

### 1. BashRead

Execute shell commands and capture stdout/stderr for analysis and information gathering. Does not modify system state.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | string | Yes | Shell command to execute |
| `timeout` | int | No | Command timeout in seconds (default: 30) |
| `working_dir` | string | No | Directory to execute from (default: current) |
| `capture_output` | bool | No | Whether to capture stdout/stderr (default: true) |

#### Execution Behavior

1. Validates that command is provided and safe (no destructive patterns)
2. Executes command in subprocess with capture
3. Waits for completion or timeout
4. Returns structured output with exit code, stdout, stderr

#### Error Handling

- **Missing command**: Returns failed StepResult with validation error
- **Timeout**: Returns failed StepResult after timeout expires
- **Non-zero exit**: Returns success=False with exit code and stderr
- **Permission denied**: Returns failed StepResult with permission error

#### Example

```python
from src.action.steps import execute_bash_read_step

# Execute read-only command
result = await execute_bash_read_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    command="git log --oneline -5",
    timeout=15
)

# Success result
# {
#     "success": true,
#     "data": {
#         "exit_code": 0,
#         "stdout": "abc1234 feat: add new feature\\ndef5678 fix: correct bug\\n",
#         "stderr": "",
#         "command": "git log --oneline -5",
#         "working_dir": "/home/coding/mta-my-way",
#         "duration_seconds": 0.45
#     }
# }

# Result with error output
# {
#     "success": false,
#     "data": {
#         "exit_code": 1,
#         "stdout": "",
#         "stderr": "fatal: not a git repository",
#         "command": "git log --oneline -5",
#         "working_dir": "/tmp"
#     }
# }
```

#### Use Cases

- Query git history (`git log`, `git diff`)
- List files and directories (`ls`, `find`)
- Check file contents (`cat`, `head`, `tail`)
- Query system information (`ps`, `df`, `uptime`)
- Read configuration files
- Test command availability (`which`, `type`)

---

### 2. Glob

Find files matching glob patterns in the codebase for targeted analysis and modification.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pattern` | string | Yes | Glob pattern (supports *, **) |
| `root_path` | string | No | Root directory to search (default: repo_path) |
| `exclude_patterns` | list[str] | No | Patterns to exclude (default: []) |
| `max_results` | int | No | Maximum files to return (default: 1000) |

#### Execution Behavior

1. Resolves root_path from project config or current directory
2. Scans directory tree for files matching pattern
3. Applies exclusion patterns (node_modules, .git, etc.)
4. Returns sorted list of matching file paths

#### Error Handling

- **Invalid pattern**: Returns failed StepResult with glob error
- **Directory not found**: Returns failed StepResult with path error
- **Too many results**: Returns failed StepResult with truncation warning

#### Example

```python
from src.action.steps import execute_glob_step

# Find all Python files
result = await execute_glob_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    pattern="**/*.py",
    exclude_patterns=["__pycache__", "*.pyc", "venv/"]
)

# Success result
# {
#     "success": true,
#     "data": {
#         "matches": [
#             "src/main.py",
#             "src/config.py",
#             "tests/test_main.py",
#             "deploy/deploy.py"
#         ],
#         "count": 4,
#         "pattern": "**/*.py",
#         "root_path": "/home/coding/mta-my-way"
#     }
# }

# Find test files specifically
result = await execute_glob_step(
    # ... same context ...
    pattern="tests/**/*.py"
)

# {
#     "success": true,
#     "data": {
#         "matches": [
#             "tests/test_main.py",
#             "tests/integration/test_api.py"
#         ],
#         "count": 2,
#         "pattern": "tests/**/*.py"
#     }
# }
```

#### Use Cases

- Find all test files before running test suite
- Locate configuration files for audit
- Find all markdown files for documentation check
- Identify source files matching language patterns
- Filter out dependencies/cache directories

---

### 3. LSPFind

Find all references to a symbol (function, class, variable) across the codebase using Language Server Protocol.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | Yes | Path to file containing symbol |
| `line` | int | Yes | Line number (1-based) |
| `character` | int | Yes | Character offset (1-based) |
| `project_path` | string | No | Project root (default: from config) |

#### Execution Behavior

1. Starts or connects to LSP server for the file type
2. Requests findReferences for symbol at position
3. Collects all reference locations
4. Returns structured reference list with file paths and positions

#### Error Handling

- **No LSP server**: Returns failed StepResult with LSP not configured error
- **Invalid position**: Returns failed StepResult with position error
- **Symbol not found**: Returns success=True with empty references list
- **Timeout**: Returns failed StepResult after LSP timeout

#### Example

```python
from src.action.steps import execute_lsp_find_step

# Find all references to a function
result = await execute_lsp_find_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    file_path="src/trading.py",
    line=42,
    character=10  # Position of function name
)

# Success result
# {
#     "success": true,
#     "data": {
#         "symbol_name": "calculate_position_size",
#         "references": [
#             {
#                 "file_path": "src/trading.py",
#                 "line": 42,
#                 "character": 10,
#                 "context": "def calculate_position_size(risk, capital):"
#             },
#             {
#                 "file_path": "src/trading.py",
#                 "line": 85,
#                 "character": 20,
#                 "context": "size = calculate_position_size(risk_params, account_capital)"
#             },
#             {
#                 "file_path": "tests/test_trading.py",
#                 "line": 23,
#                 "character": 15,
#                 "context": "size = calculate_position_size(test_risk, 10000)"
#             }
#         ],
#         "total_references": 3,
#         "files_affected": 2
#     }
# }

# No references found
# {
#     "success": true,
#     "data": {
#         "symbol_name": "unused_function",
#         "references": [],
#         "total_references": 0,
#         "files_affected": 0
#     }
# }
```

#### Use Cases

- Find all usages before renaming a function
- Detect dead code (no references)
- Understand impact of changing a symbol
- Audit test coverage for specific functions
- Trace variable usage across files

---

### 4. LSPGoToDef

Navigate to the definition location of a symbol using Language Server Protocol.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | Yes | Path to file containing symbol reference |
| `line` | int | Yes | Line number (1-based) |
| `character` | int | Yes | Character offset (1-based) |
| `project_path` | string | No | Project root (default: from config) |

#### Execution Behavior

1. Connects to LSP server for the file type
2. Requests goToDefinition for symbol at position
3. Retrieves definition location and context
4. Returns definition file path, line, and surrounding code

#### Error Handling

- **No LSP server**: Returns failed StepResult with LSP error
- **Symbol not defined**: Returns success=True with definition=None
- **Multiple definitions**: Returns all definitions (e.g., function overloads)
- **Timeout**: Returns failed StepResult after timeout

#### Example

```python
from src.action.steps import execute_lsp_goto_def_step

# Find where function is defined
result = await execute_lsp_goto_def_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    file_path="src/main.py",
    line=15,
    character=8  # Position of function call
)

# Success result
# {
#     "success": true,
#     "data": {
#         "symbol_name": "calculate_risk",
#         "definition": {
#             "file_path": "src/risk.py",
#             "line": 10,
#             "character": 0,
#             "context": "def calculate_risk(position_size, volatility):",
#             "snippet": "def calculate_risk(position_size, volatility):\n    \"\"\"Calculate risk metrics.\"\"\"\n    ..."
#         },
#         "reference_location": {
#             "file_path": "src/main.py",
#             "line": 15,
#             "character": 8
#         }
#     }
# }

# Symbol not defined (built-in or external)
# {
#     "success": true,
#     "data": {
#         "symbol_name": "print",
#         "definition": None,
#         "reason": "Built-in or external symbol"
#     }
# }
```

#### Use Cases

- Jump to implementation from usage
- Find where constants/variables are defined
- Navigate inheritance hierarchies
- Understand import chains
- Debug undefined symbol errors

---

### 5. LSPHover

Get hover information (documentation, type signature, hover text) for a symbol at cursor position.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | Yes | Path to file |
| `line` | int | Yes | Line number (1-based) |
| `character` | int | Yes | Character offset (1-based) |
| `project_path` | string | No | Project root (default: from config) |

#### Execution Behavior

1. Connects to LSP server for the file type
2. Requests hover information for symbol at position
3. Retrieves documentation, type info, and signature
4. Returns structured hover content with markdown docs

#### Error Handling

- **No LSP server**: Returns failed StepResult with LSP error
- **No hover available**: Returns success=True with hover=None
- **Timeout**: Returns failed StepResult after timeout

#### Example

```python
from src.action.steps import execute_lsp_hover_step

# Get hover info for function
result = await execute_lsp_hover_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    file_path="src/trading.py",
    line=42,
    character=15
)

# Success result with full docs
# {
#     "success": true,
#     "data": {
#         "symbol_name": "calculate_position_size",
#         "hover": {
#             "kind": "Function",
#             "documentation": {
#                 "raw": "Calculate position size based on risk parameters\\n\\nArgs:\\n    risk: Risk percentage (0-1)\\n    capital: Available capital\\n\\nReturns:\\n    Position size in units",
#                 "markdown": "Calculate position size based on risk parameters\n\n**Args:**\n- `risk`: Risk percentage (0-1)\n- `capital`: Available capital\n\n**Returns:**\n- Position size in units"
#             },
#             "signature": "def calculate_position_size(risk: float, capital: float) -> int",
#             "range": {
#                 "start_line": 42,
#                 "start_char": 15,
#                 "end_line": 42,
#                 "end_char": 38
#             }
#         },
#         "location": {
#             "file_path": "src/trading.py",
#             "line": 42,
#             "character": 15
#         }
#     }
# }

# Variable hover
# {
#     "success": true,
#     "data": {
#         "symbol_name": "position_size",
#         "hover": {
#             "kind": "Variable",
#             "type": "int",
#             "documentation": {
#                 "raw": "Position size in trading units"
#             }
#         }
#     }
# }
```

#### Use Cases

- Show function signatures and documentation
- Understand variable types
- Get quick documentation without navigating
- Assist with autocomplete suggestions
- Extract docstrings for analysis

---

### 6. LSPDocumentSymbol

Get all symbols (functions, classes, variables) in a document for structure analysis.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | Yes | Path to file to analyze |
| `project_path` | string | No | Project root (default: from config) |
| `include_nested` | bool | No | Include nested symbols (default: true) |

#### Execution Behavior

1. Connects to LSP server for the file type
2. Requests document symbol hierarchy
3. Extracts all symbols with kinds, ranges, and parent relationships
4. Returns structured symbol tree with metadata

#### Error Handling

- **No LSP server**: Returns failed StepResult with LSP error
- **File not found**: Returns failed StepResult with file error
- **Empty file**: Returns success=True with empty symbols list
- **Timeout**: Returns failed StepResult after timeout

#### Example

```python
from src.action.steps import execute_lsp_document_symbol_step

# Get all symbols in a file
result = await execute_lsp_document_symbol_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    file_path="src/trading.py"
)

# Success result
# {
#     "success": true,
#     "data": {
#         "file_path": "src/trading.py",
#         "symbols": [
#             {
#                 "name": "RiskParameters",
#                 "kind": "Class",
#                 "range": {
#                     "start_line": 5,
#                     "start_char": 0,
#                     "end_line": 15,
#                     "end_char": 0
#                 },
#                 "children": [
#                     {
#                         "name": "__init__",
#                         "kind": "Method",
#                         "range": {"start_line": 6, "end_line": 8}
#                     },
#                     {
#                         "name": "validate",
#                         "kind": "Method",
#                         "range": {"start_line": 10, "end_line": 15}
#                     }
#                 ]
#             },
#             {
#                 "name": "calculate_position_size",
#                 "kind": "Function",
#                 "range": {
#                     "start_line": 18,
#                     "start_char": 0,
#                     "end_line": 35,
#                     "end_char": 0
#                 },
#                 "children": []
#             },
#             {
#                 "name": "MAX_POSITION",
#                 "kind": "Constant",
#                 "range": {"start_line": 3, "end_line": 3}
#             }
#         ],
#         "total_symbols": 5,
#         "kinds": {
#             "Class": 1,
#             "Function": 1,
#             "Method": 2,
#             "Constant": 1
#         }
#     }
# }
```

#### Use Cases

- Analyze file structure and complexity
- Find all functions/classes for refactoring
- Generate documentation from code structure
- Detect orphaned or unused symbols
- Create symbol index for navigation
- Measure code metrics (functions per file, nesting depth)

---

## Mutating Step Types

### 1. BashMutate

Execute shell commands that modify system state (git operations, file creation, system changes).

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | string | Yes | Shell command to execute |
| `timeout` | int | No | Command timeout in seconds (default: 60) |
| `working_dir` | string | No | Directory to execute from (default: current) |
| `dry_run` | bool | No | Simulate without executing (default: false) |
| `require_confirmation` | bool | No | Require user approval (default: true for destructive) |

#### Execution Behavior

1. Validates command is in allowed mutation patterns
2. Checks for destructive patterns (rm, force-push, etc.)
3. Requests confirmation if required
4. Executes command in subprocess
5. Returns exit code and output

#### Error Handling

- **Destructive command denied**: Returns failed StepResult with blocked error
- **Timeout**: Returns failed StepResult after timeout
- **Non-zero exit**: Returns success=False with stderr
- **Dry run**: Returns success=True with dry_run=True flag

#### Example

```python
from src.action.steps import execute_bash_mutate_step

# Create a git commit
result = await execute_bash_mutate_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    command="git commit -m 'feat: add new feature'",
    dry_run=False
)

# Success result
# {
#     "success": true,
#     "data": {
#         "exit_code": 0,
#         "stdout": "[main abc1234] feat: add new feature\\n 1 file changed, 5 insertions(+)",
#         "stderr": "",
#         "command": "git commit -m 'feat: add new feature'",
#         "working_dir": "/home/coding/mta-my-way",
#         "executed": true
#     }
# }

# Dry run result
# {
#     "success": true,
#     "data": {
#         "exit_code": None,
#         "stdout": "",
#         "stderr": "",
#         "command": "git commit -m 'feat: add new feature'",
#         "working_dir": "/home/coding/mta-my-way",
#         "executed": false,
#         "dry_run": true
#     }
# }

# Destructive command blocked
# {
#     "success": false,
#     "data": {
#         "command": "rm -rf /important/data"
#     },
#     "error": "Destructive command blocked: rm -rf patterns require explicit override"
# }
```

#### Use Cases

- Git operations (commit, push, branch)
- File system operations (mkdir, chmod)
- Package management (pip install, npm install)
- Configuration changes
- Deployment scripts
- Database migrations

#### Allowed Patterns (default)

```python
ALLOWED_MUTATIONS = [
    "git *",          # Git operations
    "mkdir *",        # Directory creation
    "touch *",        # File creation
    "chmod *",        # Permission changes
    "pip install *",  # Package installation
    "npm install *",  # Node package installation
    "docker build *", # Container builds
    # Add more as needed
]
```

#### Blocked Patterns (require override)

```python
BLOCKED_PATTERNS = [
    "rm -rf *",       # Recursive delete
    "git push --force",  # Force push
    "DROP *",         # Database drops
    "DELETE FROM",    # SQL deletes
    # Override with confirm_override=True
]
```

---

### 2. Edit

Perform exact string replacements in files for precise, surgical edits.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | Yes | Absolute path to file to edit |
| `old_string` | string | Yes | Exact string to replace (must match exactly) |
| `new_string` | string | Yes | Replacement string |
| `replace_all` | bool | No | Replace all occurrences (default: false) |
| `dry_run` | bool | No | Preview changes without writing (default: false) |

#### Execution Behavior

1. Validates file_path exists and is readable
2. Reads file content
3. Searches for exact old_string match
4. Validates match is unique (unless replace_all=True)
5. Replaces old_string with new_string
6. Writes updated content back to file
7. Returns number of replacements made

#### Error Handling

- **File not found**: Returns failed StepResult with file error
- **No match found**: Returns failed StepResult with "old_string not found"
- **Multiple matches without replace_all**: Returns failed StepResult
- **Write permission denied**: Returns failed StepResult with permission error

#### Example

```python
from src.action.steps import execute_edit_step

# Single replacement
result = await execute_edit_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    file_path="/home/coding/mta-my-way/src/config.py",
    old_string="MAX_POSITION = 1000",
    new_string="MAX_POSITION = 1500"
)

# Success result
# {
#     "success": true,
#     "data": {
#         "file_path": "/home/coding/mta-my-way/src/config.py",
#         "replacements": 1,
#         "old_string": "MAX_POSITION = 1000",
#         "new_string": "MAX_POSITION = 1500",
#         "lines_affected": [42],
#         "dry_run": false,
#         "backup_created": false
#     }
# }

# Multiple replacements with replace_all
result = await execute_edit_step(
    # ... context ...
    file_path="/home/coding/mta-my-way/src/utils.py",
    old_string="print(f\"Debug: {msg}\")",
    new_string="# print(f\"Debug: {msg}\")  # Commented out",
    replace_all=True
)

# {
#     "success": true,
#     "data": {
#         "file_path": "/home/coding/mta-my-way/src/utils.py",
#         "replacements": 5,
#         "old_string": "print(f\"Debug: {msg}\")",
#         "new_string": "# print(f\"Debug: {msg}\")  # Commented out",
#         "lines_affected": [15, 23, 45, 67, 89],
#         "dry_run": false
#     }
# }

# Dry run preview
result = await execute_edit_step(
    # ... context ...
    file_path="/home/coding/mta-my-way/src/main.py",
    old_string="VERSION = \"1.0.0\"",
    new_string="VERSION = \"1.1.0\"",
    dry_run=True
)

# {
#     "success": true,
#     "data": {
#         "file_path": "/home/coding/mta-my-way/src/main.py",
#         "replacements": 0,
#         "old_string": "VERSION = \"1.0.0\"",
#         "new_string": "VERSION = \"1.1.0\"",
#         "dry_run": true,
#         "preview": [
#             {"line": 10, "before": "VERSION = \"1.0.0\"", "after": "VERSION = \"1.1.0\""}
#         ]
#     }
# }
```

#### Use Cases

- Update configuration values
- Fix typos in variable names
- Comment out debug code
- Update version numbers
- Change import paths
- Replace deprecated API calls

#### Best Practices

1. Always verify old_string matches exactly (including whitespace)
2. Use replace_all=True when intentional, otherwise it fails on duplicates
3. Enable dry_run first to preview changes
4. Include sufficient context in old_string to avoid false matches
5. Test on small files before batch operations

---

### 3. Write

Create new files or completely overwrite existing files with new content.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | Yes | Absolute path to file to write |
| `content` | string | Yes | File content to write |
| `create_dirs` | bool | No | Create parent directories (default: true) |
| `backup` | bool | No | Backup existing file before overwrite (default: false) |
| `dry_run` | bool | No | Preview without writing (default: false) |

#### Execution Behavior

1. Validates file_path is absolute
2. Creates parent directories if needed (create_dirs=True)
3. Backs up existing file if requested (backup=True)
4. Writes content to file atomically
5. Verifies file was written successfully
6. Returns bytes written and file metadata

#### Error Handling

- **Relative path**: Returns failed StepResult (requires absolute path)
- **Directory creation failed**: Returns failed StepResult with permission error
- **Write permission denied**: Returns failed StepResult with permission error
- **Disk full**: Returns failed StepResult with disk space error
- **Backup failed**: Returns failed StepResult but continues with write

#### Example

```python
from src.action.steps import execute_write_step

# Create new file
result = await execute_write_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    },
    file_path="/home/coding/mta-my-way/src/new_module.py",
    content='""\"New module for trading calculations."""\n\ndef calculate_profit(entry, exit):\n    """Calculate profit from trade."""\n    return exit - entry\n',
    create_dirs=True
)

# Success result (new file)
# {
#     "success": true,
#     "data": {
#         "file_path": "/home/coding/mta-my-way/src/new_module.py",
#         "bytes_written": 125,
#         "lines_written": 5,
#         "created": true,
#         "overwritten": false,
#         "backup_path": null,
#         "directories_created": [],
#         "dry_run": false
#     }
# }

# Overwrite existing file with backup
result = await execute_write_step(
    # ... context ...
    file_path="/home/coding/mta-my-way/config/settings.yaml",
    content="database:\n  host: localhost\n  port: 5432\n",
    backup=True
)

# Success result (overwrite)
# {
#     "success": true,
#     "data": {
#         "file_path": "/home/coding/mta-my-way/config/settings.yaml",
#         "bytes_written": 45,
#         "lines_written": 3,
#         "created": false,
#         "overwritten": true,
#         "backup_path": "/home/coding/mta-my-way/config/settings.yaml.bak.20260806",
#         "dry_run": false
#     }
# }

# Dry run preview
result = await execute_write_step(
    # ... context ...
    file_path="/home/coding/mta-my-way/README.md",
    content="# My Project\n\nNew description here.",
    dry_run=True
)

# {
#     "success": true,
#     "data": {
#         "file_path": "/home/coding/mta-my-way/README.md",
#         "bytes_written": 0,
#         "lines_written": 0,
#         "dry_run": true,
#         "preview": {
#             "would_create": false,
#             "would_overwrite": true,
#             "content_preview": "# My Project\\n\\nNew description here."
#         }
#     }
# }
```

#### Use Cases

- Create new source files
- Generate configuration files
- Write documentation
- Create test files
- Generate boilerplate code
- Update README files

#### Best Practices

1. Always use absolute paths (relative paths are rejected)
2. Enable backup=True when overwriting important files
3. Use dry_run=True to preview large file writes
4. Include proper line endings (\n for Unix, \r\n for Windows if needed)
5. Verify directory permissions before using create_dirs=True

---

## Cross-Step Patterns

### Pattern 1: Code Analysis Workflow

```python
from src.action.steps import (
    execute_glob_step,
    execute_lsp_document_symbol_step,
    execute_lsp_find_step
)

async def analyze_codebase(ctx: ExecutionContext) -> ActionResult:
    """Analyze codebase structure and find dead code."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="code_analysis",
        status="running",
        started_at=time.time(),
    )
    
    # Step 1: Find all Python files
    files = await execute_glob_step(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        project_slug=ctx.project_slug,
        project_cfg=ctx.project_cfg,
        pattern="**/*.py"
    )
    workflow.add_step(to_step_result(files, "glob"))
    
    # Step 2: Get symbols from each file
    all_symbols = []
    for file_path in files.data.get("matches", []):
        symbols = await execute_lsp_document_symbol_step(
            intent_id=ctx.intent_id,
            session_id=ctx.session_id,
            project_slug=ctx.project_slug,
            project_cfg=ctx.project_cfg,
            file_path=file_path
        )
        workflow.add_step(to_step_result(symbols, f"symbol_{file_path}"))
        all_symbols.extend(symbols.data.get("symbols", []))
    
    # Step 3: Check references for each symbol
    unused_symbols = []
    for symbol in all_symbols:
        refs = await execute_lsp_find_step(
            intent_id=ctx.intent_id,
            session_id=ctx.session_id,
            project_slug=ctx.project_slug,
            project_cfg=ctx.project_cfg,
            file_path=file_path,
            line=symbol["range"]["start_line"],
            character=symbol["range"]["start_char"]
        )
        
        if refs.data.get("total_references", 0) == 0:
            unused_symbols.append(symbol)
    
    workflow.data["unused_symbols"] = unused_symbols
    workflow.status = "completed"
    return finalize_workflow(workflow)
```

### Pattern 2: Safe Refactoring Workflow

```python
async def refactor_symbol(ctx: ExecutionContext) -> ActionResult:
    """Safely rename a symbol across the codebase."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="refactor",
        status="running",
        started_at=time.time(),
    )
    
    # Step 1: Find all references
    refs = await execute_lsp_find_step(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        project_slug=ctx.project_slug,
        project_cfg=ctx.project_cfg,
        file_path=ctx.target_file,
        line=ctx.target_line,
        character=ctx.target_char
    )
    workflow.add_step(to_step_result(refs, "find_references"))
    
    # Step 2: Preview changes with dry_run
    for ref in refs.data.get("references", []):
        edit = await execute_edit_step(
            intent_id=ctx.intent_id,
            session_id=ctx.session_id,
            project_slug=ctx.project_slug,
            project_cfg=ctx.project_cfg,
            file_path=ref["file_path"],
            old_string=ref["context"],
            new_string=ref["context"].replace(ctx.old_name, ctx.new_name),
            dry_run=True
        )
        workflow.add_step(to_step_result(edit, f"preview_{ref['file_path']}"))
    
    # Step 3: Apply changes if confirmed
    if ctx.confirmed:
        for ref in refs.data.get("references", []):
            edit = await execute_edit_step(
                intent_id=ctx.intent_id,
                session_id=ctx.session_id,
                project_slug=ctx.project_slug,
                project_cfg=ctx.project_cfg,
                file_path=ref["file_path"],
                old_string=ref["context"],
                new_string=ref["context"].replace(ctx.old_name, ctx.new_name),
                dry_run=False
            )
            workflow.add_step(to_step_result(edit, f"apply_{ref['file_path']}"))
    
    workflow.status = "completed"
    return finalize_workflow(workflow)
```

### Pattern 3: Documentation Generation

```python
async def generate_docs(ctx: ExecutionContext) -> ActionResult:
    """Generate documentation from code symbols."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="generate_docs",
        status="running",
        started_at=time.time(),
    )
    
    # Step 1: Get all source files
    files = await execute_glob_step(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        project_slug=ctx.project_slug,
        project_cfg=ctx.project_cfg,
        pattern="src/**/*.py"
    )
    
    # Step 2: Extract symbols and docs
    doc_sections = []
    for file_path in files.data.get("matches", []):
        symbols = await execute_lsp_document_symbol_step(
            intent_id=ctx.intent_id,
            session_id=ctx.session_id,
            project_slug=ctx.project_slug,
            project_cfg=ctx.project_cfg,
            file_path=file_path
        )
        
        for symbol in symbols.data.get("symbols", []):
            # Get hover info for documentation
            hover = await execute_lsp_hover_step(
                intent_id=ctx.intent_id,
                session_id=ctx.session_id,
                project_slug=ctx.project_slug,
                project_cfg=ctx.project_cfg,
                file_path=file_path,
                line=symbol["range"]["start_line"],
                character=symbol["range"]["start_char"]
            )
            
            if hover.data.get("hover"):
                doc_sections.append({
                    "name": symbol["name"],
                    "kind": symbol["kind"],
                    "file": file_path,
                    "docs": hover.data["hover"].get("documentation", {})
                })
    
    # Step 3: Write documentation
    markdown = "# API Documentation\n\n"
    for section in doc_sections:
        markdown += f"## {section['name']}\n\n"
        markdown += f"{section['docs'].get('markdown', 'No documentation')}\n\n"
    
    await execute_write_step(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        project_slug=ctx.project_slug,
        project_cfg=ctx.project_cfg,
        file_path=f"{ctx.project_cfg['repo_path']}/docs/api.md",
        content=markdown
    )
    
    workflow.status = "completed"
    return finalize_workflow(workflow)
```

---

## Error Handling Summary

### Error Response Structure

All steps return standardized error responses:

```python
{
    "success": False,
    "data": {...},  # Partial context data
    "error": "Error message describing what went wrong"
}
```

### Common Error Categories

| Error Type | Causes | Recovery Strategy |
|------------|--------|-------------------|
| **Validation Errors** | Missing required fields, invalid parameters | Fix input parameters and retry |
| **File Not Found** | File path doesn't exist | Verify file exists or create it |
| **Permission Denied** | Insufficient permissions | Fix file/directory permissions |
| **LSP Server Errors** | LSP not configured or crashed | Start LSP server or restart it |
| **Timeout Errors** | Operations exceed time limits | Increase timeout or optimize operation |
| **Pattern Match Errors** | String not found for Edit | Verify exact match including whitespace |

### Step-Specific Error Handling

| Step | Common Errors | Handling |
|------|---------------|----------|
| **BashRead** | Command timeout, non-zero exit | Return output with exit code |
| **Glob** | Invalid pattern, directory not found | Return empty list with error |
| **LSPFind** | LSP not available, position invalid | Return empty references |
| **LSPGoToDef** | Symbol not defined, external symbol | Return definition=None |
| **LSPHover** | No hover available, timeout | Return hover=None |
| **LSPDocumentSymbol** | File not found, LSP timeout | Return empty symbols list |
| **BashMutate** | Destructive command blocked | Require override confirmation |
| **Edit** | Old string not found, multiple matches | Require replace_all=True |
| **Write** | Permission denied, disk full | Create directories, free space |

---

## Quick Reference

### Step Type Selection Guide

| Use Case | Recommended Step Type |
|----------|----------------------|
| **Read git log** | `BashRead` |
| **Find source files** | `Glob` |
| **Find symbol usage** | `LSPFind` |
| **Go to definition** | `LSPGoToDef` |
| **Get function docs** | `LSPHover` |
| **List file symbols** | `LSPDocumentSymbol` |
| **Run git commit** | `BashMutate` |
| **Update config value** | `Edit` |
| **Create new file** | `Write` |

### Execution Order in Typical Refactoring Workflow

```
1. Glob (find all affected files)
2. LSPFind (locate all references)
3. LSPHover (get documentation for context)
4. Edit (apply changes with dry_run first)
5. BashMutate (git commit if verified)
```

### Return Value Quick Check

| Step | Success Indicator | Key Fields |
|------|------------------|------------|
| **BashRead** | `data.exit_code == 0` | `stdout`, `stderr` |
| **Glob** | `success == True` | `matches`, `count` |
| **LSPFind** | `success == True` | `references`, `total_references` |
| **LSPGoToDef** | `success == True` | `definition`, `symbol_name` |
| **LSPHover** | `success == True` | `hover`, `documentation` |
| **LSPDocumentSymbol** | `success == True` | `symbols`, `total_symbols` |
| **BashMutate** | `data.exit_code == 0` | `executed`, `dry_run` |
| **Edit** | `success == True` | `replacements`, `lines_affected` |
| **Write** | `success == True` | `bytes_written`, `created/overwritten` |

---

## Parameters Reference Table

### Read-Only Step Parameters

| Step | Parameter | Type | Required | Default | Description |
|------|-----------|------|----------|---------|-------------|
| **BashRead** | `command` | string | Yes | - | Shell command |
| | `timeout` | int | No | 30 | Timeout (seconds) |
| | `working_dir` | string | No | current | Execute directory |
| **Glob** | `pattern` | string | Yes | - | Glob pattern |
| | `root_path` | string | No | repo_path | Search root |
| | `exclude_patterns` | list[str] | No | [] | Patterns to exclude |
| | `max_results` | int | No | 1000 | Max files to return |
| **LSPFind** | `file_path` | string | Yes | - | Symbol location |
| | `line` | int | Yes | - | Line number (1-based) |
| | `character` | int | Yes | - | Character offset |
| | `project_path` | string | No | repo_path | Project root |
| **LSPGoToDef** | `file_path` | string | Yes | - | Reference location |
| | `line` | int | Yes | - | Line number (1-based) |
| | `character` | int | Yes | - | Character offset |
| | `project_path` | string | No | repo_path | Project root |
| **LSPHover** | `file_path` | string | Yes | - | Cursor location |
| | `line` | int | Yes | - | Line number (1-based) |
| | `character` | int | Yes | - | Character offset |
| | `project_path` | string | No | repo_path | Project root |
| **LSPDocumentSymbol** | `file_path` | string | Yes | - | File to analyze |
| | `project_path` | string | No | repo_path | Project root |
| | `include_nested` | bool | No | true | Include nested symbols |

### Mutating Step Parameters

| Step | Parameter | Type | Required | Default | Description |
|------|-----------|------|----------|---------|-------------|
| **BashMutate** | `command` | string | Yes | - | Shell command |
| | `timeout` | int | No | 60 | Timeout (seconds) |
| | `working_dir` | string | No | current | Execute directory |
| | `dry_run` | bool | No | false | Simulate only |
| | `require_confirmation` | bool | No | true | User approval needed |
| **Edit** | `file_path` | string | Yes | - | File to edit |
| | `old_string` | string | Yes | - | Exact match |
| | `new_string` | string | Yes | - | Replacement |
| | `replace_all` | bool | No | false | Replace all occurrences |
| | `dry_run` | bool | No | false | Preview changes |
| **Write** | `file_path` | string | Yes | - | File to write |
| | `content` | string | Yes | - | File content |
| | `create_dirs` | bool | No | true | Create parents |
| | `backup` | bool | No | false | Backup existing |
| | `dry_run` | bool | No | false | Preview only |

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-06  
**Maintained By:** aide-de-camp project  
**Related Documents:**
- `docs/action-step-types-reference.md` (CI/CD step types)
- `docs/action-execution-model-types.md` (Core type definitions)
- `docs/step-result.md` (StepResult detailed documentation)
- `src/action/steps/read.py` (Step implementations)
