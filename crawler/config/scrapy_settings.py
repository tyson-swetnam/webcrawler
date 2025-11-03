"""
Scrapy settings for AI News Crawler.

Most settings are defined in the spider's custom_settings.
This file provides the minimal configuration needed for Scrapy project recognition.
"""

# Scrapy project name
BOT_NAME = 'ai-news-crawler'

# Spider modules
SPIDER_MODULES = ['crawler.spiders']
NEWSPIDER_MODULE = 'crawler.spiders'

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests
CONCURRENT_REQUESTS = 16

# Disable cookies (see http://scrapy.readthedocs.org/en/latest/topics/downloader-middleware.html#cookies-enabled)
COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en',
}
