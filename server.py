"""
HoopsHype TV — Backend Server
Serves live NBA data and scraped headlines to the broadcast overlay.
Endpoints:
  GET /api/games       — live/today's box scores from nba_api
  GET /api/headlines    — scraped HoopsHype rumors headlines
  GET /api/health      — server health check
"""

import json
import time
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread, Lock

from flask import Flask, jsonify
from flask_cors import CORS

# ── Config ──────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    CFG = json.load(f)

# ── Logging ─────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "server.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("hoopshype-loop")

# ── App ─────────────────────────────────────────────────
app = Flask(__name__, static_folder="static")
CORS(app)

# ── Cache ───────────────────────────────────────────────
cache = {
    "games": {"data": [], "updated": 0},
    "headlines": {"data": [], "updated": 0},
}
cache_lock = Lock()


# ═══════════════════════════════════════════════════════
# NBA API — Live Scores
# ═══════════════════════════════════════════════════════

def fetch_games():
    """Fetch today's games from nba_api and return structured data."""
    try:
        from nba_api.live.nba.endpoints import scoreboard
        sb = scoreboard.ScoreBoard()
        data = sb.get_dict()
        games = data.get("scoreboard", {}).get("games", [])

        result = []
        for g in games:
            home = g.get("homeTeam", {})
            away = g.get("awayTeam", {})

            def parse_team(t, periods_data):
                # Leaders
                leaders = {}
                for cat_key, cat_name in [("points", "pts"), ("rebounds", "reb"), ("assists", "ast")]:
                    # Leaders come from different structure in live API
                    leaders[cat_name] = {"p": "—", "v": 0}

                # Try to get leaders from gameLeaders
                game_leaders = g.get("gameLeaders", {})
                if game_leaders:
                    for api_key, our_key in [("homeLeaders", "home"), ("awayLeaders", "away")]:
                        if api_key in game_leaders:
                            ld = game_leaders[api_key]
                            side_leaders = {}
                            if "points" in ld:
                                side_leaders["pts"] = {"p": ld.get("name", "—"), "v": ld.get("points", 0)}
                            if "rebounds" in ld:
                                side_leaders["reb"] = {"p": ld.get("name", "—"), "v": ld.get("rebounds", 0)}
                            if "assists" in ld:
                                side_leaders["ast"] = {"p": ld.get("name", "—"), "v": ld.get("assists", 0)}
                            if our_key == ("home" if t == home else "away"):
                                leaders.update(side_leaders)

                # Periods/quarters
                periods = t.get("periods", [])
                quarters = [p.get("score", 0) for p in periods] if periods else []
                # Pad to 4 quarters
                while len(quarters) < 4:
                    quarters.append(0)

                # Team stats
                stats = t.get("statistics", {})

                return {
                    "abbr": t.get("teamTricode", "???"),
                    "city": t.get("teamCity", ""),
                    "name": t.get("teamName", ""),
                    "record": f"{t.get('wins', 0)}-{t.get('losses', 0)}",
                    "score": t.get("score", 0),
                    "quarters": quarters[:4],
                    "leaders": leaders,
                    "splits": {
                        "fg": _pct(stats.get("fieldGoalsMade", 0), stats.get("fieldGoalsAttempted", 0)),
                        "tp": _pct(stats.get("threePointersMade", 0), stats.get("threePointersAttempted", 0)),
                        "ft": _pct(stats.get("freeThrowsMade", 0), stats.get("freeThrowsAttempted", 0)),
                    },
                    "players": _parse_players(t.get("players", [])),
                }

            # Game status
            status_num = g.get("gameStatus", 1)
            status_text = g.get("gameStatusText", "").strip()
            period = g.get("period", 0)

            if status_num == 1:
                status = "upcoming"
                period_str = status_text  # e.g. "7:00 pm ET"
                clock = ""
            elif status_num == 2:
                status = "live"
                clock_str = g.get("gameClock", "").replace("PT", "").replace("M", ":").replace("S", "").strip()
                # Format clock nicely
                if clock_str and clock_str != "":
                    try:
                        parts = clock_str.split(":")
                        mins = int(float(parts[0])) if parts[0] else 0
                        secs = int(float(parts[1])) if len(parts) > 1 and parts[1] else 0
                        clock = f"{mins}:{secs:02d}"
                    except:
                        clock = clock_str
                else:
                    clock = "0:00"
                ordinal = lambda n: f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"
                period_str = f"{ordinal(period)} Qtr" if period <= 4 else f"OT{period-4}" if period > 4 else ""
            else:
                status = "final"
                period_str = "Final" if period <= 4 else f"Final/OT{period-4}"
                clock = ""

            result.append({
                "id": g.get("gameId", ""),
                "status": status,
                "period": period_str,
                "clock": clock,
                "arena": g.get("arenaName", ""),
                "away": parse_team(away, g),
                "home": parse_team(home, g),
            })

        log.info(f"Fetched {len(result)} games from nba_api")
        return result

    except Exception as e:
        log.error(f"Error fetching games: {e}\n{traceback.format_exc()}")
        return None


def _pct(made, attempted):
    """Calculate shooting percentage."""
    if attempted == 0:
        return 0.0
    return round((made / attempted) * 100, 1)


def _parse_players(players_data):
    """Parse player box score data into starters/bench/dnp/totals."""
    starters = []
    bench = []
    dnp = []

    totals = {
        "min": 0, "pts": 0, "fg": [0, 0], "tp": [0, 0], "ft": [0, 0],
        "or": 0, "dr": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0,
        "to": 0, "pf": 0, "pm": "",
    }

    for p in players_data:
        stats = p.get("statistics", {})
        status = p.get("status", "ACTIVE")
        played = p.get("played", "1")

        if status != "ACTIVE" or played == "0":
            reason = p.get("notPlayingReason", "Coach's Decision")
            dnp.append({
                "n": _short_name(p.get("name", p.get("firstName", "") + " " + p.get("familyName", ""))),
                "r": f"DNP — {reason}",
            })
            continue

        mins = stats.get("minutesCalculated", stats.get("minutes", "0"))
        # Parse minutes - could be "PT25M" or "25" or "25:30"
        min_val = _parse_minutes(mins)

        fgm = stats.get("fieldGoalsMade", 0)
        fga = stats.get("fieldGoalsAttempted", 0)
        tpm = stats.get("threePointersMade", 0)
        tpa = stats.get("threePointersAttempted", 0)
        ftm = stats.get("freeThrowsMade", 0)
        fta = stats.get("freeThrowsAttempted", 0)

        player_obj = {
            "n": _short_name(p.get("name", p.get("firstName", "") + " " + p.get("familyName", ""))),
            "pos": p.get("position", ""),
            "min": min_val,
            "pts": stats.get("points", 0),
            "fg": f"{fgm}-{fga}",
            "tp": f"{tpm}-{tpa}",
            "ft": f"{ftm}-{fta}",
            "or": stats.get("reboundsOffensive", 0),
            "dr": stats.get("reboundsDefensive", 0),
            "reb": stats.get("reboundsTotal", 0),
            "ast": stats.get("assists", 0),
            "stl": stats.get("steals", 0),
            "blk": stats.get("blocks", 0),
            "to": stats.get("turnovers", 0),
            "pf": stats.get("foulsPersonal", 0),
            "pm": _format_pm(stats.get("plusMinusPoints", 0)),
        }

        # Update totals
        totals["min"] += min_val
        totals["pts"] += player_obj["pts"]
        totals["fg"][0] += fgm; totals["fg"][1] += fga
        totals["tp"][0] += tpm; totals["tp"][1] += tpa
        totals["ft"][0] += ftm; totals["ft"][1] += fta
        totals["or"] += player_obj["or"]
        totals["dr"] += player_obj["dr"]
        totals["reb"] += player_obj["reb"]
        totals["ast"] += player_obj["ast"]
        totals["stl"] += player_obj["stl"]
        totals["blk"] += player_obj["blk"]
        totals["to"] += player_obj["to"]
        totals["pf"] += player_obj["pf"]

        starter = p.get("starter", "0")
        if starter == "1":
            starters.append(player_obj)
        else:
            bench.append(player_obj)

    # Format totals
    totals_formatted = {
        "min": totals["min"],
        "pts": totals["pts"],
        "fg": f"{totals['fg'][0]}-{totals['fg'][1]}",
        "tp": f"{totals['tp'][0]}-{totals['tp'][1]}",
        "ft": f"{totals['ft'][0]}-{totals['ft'][1]}",
        "or": totals["or"], "dr": totals["dr"], "reb": totals["reb"],
        "ast": totals["ast"], "stl": totals["stl"], "blk": totals["blk"],
        "to": totals["to"], "pf": totals["pf"], "pm": "",
    }

    pcts = {
        "fg": f"{_pct(totals['fg'][0], totals['fg'][1])}%",
        "tp": f"{_pct(totals['tp'][0], totals['tp'][1])}%",
        "ft": f"{_pct(totals['ft'][0], totals['ft'][1])}%",
    }

    return {
        "starters": starters,
        "bench": bench,
        "dnp": dnp,
        "totals": totals_formatted,
        "pcts": pcts,
    }


def _short_name(full):
    """Convert 'Jayson Tatum' → 'J. Tatum'."""
    parts = full.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    return full


def _parse_minutes(val):
    """Parse minutes from various formats."""
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).replace("PT", "").replace("M", "").replace("S", "").strip()
    try:
        if ":" in s:
            return int(s.split(":")[0])
        return int(float(s))
    except:
        return 0


def _format_pm(val):
    """Format plus/minus with sign."""
    if val > 0:
        return f"+{val}"
    elif val < 0:
        return str(val)
    return "0"


# ═══════════════════════════════════════════════════════
# HOOPSHYPE HEADLINES SCRAPER
# ═══════════════════════════════════════════════════════

def fetch_headlines():
    """Scrape headlines from HoopsHype rumors page."""
    try:
        import requests
        from bs4 import BeautifulSoup

        url = CFG["hoopshype_ticker"]["url"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        headlines = []

        # HoopsHype rumors are typically in article/post elements
        # Adjust selectors based on actual page structure
        articles = soup.select("div.post-data h2 a, div.post-loop h2 a, article h2 a, .rumor-title a, h2.entry-title a")

        if not articles:
            # Fallback: try broader selectors
            articles = soup.select("h2 a, h3 a")

        for a in articles[:CFG["hoopshype_ticker"]["max_headlines"]]:
            text = a.get_text(strip=True)
            if text and len(text) > 15:  # Skip very short items
                headlines.append({
                    "t": text,
                    "b": "new" if len(headlines) < 3 else "rumor",
                    "url": a.get("href", ""),
                })

        log.info(f"Scraped {len(headlines)} headlines from HoopsHype")
        return headlines

    except Exception as e:
        log.error(f"Error scraping headlines: {e}\n{traceback.format_exc()}")
        return None


# ═══════════════════════════════════════════════════════
# BACKGROUND REFRESH THREADS
# ═══════════════════════════════════════════════════════

def refresh_loop(key, fetch_fn, interval_sec):
    """Generic background refresh loop."""
    while True:
        try:
            data = fetch_fn()
            if data is not None:
                with cache_lock:
                    cache[key]["data"] = data
                    cache[key]["updated"] = time.time()
        except Exception as e:
            log.error(f"Refresh error [{key}]: {e}")
        time.sleep(interval_sec)


# ═══════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════

@app.route("/api/games")
def api_games():
    with cache_lock:
        return jsonify({
            "games": cache["games"]["data"],
            "updated": cache["games"]["updated"],
            "count": len(cache["games"]["data"]),
        })


@app.route("/api/headlines")
def api_headlines():
    with cache_lock:
        return jsonify({
            "headlines": cache["headlines"]["data"],
            "updated": cache["headlines"]["updated"],
            "count": len(cache["headlines"]["data"]),
        })


@app.route("/api/health")
def api_health():
    with cache_lock:
        now = time.time()
        return jsonify({
            "status": "ok",
            "uptime_sec": round(now - START_TIME),
            "games_age_sec": round(now - cache["games"]["updated"]) if cache["games"]["updated"] else None,
            "headlines_age_sec": round(now - cache["headlines"]["updated"]) if cache["headlines"]["updated"] else None,
        })


@app.route("/")
def index():
    return app.send_static_file("overlay.html")


# ═══════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════

START_TIME = time.time()

if __name__ == "__main__":
    log.info("Starting HoopsHype Loop server...")

    # Start background threads
    Thread(
        target=refresh_loop,
        args=("games", fetch_games, CFG["nba_api"]["refresh_interval_sec"]),
        daemon=True,
    ).start()

    Thread(
        target=refresh_loop,
        args=("headlines", fetch_headlines, CFG["hoopshype_ticker"]["refresh_interval_sec"]),
        daemon=True,
    ).start()

    log.info(f"Server running on http://{CFG['server']['host']}:{CFG['server']['port']}")
    app.run(
        host=CFG["server"]["host"],
        port=CFG["server"]["port"],
        debug=False,
    )
