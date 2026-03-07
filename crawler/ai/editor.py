"""
Editorial Curator - Claude as Daily News Editor for Top News selection.

Performs batch curation of high-impact articles, selecting and ranking
the top stories with editorial context.
"""

import re
import logging
from typing import List, Dict, Any

from anthropic import AsyncAnthropic

from crawler.config.settings import settings

logger = logging.getLogger(__name__)


class EditorialCurator:
    """Batch editorial curation — Claude as Daily News Editor."""

    def __init__(self):
        self.claude = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def curate_top_news(self, candidates: List[Dict], max_picks: int = 10) -> List[Dict]:
        """
        Select and rank top news stories from today's articles.

        Args:
            candidates: List of article dicts with article_metadata containing impact_scores
            max_picks: Maximum number of top stories to select

        Returns:
            List of editorial picks with rank, article_id, editorial_note, impact_category
        """
        filtered = self._select_candidates(candidates)

        if len(filtered) < 3:
            logger.info(f"Editorial curation: only {len(filtered)} candidates (need 3+), skipping")
            return []

        try:
            prompt = self._build_prompt(filtered, max_picks)

            message = await self.claude.messages.create(
                model=settings.claude_model,
                max_tokens=2000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            picks = self._parse_editorial_response(response_text)

            logger.info(f"Editorial curation: selected {len(picks)} top stories from {len(filtered)} candidates")
            return picks

        except Exception as e:
            logger.warning(f"Editorial curation API call failed (non-fatal): {e}")
            return []

    def _select_candidates(self, articles: List[Dict]) -> List[Dict]:
        """Filter and rank articles by impact scores for editorial consideration."""
        candidates = []

        for art in articles:
            metadata = art.get('article_metadata') or {}
            scores = metadata.get('impact_scores', {})

            scientific = float(scores.get('scientific', 1.0))
            financial = float(scores.get('financial', 1.0))
            partnership = float(scores.get('partnership', 1.0))
            composite = (scientific + financial + partnership) / 3.0

            # Include if any single score >= 6 OR composite average >= 5.0
            if scientific >= 6 or financial >= 6 or partnership >= 6 or composite >= 5.0:
                candidates.append({
                    **art,
                    '_composite': composite,
                    '_scores': {
                        'scientific': scientific,
                        'financial': financial,
                        'partnership': partnership,
                    }
                })

        # Sort by composite score descending, take top 50
        candidates.sort(key=lambda x: x['_composite'], reverse=True)
        return candidates[:50]

    def _build_prompt(self, candidates: List[Dict], max_picks: int) -> str:
        """Build the editorial curation prompt."""
        articles_text = []
        for c in candidates:
            scores = c['_scores']
            summary = (c.get('consensus_summary') or '')[:200]
            articles_text.append(
                f"ARTICLE_ID: {c['article_id']}\n"
                f"TITLE: {c.get('title', 'Untitled')}\n"
                f"UNIVERSITY: {c.get('university_name', 'Unknown')}\n"
                f"SUMMARY: {summary}\n"
                f"SCORES: Scientific={scores['scientific']}, Financial={scores['financial']}, Partnership={scores['partnership']}"
            )

        articles_block = "\n\n".join(articles_text)

        return f"""You are the Daily News Editor for an AI university news aggregator. Your job is to select the {max_picks} most important stories from today's articles and explain why each matters.

Select stories that represent genuine significance: major scientific breakthroughs, transformative funding announcements (hundreds of millions or billions), landmark partnerships between academia/government/industry, or important policy changes affecting AI research.

Here are today's candidate articles:

{articles_block}

For each pick, provide output in this exact format:

PICK_1:
ARTICLE_ID: [id]
EDITORIAL_NOTE: [1-2 sentences explaining why this story matters]
IMPACT_CATEGORY: [exactly one of: Scientific Breakthrough, Major Funding, Strategic Partnership, Policy Impact]

PICK_2:
ARTICLE_ID: [id]
EDITORIAL_NOTE: [1-2 sentences explaining why this story matters]
IMPACT_CATEGORY: [exactly one of: Scientific Breakthrough, Major Funding, Strategic Partnership, Policy Impact]

Continue for up to {max_picks} picks. Only include stories that are truly significant — if fewer than {max_picks} qualify, include fewer. Rank them by importance (PICK_1 is most important)."""

    def _parse_editorial_response(self, response: str) -> List[Dict]:
        """Parse editorial picks from Claude's response."""
        picks = []

        # Split on PICK_N: markers
        sections = re.split(r'PICK_\d+:', response)

        for i, section in enumerate(sections[1:], start=1):  # skip text before first PICK
            pick = {'rank': i}

            # Extract ARTICLE_ID
            id_match = re.search(r'ARTICLE_ID:\s*(\d+)', section)
            if not id_match:
                continue
            pick['article_id'] = int(id_match.group(1))

            # Extract EDITORIAL_NOTE
            note_match = re.search(r'EDITORIAL_NOTE:\s*(.+?)(?=\n\s*(?:IMPACT_CATEGORY|ARTICLE_ID|PICK_|$))', section, re.DOTALL)
            if note_match:
                pick['editorial_note'] = note_match.group(1).strip()
            else:
                pick['editorial_note'] = ''

            # Extract IMPACT_CATEGORY
            cat_match = re.search(r'IMPACT_CATEGORY:\s*(.+?)(?=\n|$)', section)
            if cat_match:
                pick['impact_category'] = cat_match.group(1).strip()
            else:
                pick['impact_category'] = 'Scientific Breakthrough'

            picks.append(pick)

        return picks
