"""
ADC (aide-de-camp) CLI - Universal personal interface.

Provides command-line access to the aide-de-camp server for dispatching utterances,
querying topics, checking session status, and monitoring exceptions.
"""

# Shared version reader (src/_version.py). See the dual-mode note in
# cli/main.py: ./adc puts src/ on sys.path (top-level _version), while an
# import as src.cli resolves it as src._version (two levels up from src.cli).
try:
    from _version import read_version
except ImportError:
    from .._version import read_version

__version__ = read_version()
