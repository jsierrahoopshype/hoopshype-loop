# CLAUDE.md — Project Instructions for Claude Code

## Project: HoopsHype Loop — NBA Broadcast Overlay

### What This Is
A YouTube-ready 1920×1080 broadcast overlay that streams NBA coverage 24/7. It shows live box scores, player stats, rankings from Google Sheets, a scrolling headlines ticker, and a Bluesky social feed.

### Architecture
- **static/overlay.html** — Single-file broadcast overlay (HTML/CSS/JS). Currently runs on mock data. Needs to be wired to fetch from the Flask backend.
- **server.py** — Flask backend on port 5555. Serves `/api/games` (nba_api live scores) and `/api/headlines` (HoopsHype scraped headlines). Has background refresh threads with caching.
- **config.json** — All configurable settings (refresh rates, Bluesky accounts, Google Sheet IDs, theme).

### Tech Stack
- Python 3.8+ with Flask, nba_api, requests, beautifulsoup4
- Frontend is vanilla HTML/CSS/JS (no build step)
- Fonts: Google Fonts (Barlow, Barlow Condensed)

### Current State (Phase 0 Complete)
The overlay works standalone with hardcoded mock data. It has:
- Auto-rotating game views: team overview → away boxscore → home boxscore
- ESPN-style player stat tables (Starters/Bench/DNP/Totals)
- "Today's Games" mini-scoreboard strip
- Scrolling HoopsHype-style ticker with color-coded badges
- Bluesky NBA Buzz sidebar
- Rankings rotation for no-game periods
- Close-game prioritization

### Implementation Phases (TODO)
1. **Phase 1**: Wire overlay.html to poll `localhost:5555/api/games` instead of mock data
2. **Phase 2**: Add Google Sheets CSV fetching (direct from browser, public sheets)
3. **Phase 3**: Wire overlay.html to poll `localhost:5555/api/headlines` for ticker
4. **Phase 4**: Add Bluesky public API fetching for sidebar
5. **Phase 5**: Error states, reconnection UI, status panel

### Key Design Constraints
- Output must look broadcast-quality at 1920×1080 in OBS
- YouTube safe margins: 32px all sides
- Font: Barlow Condensed (display) + Barlow (body)
- Dark theme with cyan (#00c8ff) and orange (#ff6b35) accents
- Ticker: thin bar with orange "RUMORS" tag, color-coded badges
- All animations 60fps-friendly, CSS-only where possible

### Legal Rules
- Scores/stats: factual data from nba_api (legal)
- Headlines: title text only, never full articles
- Rankings: owner's Google Sheets (own content)
- Bluesky: public posts with full attribution
- No team logos (use text abbreviations)
- No copyrighted images

### Running Locally
```bash
pip install -r requirements.txt
python server.py
# Open http://localhost:5555
```

### Testing
- Open overlay.html directly in Chrome for mock-data testing
- Check /api/health for server status
- Check /api/games and /api/headlines for data
- Server logs are in logs/server.log
