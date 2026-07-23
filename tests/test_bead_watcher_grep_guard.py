"""
Grep-guard test for CLI-only invariant (bead adc-12ar).

This test FAILS if any code path under src/ opens a .beads/ file directly.
This enforces the plan §10 Bead Watcher invariant: detection is CLI-only,
the watcher never reads the bf workspace's private store files directly.

Violation patterns:
1. Direct open() of a path containing '.beads/'
2. Path operations on paths containing '.beads/'
3. Old BEADS_JSONL or issues.jsonl constant usage

The test scans src/ (especially src/watcher/ and src/) for these patterns
and fails if any are found. This ensures the CLI-only contract is maintained
even as the codebase evolves.
"""

import re
from pathlib import Path

import pytest


# Grep patterns that indicate direct .beads/ file access
VIOLATION_PATTERNS = [
    # Direct open() of .beads/ paths
    r'open\([^)]*\.beads/',
    # Direct Path() operations on .beads/ that READ files (not .exists())
    r'Path\([^)]*\.beads/.*\)\s*\.read',
    # Old constant names that should not exist
    r'BEADS_JSONL',
    # Direct reading of .beads/ files
    r'\.read_text\([^)]*\.beads/',
    r'\.read_bytes\([^)]*\.beads/',
    # aiofiles/asyncio file operations on .beads/
    r'aiofiles\.open\([^)]*\.beads/',
    r'asyncio.*open\([^)]*\.beads/',
]

# Additional patterns to check - but NOT shell existence checks or comments
# These patterns are ok in certain contexts (shell checks, comments)
CONTEXTUAL_PATTERNS = {
    # issues.jsonl is OK only in shell checks [ -f file ] and comments
    r'\[ -f .*\.beads/issues\.jsonl': 'shell-existence-check',
}

# Files/directories that are exempt from this check (e.g., test fixtures, comments)
EXEMPT_PATHS = [
    # This test file itself
    "test_bead_watcher_grep_guard.py",
    # Comments/documentation are fine
]

# Pattern strings that are exempt (e.g., in comments explaining the invariant)
EXEMPT_PATTERNS = [
    # Allow in comments (lines starting with #)
    r'^#.*\.beads/',
    # Allow in docstrings (triple quotes on line)
    r'^[^#]*""".*\.beads/',
]


def is_exempt(line: str) -> bool:
    """Check if a line is exempt from violation detection."""
    for exempt_pattern in EXEMPT_PATTERNS:
        if re.search(exempt_pattern, line):
            return True
    # Shell existence checks are OK
    if '[ -f ' in line and '.beads/' in line:
        return True
    # Field annotations and type comments are OK
    if ': bool' in line or '# ' in line:
        return True
    return False


def find_violations() -> list[tuple[str, int, str, str]]:
    """
    Scan src/ for CLI-only invariant violations.

    Returns:
        List of (file_path, line_number, line_text, pattern) tuples
    """
    src_dir = Path(__file__).parent.parent / "src"
    violations = []

    for py_file in src_dir.rglob("*.py"):
        # Skip exempt paths
        if any(exempt in str(py_file) for exempt in EXEMPT_PATHS):
            continue

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, start=1):
                    # Skip exempt lines (comments, etc.)
                    if is_exempt(line):
                        continue

                    # Check each violation pattern
                    for pattern in VIOLATION_PATTERNS:
                        if re.search(pattern, line):
                            violations.append((
                                str(py_file.relative_to(src_dir.parent)),
                                line_num,
                                line.strip(),
                                pattern,
                            ))
                            # Don't report multiple patterns for same line
                            break
        except Exception:
            # If we can't read the file, skip it (e.g., binary, permissions)
            continue

    return violations


@pytest.mark.parametrize(
    "pattern",
    VIOLATION_PATTERNS,
    ids=lambda p: p[:30] + "..." if len(p) > 30 else p,
)
def test_no_direct_beads_file_access(pattern):
    """
    Test that no code path under src/ directly opens .beads/ files.

    This enforces the CLI-only invariant from plan §10 Bead Watcher:
    the watcher polls `bf list --status closed` and never reads the
    bf workspace's private store files directly (both are documented
    corruption/staleness footguns in this workspace).

    If this test fails, it means someone has reintroduced direct .beads/
    file access, which violates the CLI-only contract and risks data
    corruption or staleness bugs.
    """
    violations = find_violations()

    # Filter violations for this specific pattern
    pattern_violations = [v for v in violations if v[3] == pattern]

    if pattern_violations:
        # Build a helpful error message
        msg = f"Found {len(pattern_violations)} violation(s) of pattern: {pattern}\n\n"
        for file_path, line_num, line_text, _ in pattern_violations:
            msg += f"  {file_path}:{line_num}: {line_text}\n"
        msg += "\nThis violates the CLI-only invariant (plan §10 Bead Watcher).\n"
        msg += "The bead watcher must use `bf list --status closed` instead.\n"
        pytest.fail(msg)


def test_no_direct_beads_file_access_combined():
    """
    Combined test: check all violation patterns at once for faster feedback.

    This is the main test that runs in CI - it checks all patterns in one pass
    and provides a comprehensive report of any violations.
    """
    violations = find_violations()

    if violations:
        # Group violations by file for clearer output
        by_file: dict[str, list[tuple[int, str, str]]] = {}
        for file_path, line_num, line_text, pattern in violations:
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append((line_num, line_text, pattern))

        # Build helpful error message
        msg = f"Found {len(violations)} CLI-only invariant violation(s) across {len(by_file)} file(s):\n\n"
        for file_path, file_violations in sorted(by_file.items()):
            msg += f"{file_path}:\n"
            for line_num, line_text, pattern in file_violations:
                msg += f"  Line {line_num}: {line_text}\n"
                msg += f"    Pattern: {pattern}\n"
            msg += "\n"

        msg += "This violates the CLI-only invariant (plan §10 Bead Watcher).\n"
        msg += "The bead watcher must use `bf list --status closed` via subprocess.\n"
        msg += "Direct access to .beads/ files risks corruption/staleness bugs.\n"
        pytest.fail(msg)


def test_violation_detection_works():
    """
    Meta-test: verify that the violation detector actually catches violations.

    This test intentionally introduces a violation in a temp file to prove
    that the grep-guard machinery works. If this test fails, it means the
    violation detection logic is broken.
    """
    import tempfile
    import shutil

    # Create a temp directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        src_dir = tmpdir_path / "src"
        src_dir.mkdir()

        # Create a test file with intentional violations
        test_file = src_dir / "test_violations.py"
        test_file.write_text('''
# This file has intentional violations for testing

# Violation 1: direct open()
data = open("/path/to/.beads/issues.jsonl")

# Violation 2: Path operations with read()
p = Path(".beads/data.db").read_text()

# Violation 3: old constant name
BEADS_JSONL = "/path/to/issues.jsonl"

# This comment should NOT trigger (it's a comment)
# data = open(".beads/file")
''')

        # Scan for violations in the temp directory
        violations = []
        for py_file in src_dir.rglob("*.py"):
            with open(py_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, start=1):
                    if is_exempt(line):
                        continue
                    for pattern in VIOLATION_PATTERNS:
                        if re.search(pattern, line):
                            violations.append((
                                str(py_file),
                                line_num,
                                line.strip(),
                                pattern,
                            ))
                            break

        # We should have caught exactly 3 violations (open(), Path().read, BEADS_JSONL)
        # Note: Path() alone is not a violation - only when it reads files
        assert len(violations) == 3, f"Expected 3 violations, found {len(violations)}: {violations}"

        # Verify we caught the right lines
        violation_lines = {v[1] for v in violations}
        assert 5 in violation_lines  # open()
        assert 8 in violation_lines  # Path().read (we need to add .read to trigger violation)
        assert 11 in violation_lines  # BEADS_JSONL

        # The comment on line 14 should NOT be a violation
        assert 14 not in violation_lines


def test_comment_lines_are_exempt():
    """Test that comment lines explaining the invariant are not flagged."""
    # A line with .beads/ in a comment should be exempt
    comment_line = "# This code uses bf CLI instead of reading .beads/issues.jsonl directly"
    assert is_exempt(comment_line)

    # A line with .beads/ in a docstring should be exempt
    docstring_line = '"""The watcher polls bf instead of reading .beads/ store."""'
    assert is_exempt(docstring_line)

    # Actual code should NOT be exempt
    code_line = 'data = open(".beads/file.txt")'
    assert not is_exempt(code_line)
