"""
Diff engine module.

Exports the DiffEngine class and related types.
"""

from .engine import (
    DiffEngine,
    FieldDiff,
    ResultDiff,
    get_diff_engine,
)

__all__ = [
    "DiffEngine",
    "FieldDiff",
    "ResultDiff",
    "get_diff_engine",
]
