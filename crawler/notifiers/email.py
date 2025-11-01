"""
Email notification system using SMTP.

This module sends HTML-formatted article digests via email
with responsive design and proper MIME formatting.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from datetime import datetime
import logging

from crawler.config.settings import settings
from crawler.utils.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Send HTML email reports via SMTP.

    Supports both plain text and HTML multipart messages
    for maximum compatibility.
    """

    def __init__(
        self,
        smtp_host: str = None,
        smtp_port: int = None,
        sender: str = None,
        password: str = None,
        recipients: List[str] = None
    ):
        """
        Initialize email notifier.

        Args:
            smtp_host: SMTP server hostname (uses settings if not provided)
            smtp_port: SMTP server port
            sender: Sender email address
            password: SMTP password
            recipients: List of recipient email addresses
        """
        self.smtp_host = smtp_host or settings.smtp_host
        self.smtp_port = smtp_port or settings.smtp_port
        self.sender = sender or settings.email_from
        self.password = password or settings.smtp_password
        self.recipients = recipients or settings.email_to
        self.use_ssl = settings.smtp_use_ssl

        self.report_generator = ReportGenerator()

        logger.info(f"Initialized EmailNotifier (host={self.smtp_host}, recipients={len(self.recipients)})")

    def send_daily_report(
        self,
        articles: List[Dict[str, Any]],
        date: str = None
    ) -> bool:
        """
        Send formatted HTML email report.

        Args:
            articles: List of article dictionaries
            date: Report date (uses current date if not provided)

        Returns:
            True if successful, False otherwise
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')

        try:
            # Generate HTML content
            html_content = self.report_generator.generate_html_report(
                articles,
                title=f"AI News Digest - {date}"
            )

            # Generate plain text fallback
            text_content = self.report_generator.generate_text_report(articles)

            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = f"AI News Digest - {date} ({len(articles)} articles)"
            message["From"] = self.sender
            message["To"] = ", ".join(self.recipients)
            message["Date"] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')

            # Attach parts
            part1 = MIMEText(text_content, "plain")
            part2 = MIMEText(html_content, "html")
            message.attach(part1)
            message.attach(part2)

            # Send email
            self._send_email(message)

            logger.info(f"Successfully sent email report with {len(articles)} articles to {len(self.recipients)} recipients")
            return True

        except Exception as e:
            logger.error(f"Failed to send email report: {e}")
            return False

    def send_simple_email(
        self,
        subject: str,
        body: str,
        html: bool = False
    ) -> bool:
        """
        Send simple email message.

        Args:
            subject: Email subject
            body: Email body
            html: Whether body is HTML (default: plain text)

        Returns:
            True if successful, False otherwise
        """
        try:
            message = MIMEMultipart()
            message["Subject"] = subject
            message["From"] = self.sender
            message["To"] = ", ".join(self.recipients)

            if html:
                message.attach(MIMEText(body, "html"))
            else:
                message.attach(MIMEText(body, "plain"))

            self._send_email(message)

            logger.info(f"Successfully sent simple email: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send simple email: {e}")
            return False

    def send_error_notification(
        self,
        error_message: str,
        details: str = None
    ) -> bool:
        """
        Send error notification email.

        Args:
            error_message: Main error message
            details: Optional error details

        Returns:
            True if successful, False otherwise
        """
        subject = f"⚠️ AI News Crawler Error - {datetime.utcnow().strftime('%Y-%m-%d')}"

        body = f"""
AI News Crawler Error Report

Error: {error_message}

Timestamp: {datetime.utcnow().isoformat()}

"""

        if details:
            body += f"\nDetails:\n{details}\n"

        return self.send_simple_email(subject, body)

    def _send_email(self, message: MIMEMultipart):
        """
        Send email message via SMTP.

        Args:
            message: MIME message to send

        Raises:
            Exception: If sending fails
        """
        context = ssl.create_default_context()

        if self.use_ssl:
            # Use SSL from the start (port 465)
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                server.login(self.sender, self.password)
                server.sendmail(
                    self.sender,
                    self.recipients,
                    message.as_string()
                )
        else:
            # Use TLS (port 587)
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.sender, self.password)
                server.sendmail(
                    self.sender,
                    self.recipients,
                    message.as_string()
                )

    def test_connection(self) -> bool:
        """
        Test email configuration by sending a test message.

        Returns:
            True if test successful, False otherwise
        """
        test_subject = "AI News Crawler Test Email"
        test_body = f"""
This is a test email from AI News Crawler.

Configuration:
- SMTP Host: {self.smtp_host}
- SMTP Port: {self.smtp_port}
- Sender: {self.sender}
- Recipients: {', '.join(self.recipients)}
- Timestamp: {datetime.utcnow().isoformat()}

If you received this email, your email configuration is working correctly.
"""

        try:
            result = self.send_simple_email(test_subject, test_body)
            if result:
                logger.info("✅ Email test successful")
            return result
        except Exception as e:
            logger.error(f"❌ Email test failed: {e}")
            return False
