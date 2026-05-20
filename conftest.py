"""Root conftest: ensure tests run with the repo root on sys.path so that
``from backend.app...`` imports work both locally and in CI.

This file also pins the pytest rootdir to the repo root, which is what we want
since tests reference ``backend.app...`` rather than the installed ``app``
package name.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
