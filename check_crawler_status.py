#!/usr/bin/env python3
"""
Quick diagnostic script to check crawler status and results
"""
import os
from pathlib import Path
from datetime import datetime

print("="*70)
print("CRAWLER STATUS CHECK")
print("="*70)

# 1. Check HTML output directory
print("\n1. HTML Output Directory:")
html_dir = Path("html_output")
if html_dir.exists():
    print(f"   ✓ Directory exists: {html_dir.absolute()}")
    
    # List files
    html_files = list(html_dir.glob("*.html"))
    if html_files:
        print(f"   ✓ Found {len(html_files)} HTML file(s):")
        for f in sorted(html_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            size = f.stat().st_size
            print(f"     - {f.name:30s} ({size:,} bytes, modified {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        print("   ⚠ No HTML files found")
else:
    print(f"   ✗ Directory does not exist")

# 2. Check database
print("\n2. Database Status:")
try:
    from crawler.db.session import get_db
    from crawler.db.models import Article
    from sqlalchemy import func
    
    with get_db() as session:
        total_articles = session.query(func.count(Article.article_id)).scalar()
        ai_articles = session.query(func.count(Article.article_id)).filter(Article.is_ai_related == True).scalar()
        
        print(f"   ✓ Database connected")
        print(f"   ✓ Total articles: {total_articles}")
        print(f"   ✓ AI-related articles: {ai_articles}")
        
        if total_articles > 0:
            # Get most recent article
            latest = session.query(Article).order_by(Article.first_scraped.desc()).first()
            if latest:
                print(f"   ✓ Latest article: {latest.first_scraped.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"     Title: {latest.title[:60]}...")
        else:
            print("   ⚠ No articles in database yet")
            
except Exception as e:
    print(f"   ✗ Database error: {e}")
    print("   ℹ This is normal if you haven't set up the database yet")

# 3. Check configuration
print("\n3. Configuration:")
try:
    from crawler.config.settings import settings
    print(f"   ✓ Source type: {settings.university_source_type}")
    sources = settings.get_university_sources()
    print(f"   ✓ Total sources configured: {len(sources)}")
    
    # Count by type
    from collections import Counter
    types = Counter([s.get('source_type', 'unknown') for s in sources])
    for stype, count in types.items():
        print(f"     - {stype}: {count}")
        
except Exception as e:
    print(f"   ✗ Configuration error: {e}")

# 4. Check logs
print("\n4. Recent Logs:")
log_dir = Path("/var/log/ai-news-crawler")
if log_dir.exists():
    log_files = list(log_dir.glob("*.log"))
    if log_files:
        latest_log = max(log_files, key=lambda x: x.stat().st_mtime)
        print(f"   ✓ Log file: {latest_log}")
        print(f"     Last modified: {datetime.fromtimestamp(latest_log.stat().st_mtime)}")
    else:
        print("   ⚠ No log files found")
else:
    print("   ℹ No log directory at /var/log/ai-news-crawler")
    print("   ℹ Check local directory for logs")

print("\n" + "="*70)
print("RECOMMENDATIONS:")
print("="*70)

# Check if database has articles
try:
    from crawler.db.session import get_db
    from crawler.db.models import Article
    from sqlalchemy import func
    
    with get_db() as session:
        total = session.query(func.count(Article.article_id)).scalar()
        
        if total == 0:
            print("\n⚠ No articles in database. This means:")
            print("  1. The crawler hasn't run yet, OR")
            print("  2. The crawler ran but found no new articles, OR")
            print("  3. The database isn't set up")
            print("\nNext steps:")
            print("  - Check if database is set up: scripts/test_database.sh")
            print("  - Run crawler manually: python -m crawler")
            print("  - Check crawler logs for errors")
        elif not html_dir.exists() or not list(html_dir.glob("*.html")):
            print("\n⚠ Articles exist but no HTML output. This means:")
            print("  HTML generator hasn't been called.")
            print("\nNext steps:")
            print("  - Generate HTML: python scripts/generate_html_report.py")
        else:
            print("\n✓ System appears to be working!")
            print("\nTo view results:")
            print("  1. python scripts/serve_html.py")
            print("  2. Open browser to http://localhost:8000")
            
except Exception as e:
    print(f"\n⚠ Could not check database: {e}")
    print("\nNext steps:")
    print("  - Set up database: scripts/setup_database.sh")
    print("  - Check .env configuration")

print()
