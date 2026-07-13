"""pytest configuration — adds project root to sys.path and provides mock helpers."""
from __future__ import annotations

import importlib.util
import os
import sys

# Add project root to sys.path
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)


def _load_gui_module(package_path: str, module_name: str):
    """Load a module from gui/ using importlib to avoid tests/gui/ namespace clash.

    Mock PySide6 before loading, using a proper QObject mock that accepts parent arg.
    """
    filepath = os.path.join(_proj_root, "gui", *package_path.split("."), f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    mod = importlib.util.module_from_spec(spec)

    # Ensure the mod's __package__ resolves relative imports within gui/
    mod.__package__ = f"gui.{package_path}" if package_path else "gui"

    spec.loader.exec_module(mod)
    return mod
