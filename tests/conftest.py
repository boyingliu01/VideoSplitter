"""pytest configuration — adds project root to sys.path."""
from __future__ import annotations

import os
import sys

# Add project root to sys.path
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)
