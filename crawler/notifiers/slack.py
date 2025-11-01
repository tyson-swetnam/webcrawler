"""
Slack notification integration using webhooks.

This module sends formatted article digests to Slack channels
using the Block Kit format for rich, interactive messages.
"""

import requests
from typing import List, Dict, Any
from datetime import datetime
import logging

from crawler.config.settings import settings
from crawler.utils.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class SlackNotifier:
    """
    Send formatted notifications to Slack via webhooks.

    Uses Slack Block Kit for rich message formatting with
    article cards, links, and metadata.
    """

    def __init__(self, webhook_url: str = None):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL (uses settings if not provided)
        """
        self.webhook_url = webhook_url or settings.slack_webhook_url
        self.report_generator = ReportGenerator()
        logger.info("Initialized SlackNotifier")

    def send_daily_report(
        self,
        articles: List[Dict[str, Any]],
        date: str = None,
        max_articles: int = 10
    ) -> bool:
        """
        Send daily digest to Slack.

        Args:
            articles: List of article dictionaries
            date: Report date (uses current date if not provided)
            max_articles: Maximum articles to show (default 10)

        Returns:
            True if successful, False otherwise
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')

        try:
            # Generate Slack blocks
            blocks = self.report_generator.generate_slack_blocks(
                articles,
                max_articles=max_articles
            )

            # Build payload
            payload = {
                "blocks": blocks,
                "username": "AI News Crawler",
                "icon_emoji": ":robot_face:"
            }

            # Send to Slack
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Successfully sent Slack notification with {len(articles)} articles")
                return True
            else:
                logger.error(f"Slack notification failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False

    def send_simple_message(self, message: str) -> bool:
        """
        Send simple text message to Slack.

        Args:
            message: Message text

        Returns:
            True if successful, False otherwise
        """
        try:
            payload = {
                "text": message,
                "username": "AI News Crawler",
                "icon_emoji": ":robot_face:"
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                logger.info("Successfully sent simple Slack message")
                return True
            else:
                logger.error(f"Slack message failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False

    def send_error_notification(self, error_message: str, details: str = None) -> bool:
        """
        Send error notification to Slack.

        Args:
            error_message: Main error message
            details: Optional error details

        Returns:
            True if successful, False otherwise
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ AI News Crawler Error",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:* {error_message}"
                }
            }
        ]

        if details:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{details}```"
                }
            })

        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"Timestamp: {datetime.utcnow().isoformat()}"
            }]
        })

        try:
            payload = {
                "blocks": blocks,
                "username": "AI News Crawler",
                "icon_emoji": ":warning:"
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False

    def test_connection(self) -> bool:
        """
        Test Slack webhook connection.

        Returns:
            True if connection successful, False otherwise
        """
        return self.send_simple_message("✅ AI News Crawler test notification")
