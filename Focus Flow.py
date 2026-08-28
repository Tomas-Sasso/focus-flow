#!/usr/bin/env python3
"""Focus Flow — lanzador.

    python "Focus Flow.py"
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from focusflow.app import main
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        f"Falta una dependencia: {exc}\n\n"
        "Instalalas con:\n"
        "    pip install customtkinter pillow numpy keyboard miniaudio"
    )

if __name__ == "__main__":
    main()
