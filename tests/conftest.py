"""Put both import roots on `sys.path` so `pytest` works from a clean
clone without any `PYTHONPATH` nudge.

This project uses implicit namespace packages (there is no
`src/__init__.py`), and two run conventions coexist by design:

- the `news_features` side is run as `python3 -m src.news_features.xxx`
  and imports with the `src.` prefix -> needs the **repo root** on the path;
- the `news_modelling` side is run as `PYTHONPATH=src python3 -m
  news_modelling.xxx` and imports bare -> needs **`src/`** on the path.

Adding both here reproduces exactly the path state under which the full
suite already passes (`PYTHONPATH=src pytest`), so a plain `pytest`
collects every test instead of half of them.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
