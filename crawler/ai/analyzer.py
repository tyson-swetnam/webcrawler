"""
Multi-AI analysis engine for article classification and summarization.

This module orchestrates parallel AI analysis using Claude, OpenAI, and Gemini
to provide high-quality, consensus-based article summaries and relevance scoring.
"""

import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from google import genai

from crawler.config.settings import settings

logger = logging.getLogger(__name__)


class MultiAIAnalyzer:
    """
    Orchestrate parallel AI analysis across multiple providers.

    Uses Claude Sonnet-4-5 as primary analyzer with OpenAI and Gemini
    for additional validation and consensus building.
    """

    def __init__(self):
        """Initialize AI API clients."""
        try:
            # Initialize Anthropic Claude
            self.claude = AsyncAnthropic(api_key=settings.anthropic_api_key)

            # Initialize OpenAI
            self.openai = AsyncOpenAI(api_key=settings.openai_api_key)

            # Initialize Gemini
            self.gemini_client = genai.Client(api_key=settings.gemini_api_key)

            logger.info("Initialized MultiAIAnalyzer with all three providers")

        except Exception as e:
            logger.error(f"Failed to initialize AI clients: {e}")
            raise

    async def analyze_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze single article with all AI providers in parallel.

        Args:
            article: Article dictionary with title, content, etc.

        Returns:
            Dictionary with results from all providers plus consensus
        """
        start_time = datetime.utcnow()

        # Create analysis tasks for parallel execution
        tasks = [
            self._safe_claude_analyze(article),
            self._safe_openai_analyze(article),
            self._safe_gemini_analyze(article)
        ]

        # Execute in parallel
        claude_result, openai_result, gemini_result = await asyncio.gather(*tasks)

        # Build consensus
        consensus = self.build_consensus(claude_result, openai_result, gemini_result)

        # Calculate processing time
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        result = {
            'article_id': article.get('article_id'),
            'claude': claude_result,
            'openai': openai_result,
            'gemini': gemini_result,
            'consensus': consensus,
            'processing_time_ms': int(processing_time)
        }

        logger.info(
            f"Analyzed article {article.get('article_id')} in {processing_time:.0f}ms "
            f"(providers: {consensus['providers_count']}/3)"
        )

        return result

    async def _safe_claude_analyze(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Safely execute Claude analysis with error handling."""
        try:
            return await self.claude_analyze(article)
        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            return None

    async def _safe_openai_analyze(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Safely execute OpenAI analysis with error handling."""
        try:
            return await self.openai_analyze(article)
        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            return None

    async def _safe_gemini_analyze(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Safely execute Gemini analysis with error handling."""
        try:
            return await self.gemini_analyze(article)
        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            return None

    async def claude_analyze(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep analysis with Claude Sonnet-4-5.

        Provides comprehensive summary, key findings, and relevance scoring.

        Args:
            article: Article data

        Returns:
            Analysis results from Claude
        """
        # Truncate content to fit token limits
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
AI_RELATED: [yes/no]"""

        message = await self.claude.messages.create(
            model=settings.claude_model,
            max_tokens=settings.max_ai_tokens,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text

        # Parse structured response
        parsed = self._parse_claude_response(response_text)

        return {
            'summary': parsed.get('summary', ''),
            'key_points': parsed.get('key_points', []),
            'relevance_score': parsed.get('relevance_score', 5),
            'is_ai_related': parsed.get('is_ai_related', True),
            'raw_response': response_text,
            'model': settings.claude_model
        }

    def _parse_claude_response(self, response: str) -> Dict[str, Any]:
        """Parse structured response from Claude."""
        lines = response.split('\n')
        parsed = {
            'summary': '',
            'key_points': [],
            'relevance_score': 5,
            'is_ai_related': True
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
            elif line.startswith('-') and current_section == 'key_points':
                parsed['key_points'].append(line[1:].strip())
            elif current_section == 'summary' and line and not line.startswith(('KEY_POINTS', 'RELEVANCE', 'AI_RELATED')):
                parsed['summary'] += ' ' + line

        return parsed

    async def openai_analyze(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Categorization and summarization with GPT-4.

        Args:
            article: Article data

        Returns:
            Analysis results from OpenAI
        """
        content = article.get('content', '')[:4000]

        response = await self.openai.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI research analyst. Categorize articles and provide concise summaries."
                },
                {
                    "role": "user",
                    "content": f"""Analyze this article:

Title: {article.get('title', 'Untitled')}
Content: {content}

Provide:
1. A 2-sentence summary
2. Primary category (Machine Learning, NLP, Computer Vision, Robotics, AI Ethics, or Other)
3. Is this AI-related? (yes/no)"""
                }
            ],
            temperature=0.3,
            max_tokens=500
        )

        response_text = response.choices[0].message.content

        # Parse category and AI-related flag
        category = self._extract_category(response_text)
        is_ai_related = 'no' not in response_text.lower() or 'yes' in response_text.lower()

        return {
            'summary': response_text,
            'category': category,
            'is_ai_related': is_ai_related,
            'model': settings.openai_model
        }

    def _extract_category(self, text: str) -> str:
        """Extract category from OpenAI response."""
        categories = [
            'Machine Learning',
            'NLP',
            'Computer Vision',
            'Robotics',
            'AI Ethics'
        ]

        text_lower = text.lower()
        for category in categories:
            if category.lower() in text_lower:
                return category

        return 'Other'

    async def gemini_analyze(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fast processing with Gemini Flash.

        Args:
            article: Article data

        Returns:
            Analysis results from Gemini
        """
        content = article.get('content', '')[:3000]

        prompt = f"""Briefly summarize this AI article in 2-3 sentences and indicate if it's truly AI-related:

Title: {article.get('title', 'Untitled')}
Content: {content}

Format:
SUMMARY: [your summary]
AI_RELATED: [yes/no]"""

        # Note: Gemini API is synchronous in current version
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.gemini_client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt
            )
        )

        response_text = response.text

        # Parse response
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
            'model': settings.gemini_model
        }

    def build_consensus(
        self,
        claude_result: Optional[Dict],
        openai_result: Optional[Dict],
        gemini_result: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Synthesize results from multiple AI providers.

        Args:
            claude_result: Claude analysis results
            openai_result: OpenAI analysis results
            gemini_result: Gemini analysis results

        Returns:
            Consensus summary and metadata
        """
        summaries = []
        is_ai_votes = []
        relevance_scores = []

        # Collect successful results
        if claude_result:
            summaries.append(('claude', claude_result.get('summary', '')))
            is_ai_votes.append(claude_result.get('is_ai_related', True))
            relevance_scores.append(claude_result.get('relevance_score', 5))

        if openai_result:
            summaries.append(('openai', openai_result.get('summary', '')))
            is_ai_votes.append(openai_result.get('is_ai_related', True))

        if gemini_result:
            summaries.append(('gemini', gemini_result.get('summary', '')))
            is_ai_votes.append(gemini_result.get('is_ai_related', True))

        # Determine consensus summary (prefer Claude)
        consensus_summary = "Analysis unavailable"
        if summaries:
            # Use Claude if available, otherwise first available
            for provider, summary in summaries:
                if provider == 'claude':
                    consensus_summary = summary
                    break
            else:
                consensus_summary = summaries[0][1]

        # Determine AI-related consensus (majority vote)
        is_ai_related = sum(is_ai_votes) > len(is_ai_votes) / 2 if is_ai_votes else False

        # Average relevance score
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 5.0

        return {
            'summary': consensus_summary,
            'is_ai_related': is_ai_related,
            'relevance_score': avg_relevance,
            'providers_count': len(summaries),
            'confidence': len(summaries) / 3.0  # 0.33, 0.67, or 1.0
        }

    async def batch_analyze(
        self,
        articles: List[Dict[str, Any]],
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple articles with rate limiting.

        Args:
            articles: List of article dictionaries
            max_concurrent: Maximum concurrent API requests

        Returns:
            List of analysis results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_limit(article):
            async with semaphore:
                return await self.analyze_article(article)

        tasks = [analyze_with_limit(article) for article in articles]
        results = await asyncio.gather(*tasks)

        logger.info(f"Batch analyzed {len(articles)} articles")
        return results

    async def is_ai_related(self, article: Dict[str, Any]) -> bool:
        """
        Quick check if article is AI-related using Gemini (fastest/cheapest).

        Args:
            article: Article data

        Returns:
            True if AI-related, False otherwise
        """
        try:
            result = await self.gemini_analyze(article)
            return result.get('is_ai_related', False)
        except Exception as e:
            logger.error(f"AI relevance check failed: {e}")
            # Default to True to avoid filtering out potential AI articles
            return True
