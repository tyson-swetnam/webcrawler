"""Shared test configuration.

Sets the minimal environment before any crawler module is imported —
crawler.config.settings instantiates a global Settings() at import time.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

sys.path.insert(0, str(Path(__file__).parent.parent))
