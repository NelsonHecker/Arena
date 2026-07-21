"""Bootstrap for the arena CLI, exec'd as `python -E -S __main__.py` by the shell shim."""

import importlib
import os
import sys

_venv = os.environ.get("ARENA_VENV_DIR") or os.environ.get("VIRTUAL_ENV")
if _venv:
    _lib = os.path.join(_venv, "lib")
    if os.path.isdir(_lib):
        for _entry in sorted(os.listdir(_lib)):
            _sp = os.path.join(_lib, _entry, "site-packages")
            if os.path.isdir(_sp):
                sys.path.append(_sp)

try:
    _cli = importlib.import_module("cli")
except ImportError as e:
    sys.stderr.write(f"arena: CLI failed to start ({e})\n")
    sys.exit(113)
_cli.main(prog_name="arena")
