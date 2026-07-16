"""
Shared theme taxonomy helpers.

The taxonomy is closed-vocabulary — the model must pick from these ids,
so the dashboard's theme charts stay comparable across runs.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _load_theme_taxonomy() -> Dict[str, Any]:
    """Load the fixed theme taxonomy from crawler/config/themes.json."""
    path = Path(__file__).parent.parent / "config" / "themes.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"Could not load themes.json ({e}); falling back to empty taxonomy")
        return {"version": 0, "themes": []}


THEME_TAXONOMY = _load_theme_taxonomy()
THEME_IDS = {t["id"] for t in THEME_TAXONOMY.get("themes", [])}


def build_themes_prompt_block() -> str:
    """Render the taxonomy as a compact block for the model prompt."""
    themes = THEME_TAXONOMY.get("themes", [])
    if not themes:
        return ""
    lines = [f"- {t['id']}: {t['description']}" for t in themes]
    return "\n".join(lines)


THEMES_PROMPT_BLOCK = build_themes_prompt_block()


def validate_themes(raw: Any) -> List[str]:
    """Return validated, deduplicated theme ids (max 5).

    Accepts a list of ids or a comma/space separated string. Drops tokens
    not in the taxonomy so charts only ever see valid ids.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        cleaned = raw.strip().strip("[]").strip()
        tokens = re.split(r"[,\s]+", cleaned) if cleaned else []
    else:
        tokens = list(raw)

    seen: List[str] = []
    for token in tokens:
        tid = str(token).strip().strip("\"'").lower()
        if tid and tid in THEME_IDS and tid not in seen:
            seen.append(tid)
    return seen[:5]
