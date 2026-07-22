"""
Make Playwright's bundled browser actually launch on NixOS.

Problem
-------
Playwright ships a normal-FHS chromium build. On NixOS the libraries it links
against (libstdc++, libnss3, libglib-2.0, the X11 stack, …) are not in any
standard loader path — they live under hashed ``/nix/store/*`` directories.
This breaks Playwright in *two* places:

1. **Python import.** ``import playwright`` pulls in ``greenlet``, whose C
   extension ``dlopen``s ``libstdc++.so.6`` by soname and fails with
   ``ImportError: libstdc++.so.6: cannot open shared object file``. This happens
   before any user code runs, so the env cannot be fixed lazily.
2. **Browser subprocess.** Even once Playwright imports, the chromium process it
   spawns is missing ~22 shared libraries (``ldd`` reports "not found") and dies
   immediately with ``TargetClosedError``.

The pre-existing canvas suites (``tests/test_canvas_dom_verify.py`` and friends)
worked around this by driving ``src/canvas/canvas.js`` through a Node DOM shim
instead of a real browser, and noted that "Playwright's chromium is missing ~26
FHS libraries" on this host. That left the actual headless-browser verification
(bead adc-jr35) unimplemented.

Solution
--------
This module makes a real headless browser runnable, entirely in-process — no
re-exec, no shell wrapper, no nix-shell — by doing two things before Playwright
is imported:

1. **Preload libstdc++ with ``RTLD_GLOBAL``** via ``ctypes``. That puts the
   soname in the process-global symbol scope, so ``greenlet``'s later ``dlopen``
   resolves it and ``import playwright`` succeeds (no re-exec needed).
2. **Resolve every other missing library dynamically** by running ``ldd`` on the
   chromium binary, then ``find``-ing each "not found" soname under
   ``/nix/store``, and setting the resulting dirs into ``LD_LIBRARY_PATH``. The
   chromium subprocess inherits that env, so it finds its libs.

Resolution is dynamic (not hardcoded nix-store hashes), so it survives a
``nixos-rebuild`` that bumps glib/nss/mesa versions. The resolved path is cached
to disk keyed by the ``ldd`` "not found" signature, so the (slow) ``find``
pass only runs when linkage actually changes — repeated pytest runs pay just one
``ldd`` call.

Call :func:`bootstrap` at the top of ``conftest.py``, before any
``from playwright...`` import. It is idempotent and safe to call unconditionally.
"""
from __future__ import annotations

import ctypes
import glob
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

_CACHE_PATH = Path(__file__).parent / ".browser_libpath_cache.json"
_READY_SENTINEL = "ADC_BROWSER_LIBS_READY"

# Binaries Playwright may launch — resolve libs for whichever exist. Covers both
# the full chromium build and the headless-shell build.
_BROWSER_BIN_GLOBS = [
    os.path.expanduser(
        "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
    ),
    os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
    ),
]

# Candidate sonames the loader may be missing at Python-import time. We preload
# the first one we can locate so `import greenlet` (→ libstdc++) works.
_PRELOAD_CANDIDATES = [
    "libstdc++.so.6",
    "libgcc_s.so.1",
]


def _nix_store_lib_dirs() -> list[str]:
    """Best-effort: dirs that hold FHS libs on this machine.

    ``/nix/store`` is the only place libs live on NixOS; honour an explicit
    ``NIX_LIB_DIRS`` override if a user provides one.
    """
    dirs = ["/nix/store"]
    extra = os.environ.get("NIX_LIB_DIRS", "")
    dirs.extend(d for d in extra.split(":") if d)
    return dirs


def _ldd_missing(binary: str) -> list[str]:
    """Sonames ``ldd`` reports as 'not found' for ``binary``."""
    try:
        out = subprocess.run(
            ["ldd", binary], capture_output=True, text=True, timeout=15
        ).stdout
    except Exception:
        return []
    missing = []
    for line in out.splitlines():
        if "=>" not in line:
            continue
        if "not found" in line:
            soname = line.split()[0]
            if soname:
                missing.append(soname)
    return missing


def _find_in_store(soname: str, *, store_dirs: list[str], timeout: float = 20.0) -> Optional[str]:
    """Return the directory holding ``soname`` under one of ``store_dirs``."""
    for root in store_dirs:
        try:
            res = subprocess.run(
                ["find", root, "-maxdepth", "4", "-name", soname],
                capture_output=True,
                text=True,
                timeout=timeout,
            ).stdout.split()
        except Exception:
            continue
        for hit in res:
            # Avoid the gdb-script suffix etc. — want the bare soname file.
            if os.path.basename(hit) == soname:
                return os.path.dirname(hit)
        if res:
            return os.path.dirname(res[0])
    return None


def _resolve_browser_libpath() -> tuple[list[str], str]:
    """Compute the LD_LIBRARY_PATH needed for the chromium subprocess.

    Returns ``(binary_paths_seen, libpath)``.
    """
    binaries = sorted({b for pat in _BROWSER_BIN_GLOBS for b in glob.glob(pat)})
    store_dirs = _nix_store_lib_dirs()

    missing: list[str] = []
    for binary in binaries:
        for soname in _ldd_missing(binary):
            if soname not in missing:
                missing.append(soname)

    dirs: list[str] = []
    for soname in missing:
        d = _find_in_store(soname, store_dirs=store_dirs)
        if d and d not in dirs:
            dirs.append(d)
    return binaries, ":".join(dirs)


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.write_text(json.dumps(cache))
    except Exception:
        pass  # caching is best-effort


def _missing_signature() -> tuple[str, list[str]]:
    """Cheap, stable signature of what ldd currently can't resolve.

    Used as a cache key: if the set of missing sonames changes (e.g. after a
    nixos-rebuild rewrites glib/nss), the find pass re-runs.
    """
    binaries = sorted({b for pat in _BROWSER_BIN_GLOBS for b in glob.glob(pat)})
    missing: list[str] = []
    for binary in binaries:
        for soname in _ldd_missing(binary):
            if soname not in missing:
                missing.append(soname)
    blob = "\n".join(binaries + missing)
    return hashlib.sha1(blob.encode()).hexdigest(), missing


def _preload_import_time_libs() -> int:
    """Preload libstdc++ (etc.) so `import playwright`/greenlet succeeds.

    Returns the number of candidate libs successfully preloaded. ``RTLD_GLOBAL``
    exposes their symbols process-wide, so a later ``dlopen`` of greenlet's C
    extension resolves its libstdc++ dependency without ``LD_LIBRARY_PATH`` being
    set in the *parent* shell.
    """
    loaded = 0
    store_dirs = _nix_store_lib_dirs()
    for soname in _PRELOAD_CANDIDATES:
        d = _find_in_store(soname, store_dirs=store_dirs)
        if not d:
            continue
        path = os.path.join(d, soname)
        try:
            ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
            loaded += 1
        except OSError:
            continue
    return loaded


def bootstrap(*, force: bool = False) -> bool:
    """Idempotently make Playwright importable + its browser launchable.

    Call once, early (top of conftest, before ``from playwright... import``).
    Returns True if a browser binary was found and wired up, False if none is
    installed (caller should then let the normal "playwright not installed" skip
    path apply).
    """
    if os.environ.get(_READY_SENTINEL) == "1" and not force:
        return True

    # 1) Preload so the *current* process can import playwright/greenlet.
    _preload_import_time_libs()

    # 2) Resolve + cache the subprocess LD_LIBRARY_PATH.
    sig, missing = _missing_signature()
    cache = _load_cache()
    libpath = ""
    if cache.get("sig") == sig and not force:
        libpath = cache.get("libpath", "")
    else:
        binaries, libpath = _resolve_browser_libpath()
        if binaries:
            _save_cache({"sig": sig, "libpath": libpath})

    if libpath:
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = (
            libpath if not existing else f"{libpath}:{existing}"
        )
    os.environ[_READY_SENTINEL] = "1"
    return bool(missing)


__all__ = ["bootstrap"]
