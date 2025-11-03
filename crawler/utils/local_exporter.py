"""
Local file export utilities for article results.

This module saves crawler results to local files in multiple formats
when notifications are disabled or for archival purposes.
"""

import json
import csv
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import logging

from crawler.config.settings import settings
from crawler.utils.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class LocalExporter:
    """
    Export article results to local files.

    Supports multiple formats: JSON, CSV, HTML, and plain text.
    Creates organized directory structure for outputs.
    """

    def __init__(self, output_dir: str = None):
        """
        Initialize local exporter.

        Args:
            output_dir: Base output directory (uses settings if not provided)
        """
        self.output_dir = Path(output_dir or settings.local_output_dir)
        self.report_generator = ReportGenerator()
        self._ensure_directories()

    def _ensure_directories(self):
        """Create output directory structure if it doesn't exist."""
        directories = [
            self.output_dir,
            self.output_dir / "results",
            self.output_dir / "reports",
            self.output_dir / "exports",
            self.output_dir / "logs"
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")

    def export_all(
        self,
        articles: List[Dict[str, Any]],
        analyses: List[Dict[str, Any]] = None,
        date: str = None
    ) -> Dict[str, str]:
        """
        Export results in all enabled formats.

        Args:
            articles: List of article dictionaries
            analyses: Optional list of AI analysis results
            date: Report date (uses current date if not provided)

        Returns:
            Dictionary of format -> file path mappings
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')

        exported_files = {}

        # Export JSON
        if settings.export_json:
            json_path = self.export_json(articles, analyses, date)
            if json_path:
                exported_files['json'] = str(json_path)

        # Export CSV
        if settings.export_csv:
            csv_path = self.export_csv(articles, date)
            if csv_path:
                exported_files['csv'] = str(csv_path)

        # Export HTML
        if settings.export_html:
            html_path = self.export_html(articles, date)
            if html_path:
                exported_files['html'] = str(html_path)

        # Export text summary
        if settings.export_text_summary:
            text_path = self.export_text_summary(articles, date)
            if text_path:
                exported_files['text'] = str(text_path)

        logger.info(f"Exported {len(exported_files)} file formats")
        return exported_files

    def export_json(
        self,
        articles: List[Dict[str, Any]],
        analyses: List[Dict[str, Any]] = None,
        date: str = None
    ) -> Path:
        """
        Export results as JSON file.

        Args:
            articles: List of article dictionaries
            analyses: Optional list of AI analysis results
            date: Report date

        Returns:
            Path to created JSON file
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')

        try:
            output_path = self.output_dir / "results" / f"results_{date}.json"

            data = {
                "date": date,
                "timestamp": datetime.utcnow().isoformat(),
                "article_count": len(articles),
                "articles": articles,
                "ai_analyses": analyses or [],
                "metadata": {
                    "crawler_version": "1.0",
                    "enable_ai_analysis": settings.enable_ai_analysis,
                    "lookback_days": settings.lookback_days
                }
            }

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Exported JSON: {output_path} ({len(articles)} articles)")
            return output_path

        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
            return None

    def export_csv(
        self,
        articles: List[Dict[str, Any]],
        date: str = None
    ) -> Path:
        """
        Export articles as CSV file.

        Args:
            articles: List of article dictionaries
            date: Report date

        Returns:
            Path to created CSV file
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')

        if not articles:
            logger.info("No articles to export to CSV")
            return None

        try:
            output_path = self.output_dir / "exports" / f"articles_{date}.csv"

            # Define CSV columns
            fieldnames = [
                'title',
                'university_name',
                'published_date',
                'url',
                'summary',
                'author',
                'word_count',
                'is_ai_related',
                'ai_confidence_score'
            ]

            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()

                for article in articles:
                    # Ensure all fields exist with defaults
                    row = {field: article.get(field, '') for field in fieldnames}
                    writer.writerow(row)

            logger.info(f"Exported CSV: {output_path} ({len(articles)} articles)")
            return output_path

        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            return None

    def export_html(
        self,
        articles: List[Dict[str, Any]],
        date: str = None
    ) -> Path:
        """
        Export HTML report.

        Args:
            articles: List of article dictionaries
            date: Report date

        Returns:
            Path to created HTML file
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')

        try:
            output_path = self.output_dir / "reports" / f"report_{date}.html"

            html_content = self.report_generator.generate_html_report(
                articles,
                title=f"AI News Digest - {date}"
            )

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"Exported HTML: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to export HTML: {e}")
            return None

    def export_text_summary(
        self,
        articles: List[Dict[str, Any]],
        date: str = None
    ) -> Path:
        """
        Export plain text summary.

        Args:
            articles: List of article dictionaries
            date: Report date

        Returns:
            Path to created text file
        """
        if date is None:
            date = datetime.utcnow().strftime('%Y-%m-%d')

        try:
            output_path = self.output_dir / f"summary_{date}.txt"

            text_content = self.report_generator.generate_text_report(articles)

            # Add statistics header
            stats = self._generate_statistics(articles)
            full_content = f"{stats}\n\n{text_content}"

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_content)

            logger.info(f"Exported text summary: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to export text summary: {e}")
            return None

    def _generate_statistics(self, articles: List[Dict[str, Any]]) -> str:
        """
        Generate statistics summary.

        Args:
            articles: List of article dictionaries

        Returns:
            Statistics text
        """
        total = len(articles)
        ai_related = sum(1 for art in articles if art.get('is_ai_related', False))

        # Count by university
        universities = {}
        for article in articles:
            uni = article.get('university_name', 'Unknown')
            universities[uni] = universities.get(uni, 0) + 1

        stats_lines = [
            "=" * 60,
            "AI NEWS CRAWLER STATISTICS",
            "=" * 60,
            f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total Articles: {total}",
            f"AI-Related Articles: {ai_related}",
            f"",
            "Articles by University:",
        ]

        for uni, count in sorted(universities.items(), key=lambda x: x[1], reverse=True):
            stats_lines.append(f"  - {uni}: {count}")

        return '\n'.join(stats_lines)

    def get_latest_export_path(self, format_type: str = 'json') -> Path:
        """
        Get path to most recent export file.

        Args:
            format_type: File format (json, csv, html, text)

        Returns:
            Path to latest file or None if not found
        """
        if format_type == 'json':
            search_dir = self.output_dir / "results"
            pattern = "results_*.json"
        elif format_type == 'csv':
            search_dir = self.output_dir / "exports"
            pattern = "articles_*.csv"
        elif format_type == 'html':
            search_dir = self.output_dir / "reports"
            pattern = "report_*.html"
        elif format_type == 'text':
            search_dir = self.output_dir
            pattern = "summary_*.txt"
        else:
            logger.error(f"Unknown format type: {format_type}")
            return None

        if not search_dir.exists():
            return None

        files = sorted(search_dir.glob(pattern), reverse=True)
        return files[0] if files else None

    def cleanup_old_exports(self, keep_days: int = 30):
        """
        Remove export files older than specified days.

        Args:
            keep_days: Number of days to keep files
        """
        cutoff_date = datetime.utcnow().timestamp() - (keep_days * 86400)
        removed_count = 0

        for directory in [
            self.output_dir / "results",
            self.output_dir / "reports",
            self.output_dir / "exports",
            self.output_dir
        ]:
            if not directory.exists():
                continue

            for file_path in directory.glob("*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_date:
                    try:
                        file_path.unlink()
                        removed_count += 1
                        logger.debug(f"Removed old export: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to remove {file_path}: {e}")

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old export files (>{keep_days} days)")
