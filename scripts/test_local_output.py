#!/usr/bin/env python3
"""
Test Local Output System

This script tests the local file export functionality without
requiring a full crawler run or database setup.

Usage:
    python scripts/test_local_output.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.utils.local_exporter import LocalExporter


def create_test_articles():
    """Create sample article data for testing."""
    return [
        {
            'title': 'Stanford Researchers Develop Breakthrough AI Model',
            'university_name': 'Stanford University',
            'published_date': '2025-10-30',
            'url': 'https://news.stanford.edu/ai-breakthrough',
            'summary': 'Stanford researchers have developed a new AI model that achieves state-of-the-art performance on natural language understanding tasks.',
            'author': 'John Doe',
            'word_count': 1250,
            'is_ai_related': True,
            'ai_confidence_score': 0.95
        },
        {
            'title': 'MIT Announces New AI Ethics Initiative',
            'university_name': 'MIT',
            'published_date': '2025-10-30',
            'url': 'https://news.mit.edu/ai-ethics',
            'summary': 'MIT has launched a new initiative focused on developing ethical guidelines for AI development and deployment.',
            'author': 'Jane Smith',
            'word_count': 890,
            'is_ai_related': True,
            'ai_confidence_score': 0.88
        },
        {
            'title': 'Berkeley Team Creates Efficient AI Training Method',
            'university_name': 'UC Berkeley',
            'published_date': '2025-10-29',
            'url': 'https://news.berkeley.edu/ai-training',
            'summary': 'UC Berkeley researchers have discovered a method to train large AI models with significantly reduced computational resources.',
            'author': 'Alice Johnson',
            'word_count': 1450,
            'is_ai_related': True,
            'ai_confidence_score': 0.92
        }
    ]


def create_test_analyses():
    """Create sample AI analysis data."""
    return [
        {
            'claude': {
                'summary': 'Significant advancement in natural language processing',
                'key_points': ['State-of-the-art performance', 'Novel architecture']
            },
            'openai': {
                'summary': 'Important AI research breakthrough',
                'category': 'Machine Learning'
            },
            'gemini': {
                'summary': 'Major development in AI language models'
            },
            'consensus': {
                'summary': 'Stanford researchers achieve breakthrough in AI language understanding',
                'is_ai_related': True,
                'confidence': 0.95,
                'relevance_score': 0.93
            },
            'processing_time_ms': 1234
        },
        {
            'claude': {
                'summary': 'Important ethical framework for AI development',
                'key_points': ['Responsible AI', 'Industry standards']
            },
            'openai': {
                'summary': 'New guidelines for ethical AI',
                'category': 'AI Ethics'
            },
            'gemini': {
                'summary': 'Ethics-focused AI initiative'
            },
            'consensus': {
                'summary': 'MIT launches comprehensive AI ethics initiative',
                'is_ai_related': True,
                'confidence': 0.88,
                'relevance_score': 0.85
            },
            'processing_time_ms': 987
        },
        {
            'claude': {
                'summary': 'Innovative approach to efficient AI training',
                'key_points': ['Reduced compute requirements', 'Sustainable AI']
            },
            'openai': {
                'summary': 'Breakthrough in efficient model training',
                'category': 'AI Optimization'
            },
            'gemini': {
                'summary': 'New method for resource-efficient AI'
            },
            'consensus': {
                'summary': 'Berkeley develops efficient AI training methodology',
                'is_ai_related': True,
                'confidence': 0.92,
                'relevance_score': 0.90
            },
            'processing_time_ms': 1456
        }
    ]


def test_export_all():
    """Test exporting all formats."""
    print("=" * 60)
    print("Testing Local Export System")
    print("=" * 60)

    # Create test data
    print("\n1. Creating test data...")
    articles = create_test_articles()
    analyses = create_test_analyses()
    print(f"   ✓ Created {len(articles)} test articles")
    print(f"   ✓ Created {len(analyses)} test analyses")

    # Initialize exporter
    print("\n2. Initializing LocalExporter...")
    exporter = LocalExporter()
    print(f"   ✓ Output directory: {exporter.output_dir}")

    # Export all formats
    print("\n3. Exporting all formats...")
    test_date = datetime.utcnow().strftime('%Y-%m-%d')
    exported_files = exporter.export_all(articles, analyses, test_date)

    if not exported_files:
        print("   ✗ No files exported!")
        return False

    print(f"   ✓ Exported {len(exported_files)} formats")

    # Verify each export
    print("\n4. Verifying exports...")
    all_valid = True

    for format_type, file_path in exported_files.items():
        file_path = Path(file_path)
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"   ✓ {format_type.upper()}: {file_path} ({size} bytes)")
        else:
            print(f"   ✗ {format_type.upper()}: File not found at {file_path}")
            all_valid = False

    # Test getting latest files
    print("\n5. Testing get_latest_export_path()...")
    for format_type in ['json', 'csv', 'html', 'text']:
        latest = exporter.get_latest_export_path(format_type)
        if latest and latest.exists():
            print(f"   ✓ Latest {format_type}: {latest.name}")
        else:
            print(f"   ✗ No {format_type} file found")
            all_valid = False

    return all_valid


def test_individual_exports():
    """Test individual export functions."""
    print("\n" + "=" * 60)
    print("Testing Individual Export Functions")
    print("=" * 60)

    articles = create_test_articles()
    analyses = create_test_analyses()
    exporter = LocalExporter()
    test_date = "test_" + datetime.utcnow().strftime('%Y-%m-%d-%H%M%S')

    results = {}

    # Test JSON export
    print("\n1. Testing JSON export...")
    json_path = exporter.export_json(articles, analyses, test_date)
    results['json'] = json_path and json_path.exists()
    print(f"   {'✓' if results['json'] else '✗'} JSON: {json_path}")

    # Test CSV export
    print("\n2. Testing CSV export...")
    csv_path = exporter.export_csv(articles, test_date)
    results['csv'] = csv_path and csv_path.exists()
    print(f"   {'✓' if results['csv'] else '✗'} CSV: {csv_path}")

    # Test HTML export
    print("\n3. Testing HTML export...")
    html_path = exporter.export_html(articles, test_date)
    results['html'] = html_path and html_path.exists()
    print(f"   {'✓' if results['html'] else '✗'} HTML: {html_path}")

    # Test text export
    print("\n4. Testing text summary export...")
    text_path = exporter.export_text_summary(articles, test_date)
    results['text'] = text_path and text_path.exists()
    print(f"   {'✓' if results['text'] else '✗'} Text: {text_path}")

    return all(results.values())


def test_empty_articles():
    """Test handling of empty article list."""
    print("\n" + "=" * 60)
    print("Testing Empty Articles Handling")
    print("=" * 60)

    exporter = LocalExporter()
    test_date = "empty_" + datetime.utcnow().strftime('%Y-%m-%d-%H%M%S')

    print("\n1. Testing with empty article list...")
    exported_files = exporter.export_all([], [], test_date)

    # Should still create files (empty reports)
    if exported_files:
        print(f"   ✓ Created {len(exported_files)} empty files")
        for format_type, file_path in exported_files.items():
            print(f"      - {format_type}: {Path(file_path).name}")
        return True
    else:
        print("   ✗ No files created for empty articles")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LOCAL OUTPUT SYSTEM TEST SUITE")
    print("=" * 60)

    results = {}

    # Run tests
    results['export_all'] = test_export_all()
    results['individual_exports'] = test_individual_exports()
    results['empty_articles'] = test_empty_articles()

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(results.values())

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n✓ All tests passed!")
        print("\nYou can now:")
        print("  1. Run the crawler: python -m crawler")
        print("  2. View results: ./scripts/view_latest_results.sh")
        print("  3. Generate reports: python scripts/generate_html_report.py")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
