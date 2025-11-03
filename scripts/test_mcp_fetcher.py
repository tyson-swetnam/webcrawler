#!/usr/bin/env python3
"""
Test script for MCP fetcher functionality.

This script tests the MCP fallback mechanism for bypassing bot protection
on university news sites that block Scrapy.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from crawler.utils.mcp_fetcher import MCPFetcher
from crawler.extractors.content import ContentExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_mcp_fetcher():
    """Test MCP fetcher on known blocked URLs."""

    # URLs that are known to block Scrapy with 403 errors
    test_urls = [
        "https://today.ucsd.edu/",
        "https://news.uci.edu/",
        "https://news.berkeley.edu/topics/artificial-intelligence/",
        "https://today.umd.edu/"
    ]

    fetcher = MCPFetcher()
    extractor = ContentExtractor()

    results = []

    for url in test_urls:
        logger.info(f"\n{'='*80}")
        logger.info(f"Testing URL: {url}")
        logger.info(f"{'='*80}")

        # Test if MCP fallback should be used
        should_fallback = fetcher.should_use_mcp_fallback(403, url)
        logger.info(f"Should use MCP fallback for 403: {should_fallback}")

        # Attempt MCP fetch
        try:
            html_content = fetcher.fetch_with_mcp(url)

            if html_content:
                logger.info(f"✓ MCP fetch successful ({len(html_content)} chars)")

                # Try to extract content with Trafilatura
                extracted = extractor.extract_from_html(html_content, url)

                if extracted:
                    logger.info(f"✓ Content extraction successful")
                    logger.info(f"  Title: {extracted.get('title', 'N/A')}")
                    logger.info(f"  Author: {extracted.get('author', 'N/A')}")
                    logger.info(f"  Word count: {extracted.get('word_count', 0)}")
                    logger.info(f"  Language: {extracted.get('language', 'N/A')}")

                    # Validate content quality
                    is_valid = extractor.is_content_valid(extracted, min_words=100)
                    logger.info(f"  Content valid: {is_valid}")

                    results.append({
                        'url': url,
                        'fetch_success': True,
                        'extract_success': True,
                        'content_valid': is_valid,
                        'word_count': extracted.get('word_count', 0)
                    })
                else:
                    logger.warning(f"✗ Content extraction failed")
                    results.append({
                        'url': url,
                        'fetch_success': True,
                        'extract_success': False,
                        'content_valid': False,
                        'word_count': 0
                    })
            else:
                logger.error(f"✗ MCP fetch failed")
                results.append({
                    'url': url,
                    'fetch_success': False,
                    'extract_success': False,
                    'content_valid': False,
                    'word_count': 0
                })

        except Exception as e:
            logger.error(f"✗ Error testing {url}: {e}")
            results.append({
                'url': url,
                'fetch_success': False,
                'extract_success': False,
                'content_valid': False,
                'error': str(e)
            })

    # Print summary
    logger.info(f"\n{'='*80}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*80}")

    total_tests = len(results)
    fetch_successes = sum(1 for r in results if r['fetch_success'])
    extract_successes = sum(1 for r in results if r['extract_success'])
    valid_content = sum(1 for r in results if r['content_valid'])

    logger.info(f"Total URLs tested: {total_tests}")
    logger.info(f"MCP fetch successes: {fetch_successes}/{total_tests} ({fetch_successes/total_tests*100:.1f}%)")
    logger.info(f"Content extraction successes: {extract_successes}/{total_tests} ({extract_successes/total_tests*100:.1f}%)")
    logger.info(f"Valid content: {valid_content}/{total_tests} ({valid_content/total_tests*100:.1f}%)")

    # Get MCP fetcher stats
    stats = fetcher.get_stats()
    logger.info(f"\nMCP Fetcher Statistics:")
    logger.info(f"  Attempts: {stats['fetch_attempts']}")
    logger.info(f"  Successes: {stats['fetch_successes']}")
    logger.info(f"  Failures: {stats['fetch_failures']}")

    # Return success if at least half of the tests passed
    success = fetch_successes >= total_tests / 2
    return success


if __name__ == '__main__':
    try:
        success = test_mcp_fetcher()
        if success:
            logger.info("\n✓ MCP fetcher test PASSED")
            sys.exit(0)
        else:
            logger.error("\n✗ MCP fetcher test FAILED")
            sys.exit(1)
    except Exception as e:
        logger.error(f"\n✗ Test failed with error: {e}", exc_info=True)
        sys.exit(1)
