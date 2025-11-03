# AI University News Aggregator

**Live Site:** https://tyson-swetnam.github.io/webcrawler

Automated daily news aggregator tracking AI research and developments from 52 US universities and research facilities.

**Last Updated:** Auto-updates daily at 07:00 PST

---

## About

This site automatically crawls university news sites every day and aggregates AI-related research news in a Drudge Report-style format.

### Sources

- **27 Peer Institutions** - Top R1 universities (Stanford, MIT, CMU, Berkeley, etc.)
- **187 R1 Research Universities** - Leading research institutions nationwide  
- **27 Major Research Facilities** - National Labs and Supercomputing Centers (ORNL, LLNL, Argonne, etc.)

### Features

- Daily automated crawls at 07:00 PST
- AI-powered content analysis (Claude + GPT)
- Clean, mobile-responsive Drudge Report-style design
- Archive of historical reports
- Smart deduplication (skips previously seen content)
- 30-day rolling content window (recent news only)

---

## Technology

- **Crawler:** Python + Scrapy with ethical rate limiting
- **AI Analysis:** Claude (Anthropic) + GPT (OpenAI)
- **Deployment:** GitHub Actions + GitHub Pages
- **Update Schedule:** Daily at 07:00 PST via automated workflow

---

## Browse

- **[Today's News](index.html)** - Latest AI research news
- **[Archive](archive/)** - Historical reports

---

*Automated with GitHub Actions | Generated with [Claude Code](https://claude.com/claude-code)*
