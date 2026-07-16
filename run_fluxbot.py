"""Frozen / script entrypoint for FluxBot."""
from __future__ import annotations

import sys
from pathlib import Path

# Dev: allow `python run_fluxbot.py` from project root
if not getattr(sys, "frozen", False):
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from app.main import main

if __name__ == "__main__":
    main()
