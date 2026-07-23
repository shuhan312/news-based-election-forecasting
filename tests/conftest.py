"""Make the repo root importable as `src.news_collection...` regardless
of which directory pytest is invoked from - there is no src/__init__.py
(this project uses implicit namespace packages, matching how every
`python3 -m src.news_collection.xxx` script in this repo is already
run), so pytest needs a nudge to find it without one.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
