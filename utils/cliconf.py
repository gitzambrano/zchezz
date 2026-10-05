"""Small optional CLI override helper.

Repository tools must work from their in-file defaults with no arguments.
This module only provides optional overrides plus a non-destructive
``--show-config`` inspection mode. It contains no workflow, version-selection,
file-system, build, or process-launch policy.
"""
from __future__ import annotations
import argparse
from typing import Any, Mapping, MutableMapping, Sequence

def force_utf8_stdio() -> None:
    import sys
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError): pass

def _dest(flag: str) -> str: return flag.lstrip("-").replace("-", "_")

def build_parser(config: Mapping[str, Any], spec: Sequence[tuple], *, prog=None, description=None, epilog=None):
    parser = argparse.ArgumentParser(prog=prog, description=description, epilog=epilog)
    parser.add_argument("--show-config", action="store_true", help="print resolved defaults/overrides and exit")
    for entry in spec:
        name, flag, kind, help_text = entry[:4]
        choices = entry[4] if len(entry) > 4 else None
        if name not in config: raise KeyError(f"CLI option {name!r} has no configuration constant")
        kwargs = {"dest": _dest(flag), "default": config[name], "help": help_text}
        if kind is bool: parser.add_argument(flag, action=argparse.BooleanOptionalAction, **kwargs)
        elif kind is list:
            kwargs["action"] = "append"; kwargs["default"] = None; parser.add_argument(flag, **kwargs)
        else:
            if kind is not None: kwargs["type"] = kind
            if choices is not None: kwargs["choices"] = tuple(choices)
            parser.add_argument(flag, **kwargs)
    return parser

def override_from_cli(config: MutableMapping[str, Any], spec: Sequence[tuple], argv=None, *, prog=None, description=None, epilog=None):
    parser = build_parser(config, spec, prog=prog, description=description, epilog=epilog)
    args = parser.parse_args(argv)
    for entry in spec:
        name, flag, kind = entry[:3]
        value = getattr(args, _dest(flag))
        if kind is list and value is None: value = config[name]
        config[name] = value
    if args.show_config:
        print("Resolved configuration:")
        for entry in spec: print(f"  {entry[0]} = {config[entry[0]]!r}")
        raise SystemExit(0)
    return args

def print_config(config: Mapping[str, Any], spec: Sequence[tuple], prefix: str = "  ") -> None:
    for entry in spec: print(f"{prefix}{entry[0]} = {config[entry[0]]!r}")
