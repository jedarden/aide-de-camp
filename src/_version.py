"""
Single source of truth for the package version.

The canonical version is ``[project] version`` in ``pyproject.toml`` -- per
CLAUDE.md ("Versioning"), it must never be hardcoded anywhere else. Both the
FastAPI server (``src/main.py``) and the CLI (``src/cli/main.py``) read it
through :func:`read_version` so the value can never drift between call sites.

``pyproject.toml`` is resolved relative to this file (``src/_version.py`` ->
repo root), so the version is correct regardless of the caller's working
directory -- e.g. when ``./adc`` is invoked from outside the repo. If the file
genuinely cannot be read, we fall back to ``"0.0.0"`` rather than crash.
"""

from pathlib import Path


def read_version() -> str:
    """Return the project version from pyproject.toml, or ``"0.0.0"`` if unreadable."""
    try:
        import tomllib

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        return tomllib.loads(pyproject.read_text())["project"]["version"]
    except Exception:
        return "0.0.0"
