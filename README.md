# HoopsHype Loop — NBA Broadcast Overlay

A 24/7 YouTube-ready broadcast overlay for NBA coverage. Live box scores, player stats, rankings rotation, headlines ticker, and Bluesky NBA Buzz feed.

## Quick Start

```bash
pip install -r requirements.txt
python server.py
# Open http://localhost:5555 in Chrome
# Or open static/overlay.html directly for mock-data mode
```

## OBS Capture

1. Add **Browser Source** → URL: `http://localhost:5555` → 1920×1080
2. Set YouTube stream key → Start Streaming

## Structure

```
├── server.py          # Flask backend (nba_api + scraper)
├── config.json        # All settings
├── requirements.txt   # Python deps
├── static/overlay.html # Broadcast overlay
├── data/              # Cache (auto)
└── logs/              # Logs (auto)
```

## Legal

Only factual scores/stats (nba_api), headline titles (not full articles), your own Google Sheets content, and public Bluesky posts with attribution. No team logos, copyrighted images, or paywalled content.
