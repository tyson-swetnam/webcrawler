#!/usr/bin/env python3
"""
Test notification system (Slack and Email) without running full crawler.

Usage: python scripts/test_notifications.py
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.config.settings import settings
from crawler.notifiers.slack import SlackNotifier
from crawler.notifiers.email import EmailNotifier
from datetime import datetime


def test_slack():
    """Test Slack notification."""
    print("Testing Slack notification...")

    try:
        slack = SlackNotifier()

        # Send test message
        success = slack.send_simple_message(
            "✅ AI News Crawler - Slack integration test successful!"
        )

        if success:
            print("  ✓ Slack test PASSED")
            return True
        else:
            print("  ✗ Slack test FAILED")
            return False

    except Exception as e:
        print(f"  ✗ Slack test ERROR: {e}")
        return False


def test_email():
    """Test email notification."""
    print("Testing Email notification...")

    try:
        email = EmailNotifier()

        # Send test email
        success = email.send_simple_email(
            subject="AI News Crawler - Email Test",
            body=f"""This is a test email from AI News Crawler.

Configuration:
- SMTP Host: {settings.smtp_host}
- SMTP Port: {settings.smtp_port}
- Sender: {settings.email_from}
- Recipients: {', '.join(settings.email_to)}
- Timestamp: {datetime.utcnow().isoformat()}

If you received this email, your email configuration is working correctly!
"""
        )

        if success:
            print("  ✓ Email test PASSED")
            return True
        else:
            print("  ✗ Email test FAILED")
            return False

    except Exception as e:
        print(f"  ✗ Email test ERROR: {e}")
        return False


def test_sample_report():
    """Test with sample article data."""
    print("Testing with sample article data...")

    sample_articles = [
        {
            'title': 'Stanford Researchers Develop New AI Model for Medical Diagnosis',
            'university_name': 'Stanford University',
            'published_date': '2024-01-15',
            'url': 'https://news.stanford.edu/example-1',
            'summary': 'Researchers at Stanford have developed a new artificial intelligence model that can diagnose rare diseases with 95% accuracy, potentially revolutionizing medical diagnostics.',
            'author': 'Jane Doe',
            'word_count': 850
        },
        {
            'title': 'MIT Team Creates Breakthrough in Natural Language Processing',
            'university_name': 'MIT',
            'published_date': '2024-01-14',
            'url': 'https://news.mit.edu/example-2',
            'summary': 'MIT researchers have achieved a significant breakthrough in natural language processing, enabling AI systems to understand context and nuance with unprecedented accuracy.',
            'author': 'John Smith',
            'word_count': 1200
        }
    ]

    slack_success = False
    email_success = False

    # Test Slack
    if settings.enable_slack_notifications:
        try:
            slack = SlackNotifier()
            slack_success = slack.send_daily_report(
                sample_articles,
                date=datetime.utcnow().strftime('%Y-%m-%d')
            )
            if slack_success:
                print("  ✓ Slack sample report SENT")
            else:
                print("  ✗ Slack sample report FAILED")
        except Exception as e:
            print(f"  ✗ Slack sample report ERROR: {e}")

    # Test Email
    if settings.enable_email_notifications:
        try:
            email = EmailNotifier()
            email_success = email.send_daily_report(
                sample_articles,
                date=datetime.utcnow().strftime('%Y-%m-%d')
            )
            if email_success:
                print("  ✓ Email sample report SENT")
            else:
                print("  ✗ Email sample report FAILED")
        except Exception as e:
            print(f"  ✗ Email sample report ERROR: {e}")

    return slack_success or email_success


def main():
    """Run all notification tests."""
    print("=" * 60)
    print("AI News Crawler - Notification System Test")
    print("=" * 60)
    print()

    results = {
        'slack': False,
        'email': False,
        'sample': False
    }

    # Test Slack
    if settings.enable_slack_notifications:
        results['slack'] = test_slack()
        print()
    else:
        print("Slack notifications disabled in settings")
        print()

    # Test Email
    if settings.enable_email_notifications:
        results['email'] = test_email()
        print()
    else:
        print("Email notifications disabled in settings")
        print()

    # Test sample report
    results['sample'] = test_sample_report()
    print()

    # Summary
    print("=" * 60)
    print("Test Summary:")
    print("=" * 60)

    if settings.enable_slack_notifications:
        print(f"Slack:        {'✓ PASSED' if results['slack'] else '✗ FAILED'}")
    else:
        print("Slack:        (disabled)")

    if settings.enable_email_notifications:
        print(f"Email:        {'✓ PASSED' if results['email'] else '✗ FAILED'}")
    else:
        print("Email:        (disabled)")

    print(f"Sample Report: {'✓ PASSED' if results['sample'] else '✗ FAILED'}")
    print()

    # Exit code
    all_passed = all(results.values())
    if all_passed:
        print("✅ All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed. Check configuration in .env file")
        return 1


if __name__ == "__main__":
    sys.exit(main())
