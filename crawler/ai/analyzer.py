"""
Multi-AI analysis engine for article classification and summarization.

Uses Claude Sonnet as the primary deep-analysis model and Claude Haiku
for fast validation/filtering. OpenAI has been removed.
"""

import asyncio
import re
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging

from anthropic import AsyncAnthropic

from crawler.config.settings import settings

logger = logging.getLogger(__name__)


class MultiAIAnalyzer:
    """
    Orchestrate parallel AI analysis using Claude Sonnet + Claude Haiku.

    Sonnet handles deep analysis; Haiku provides fast cross-validation.
    Confidence = 0.5 (Haiku only), 1.0 (both succeed).
    """

    def __init__(self):
        """Initialize Anthropic client (single client for both Sonnet and Haiku)."""
        try:
            self.claude = AsyncAnthropic(api_key=settings.anthropic_api_key)
            logger.info(
                f"Initialized MultiAIAnalyzer with Claude Sonnet ({settings.claude_model}) "
                f"+ Haiku ({settings.claude_haiku_model})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}")
            raise

    async def analyze_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a single article with Sonnet + Haiku in parallel.

        Returns:
            Dictionary with claude, haiku, and consensus results.
        """
        start_time = datetime.utcnow()

        claude_result, haiku_result = await asyncio.gather(
            self._safe_claude_analyze(article),
            self._safe_haiku_analyze(article),
        )

        consensus = self.build_consensus(claude_result, haiku_result)

        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        result = {
            'article_id': article.get('article_id'),
            'claude': claude_result,
            'openai': None,   # kept for DB schema compatibility
            'haiku': haiku_result,
            'consensus': consensus,
            'processing_time_ms': int(processing_time),
        }

        logger.info(
            f"Analyzed article {article.get('article_id')} in {processing_time:.0f}ms "
            f"(providers: {consensus['providers_count']}/2)"
        )
        return result

    # ------------------------------------------------------------------ #
    #  Safe wrappers
    # ------------------------------------------------------------------ #

    async def _safe_claude_analyze(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return await self.claude_analyze(article)
        except Exception as e:
            logger.error(f"Claude Sonnet analysis failed: {e}")
            return None

    async def _safe_haiku_analyze(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return await self.haiku_analyze(article)
        except Exception as e:
            logger.error(f"Claude Haiku analysis failed: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Claude Sonnet — deep analysis
    # ------------------------------------------------------------------ #

    async def claude_analyze(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep analysis with Claude Sonnet.

        Provides comprehensive summary, key findings, and relevance scoring.
        """
        content = article.get('content', '')[:4000]

        prompt = f"""Analyze this AI research article and provide:

1. A concise 2-3 sentence summary of the main findings
2. 3-5 key points or innovations (as a bullet list)
3. Relevance score (1-10 scale) indicating how significant this AI research is
4. Whether this is truly AI-related (yes/no)

Article Title: {article.get('title', 'Untitled')}
Content: {content}

Provide structured output in this format:
SUMMARY: [your 2-3 sentence summary]
KEY_POINTS:
- [point 1]
- [point 2]
- [point 3]
RELEVANCE: [score 1-10]
AI_RELATED: [yes/no]
SCIENTIFIC_IMPACT: [1-10, how significant is the scientific or technological innovation]
FINANCIAL_IMPACT: [1-10, based on dollar figures: billions=9-10, hundreds of millions=7-8, tens of millions=5-6, smaller or none=1-4]
PARTNERSHIP_IMPACT: [1-10, significance of new partnerships between academia, government, and industry]"""

        message = await self.claude.messages.create(
            model=settings.claude_model,
            max_tokens=settings.max_ai_tokens,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text
        parsed = self._parse_claude_response(response_text)

        return {
            'summary': parsed.get('summary', ''),
            'key_points': parsed.get('key_points', []),
            'relevance_score': parsed.get('relevance_score', 5),
            'is_ai_related': parsed.get('is_ai_related', True),
            'impact_scores': {
                'scientific': parsed.get('scientific_impact', 1.0),
                'financial': parsed.get('financial_impact', 1.0),
                'partnership': parsed.get('partnership_impact', 1.0),
            },
            'raw_response': response_text,
            'model': settings.claude_model,
        }

    def _parse_claude_response(self, response: str) -> Dict[str, Any]:
        """Parse structured response from Claude."""
        lines = response.split('\n')
        parsed = {
            'summary': '',
            'key_points': [],
            'relevance_score': 5,
            'is_ai_related': True,
            'scientific_impact': 1.0,
            'financial_impact': 1.0,
            'partnership_impact': 1.0,
        }

        current_section = None

        for line in lines:
            line = line.strip()

            if line.startswith('SUMMARY:'):
                parsed['summary'] = line.replace('SUMMARY:', '').strip()
                current_section = 'summary'
            elif line.startswith('KEY_POINTS:'):
                current_section = 'key_points'
            elif line.startswith('RELEVANCE:'):
                try:
                    score_text = line.replace('RELEVANCE:', '').strip()
                    parsed['relevance_score'] = float(score_text.split()[0])
                except (ValueError, IndexError):
                    pass
            elif line.startswith('AI_RELATED:'):
                ai_text = line.replace('AI_RELATED:', '').strip().lower()
                parsed['is_ai_related'] = ai_text.startswith('yes')
                current_section = None
            elif line.startswith('SCIENTIFIC_IMPACT:'):
                try:
                    score_text = line.replace('SCIENTIFIC_IMPACT:', '').strip()
                    parsed['scientific_impact'] = float(score_text.split()[0].split('/')[0])
                except (ValueError, IndexError):
                    parsed['scientific_impact'] = 1.0
                current_section = None
            elif line.startswith('FINANCIAL_IMPACT:'):
                try:
                    score_text = line.replace('FINANCIAL_IMPACT:', '').strip()
                    parsed['financial_impact'] = float(score_text.split()[0].split('/')[0])
                except (ValueError, IndexError):
                    parsed['financial_impact'] = 1.0
                current_section = None
            elif line.startswith('PARTNERSHIP_IMPACT:'):
                try:
                    score_text = line.replace('PARTNERSHIP_IMPACT:', '').strip()
                    parsed['partnership_impact'] = float(score_text.split()[0].split('/')[0])
                except (ValueError, IndexError):
                    parsed['partnership_impact'] = 1.0
                current_section = None
            elif line.startswith('-') and current_section == 'key_points':
                parsed['key_points'].append(line[1:].strip())
            elif (
                current_section == 'summary'
                and line
                and not line.startswith(
                    ('KEY_POINTS', 'RELEVANCE', 'AI_RELATED',
                     'SCIENTIFIC_IMPACT', 'FINANCIAL_IMPACT', 'PARTNERSHIP_IMPACT')
                )
            ):
                parsed['summary'] += ' ' + line

        return parsed

    # ------------------------------------------------------------------ #
    #  Claude Haiku — fast validation
    # ------------------------------------------------------------------ #

    async def haiku_analyze(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Fast processing with Claude Haiku for cross-validation."""
        content = article.get('content', '')[:3000]

        prompt = f"""Briefly summarize this AI article in 2-3 sentences and indicate if it's truly AI-related:

Title: {article.get('title', 'Untitled')}
Content: {content}

Format:
SUMMARY: [your summary]
AI_RELATED: [yes/no]"""

        message = await self.claude.messages.create(
            model=settings.claude_haiku_model,
            max_tokens=settings.max_haiku_tokens,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text

        is_ai_related = True
        summary = response_text

        if 'AI_RELATED:' in response_text:
            parts = response_text.split('AI_RELATED:')
            if len(parts) > 1:
                is_ai_related = 'yes' in parts[1].lower()
            if 'SUMMARY:' in parts[0]:
                summary = parts[0].replace('SUMMARY:', '').strip()

        return {
            'summary': summary,
            'is_ai_related': is_ai_related,
            'model': settings.claude_haiku_model,
        }

    # ------------------------------------------------------------------ #
    #  Consensus builder
    # ------------------------------------------------------------------ #

    def build_consensus(
        self,
        claude_result: Optional[Dict],
        haiku_result: Optional[Dict],
        # kept for call-site compatibility; ignored
        openai_result: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Synthesize results from Claude Sonnet + Haiku.

        Confidence:
          - 1.0 → both providers succeeded and agree
          - 0.8 → both succeeded but disagree (majority wins)
          - 0.5 → only one provider succeeded
          - 0.0 → all failed
        """
        summaries = []
        is_ai_votes = []
        relevance_scores = []

        if claude_result:
            summaries.append(('claude', claude_result.get('summary', '')))
            is_ai_votes.append(claude_result.get('is_ai_related', True))
            relevance_scores.append(claude_result.get('relevance_score', 5))

        if haiku_result:
            summaries.append(('haiku', haiku_result.get('summary', '')))
            is_ai_votes.append(haiku_result.get('is_ai_related', True))

        if not summaries:
            logger.warning("All AI providers failed — returning uncertain consensus")
            return {
                'summary': 'Analysis unavailable',
                'is_ai_related': None,
                'relevance_score': 0,
                'providers_count': 0,
                'confidence': 0.0,
            }

        # Prefer Claude Sonnet summary; fall back to Haiku
        consensus_summary = next(
            (s for p, s in summaries if p == 'claude'),
            summaries[0][1]
        )

        # Majority vote on AI-related
        is_ai_related = sum(is_ai_votes) > len(is_ai_votes) / 2

        # Agreement bonus
        providers_count = len(summaries)
        if providers_count == 2:
            agreement = is_ai_votes[0] == is_ai_votes[1]
            confidence = 1.0 if agreement else 0.8
        else:
            confidence = 0.5  # single provider

        avg_relevance = (
            sum(relevance_scores) / len(relevance_scores) if relevance_scores else 5.0
        )

        return {
            'summary': consensus_summary,
            'is_ai_related': is_ai_related,
            'relevance_score': avg_relevance,
            'providers_count': providers_count,
            'confidence': confidence,
        }

    # ------------------------------------------------------------------ #
    #  Batch + quick-check helpers
    # ------------------------------------------------------------------ #

    async def batch_analyze(
        self,
        articles: List[Dict[str, Any]],
        max_concurrent: int = 5,
    ) -> List[Dict[str, Any]]:
        """Analyze multiple articles with rate limiting."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_limit(article):
            async with semaphore:
                return await self.analyze_article(article)

        results = await asyncio.gather(*[analyze_with_limit(a) for a in articles])
        logger.info(f"Batch analyzed {len(articles)} articles")
        return results

    async def is_ai_related(self, article: Dict[str, Any]) -> bool:
        """Quick AI-relevance check using Claude Haiku."""
        try:
            result = await self.haiku_analyze(article)
            return result.get('is_ai_related', False)
        except Exception as e:
            logger.error(f"AI relevance check failed: {e}")
            return True  # default to True to avoid false negatives

    # ------------------------------------------------------------------ #
    #  Stub kept for any call-sites that still reference openai_analyze
    # ------------------------------------------------------------------ #

    async def openai_analyze(self, article: Dict[str, Any]) -> None:  # type: ignore[override]
        """OpenAI removed — returns None for backward compatibility."""
        logger.debug("openai_analyze called but OpenAI is disabled; returning None")
        return None
