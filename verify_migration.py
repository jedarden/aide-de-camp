#!/usr/bin/env python3
"""
Verification script for context modules migration to canonical fetch stack.

This script verifies that:
1. No modules import from fetch.executor or fetch.strand
2. Context modules use the canonical stack (fetch.commands and fetch.orchestrator)
3. The modules can be imported and instantiated correctly
"""

import sys
import ast
from pathlib import Path


def check_imports(filepath):
    """Check if a Python file imports from old modules."""
    with open(filepath, 'r') as f:
        tree = ast.parse(f.read(), filename=filepath)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                if 'fetch.executor' in node.module or 'fetch.strand' in node.module:
                    return True, f"Found import from {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if 'fetch.executor' in alias.name or 'fetch.strand' in alias.name:
                    return True, f"Found import {alias.name}"

    return False, None


def main():
    """Main verification function."""
    print("Verifying context modules migration to canonical fetch stack...")
    print()

    # Check all Python files in src/
    src_dir = Path('/home/coding/aide-de-camp/src')
    issues = []

    for py_file in src_dir.rglob('*.py'):
        has_old_import, msg = check_imports(py_file)
        if has_old_import:
            issues.append(f"{py_file}: {msg}")

    if issues:
        print("❌ FAILED: Found imports from old modules:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    else:
        print("✅ PASSED: No imports from fetch.executor or fetch.strand")

    # Verify context modules can be imported
    print()
    print("Testing imports...")

    try:
        from src.context import warmer, prefetch
        from src.fetch import commands, orchestrator
        print("✅ PASSED: All modules can be imported")
    except ImportError as e:
        print(f"❌ FAILED: Import error: {e}")
        return 1

    # Verify specific imports
    print()
    print("Verifying specific imports from context modules...")

    try:
        from src.context.warmer import (
            ContextWarmer,
            get_context_warmer,
            get_fetch_strand,
        )
        from src.context.prefetch import (
            SpeculativePrefetcher,
            get_prefetcher,
        )
        from src.fetch.commands import (
            FetchContext,
            FetchSource,
            IntentType,
        )
        from src.fetch.orchestrator import (
            FetchStrand,
            get_fetch_strand as get_orchestrator_strand,
        )
        print("✅ PASSED: All specific imports work correctly")
    except ImportError as e:
        print(f"❌ FAILED: Import error: {e}")
        return 1

    # Verify instantiation
    print()
    print("Testing module instantiation...")

    try:
        warmer = get_context_warmer()
        prefetcher = get_prefetcher()
        strand = get_orchestrator_strand()

        assert warmer is not None
        assert prefetcher is not None
        assert strand is not None

        print("✅ PASSED: All singletons can be instantiated")
    except Exception as e:
        print(f"❌ FAILED: Instantiation error: {e}")
        return 1

    print()
    print("=" * 60)
    print("✅ ALL CHECKS PASSED - Migration is complete!")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
