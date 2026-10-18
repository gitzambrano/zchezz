"""Forward legacy entry points to one canonical implementation."""
import importlib
import sys


def redirect(name, target):
    """Preserve module identity for callers and command execution."""
    module = importlib.import_module(target)
    if name == "__main__":
        raise SystemExit(module.main())
    sys.modules[name] = module
