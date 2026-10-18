"""Share Colab settings and preserve legacy imports."""
from pathlib import Path
for _directory in ("playwright", "playwright/diagnostics", "remote"):
    __path__.append(str(Path(__file__).resolve().parent / _directory))
