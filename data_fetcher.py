"""
Fetches transfer data from a self-hosted transfermarkt-api and caches in Supabase.

API endpoints:
  GET /competitions/{league_id}/clubs          → club list
  GET /clubs/{club_id}/players?season_id=YYYY  → squad (player IDs + info)
  GET /players/{player_id}/transfers           → full transfer history with fees

Run once to populate, then to refresh:
  python data_fetcher.py
"""

import logging
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import TRANSFERMARKT_API_URL
import database as db

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

BASE = TRANSFERMARKT_API_URL.rstrip("/")

LEAGUE_IDS = ["GB1", "ES1", "L1", "IT1", "FR1"]

# Scan these seasons to collect player IDs (player transfers API covers full history)
SQUAD_SEASONS = ["2024", "2022", "2020", "2018", "2015", "2010", "2005", "2000"]

# Parallel workers for player transfer requests
WORKERS = 5

# Min transfer year to store
MIN_YEAR = 2000

# Max unique players to fetch transfers for per club
MAX_PLAYERS_PER_CLUB = 80

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TransferGameBot/1.0"})


def _get(path: str, params: dict | None = None, retries: int = 3) -> dict | None:
    url = f"{BASE}{path}"
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
            else:
                logger.debug("GET %s failed: %s", url, exc)
    return None


def fetch_clubs_for_league(league_id: str) -> list[dict]:
    data = _get(f"/competitions/{league_id}/clubs")
    if not data:
        logger.error("Failed to fetch clubs for league %s", league_id)
        return []

    result = []
    for club in data.get("clubs", []):
        club_id = str(club.get("id", "")).strip()
        club_name = club.get("name", "").strip()
        if club_id and club_name:
            db.upsert_club(club_id, club_name, league_id)
            result.append({"club_id": club_id, "club_name": club_name})

    logger.info("  %d clubs fetched for %s", len(result), league_id)
    return result


def _collect_players_for_club(club_id: str) -> dict[str, dict]:
    """
    Scan multiple seasons, return {player_id: player_info} deduplicated.
    Using a persistent session so TCP connections are reused.
    """
    seen: dict[str, dict] = {}
    for season in SQUAD_SEASONS:
        data = _get(f"/clubs/{club_id}/players", params={"season_id": season})
        if data:
            for p in data.get("players", []):
                pid = str(p.get("id", "")).strip()
                if pid and pid not in seen:
                    seen[pid] = p
        time.sleep(0.15)
    return seen


def _fetch_player_transfers(player_id: str, player_info: dict, club_id: str, club_name: str) -> list[dict]:
    """
    Fetch transfer history for one player, return rows to insert.
    Runs in a thread worker.
    """
    from scoring import format_fee

    data = _get(f"/players/{player_id}/transfers")
    if not data:
        return []

    rows = []
    for t in data.get("transfers", []):
        club_to = t.get("clubTo") or {}
        if str(club_to.get("id", "")) != club_id:
            continue

        fee = t.get("fee")
        if not fee or fee == 0:
            continue

        # Filter by year
        date_str = str(t.get("date", "") or "")
        year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else 0
        if year < MIN_YEAR:
            continue

        club_from = t.get("clubFrom") or {}
        nationality = player_info.get("nationality") or []
        nationality_str = nationality[0] if isinstance(nationality, list) and nationality else str(nationality or "")

        rows.append({
            "club_id": club_id,
            "player_name": player_info.get("name", ""),
            "transfer_fee": int(fee),
            "fee_display": format_fee(fee),
            "season": t.get("season", ""),
            "from_club": club_from.get("name", "") if isinstance(club_from, dict) else "",
            "to_club": club_to.get("name", club_name) if isinstance(club_to, dict) else club_name,
            "position": player_info.get("position"),
            "age": player_info.get("age"),
            "nationality": nationality_str or None,
            "market_value": player_info.get("marketValue"),
            "market_value_display": format_fee(player_info.get("marketValue")),
            "transfer_type": "in",
        })

    return rows


def fetch_transfers_for_club(club_id: str, club_name: str) -> int:
    # Step 1: collect unique players across seasons
    players = _collect_players_for_club(club_id)
    if not players:
        logger.warning("  No players for %s", club_name)
        return 0

    # Sort by market value, take top N
    sorted_players = sorted(
        players.items(),
        key=lambda kv: kv[1].get("marketValue") or 0,
        reverse=True,
    )[:MAX_PLAYERS_PER_CLUB]

    logger.info("  %d unique players → fetching transfers (parallel)…", len(sorted_players))

    # Step 2: fetch player transfers in parallel
    inserted = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(_fetch_player_transfers, pid, pinfo, club_id, club_name): pid
            for pid, pinfo in sorted_players
        }
        for future in as_completed(futures):
            rows = future.result()
            for row in rows:
                try:
                    db.upsert_transfer(row)
                    inserted += 1
                    logger.info("    ✓ %s → %s (%s, %s)",
                                row["player_name"], club_name,
                                row["fee_display"], row["season"])
                except Exception as exc:
                    logger.debug("    Insert failed for %s: %s", row["player_name"], exc)

    return inserted


def run_full_fetch(league_ids: list[str] | None = None):
    target_leagues = league_ids or LEAGUE_IDS
    leagues = [lg for lg in db.get_leagues() if lg["league_id"] in target_leagues]

    if not leagues:
        logger.error("No matching leagues in DB.")
        return

    total_clubs = 0
    total_transfers = 0

    for league in leagues:
        league_id = league["league_id"]
        logger.info("══ %s (%s) ══", league["league_name"], league_id)

        clubs = fetch_clubs_for_league(league_id)
        total_clubs += len(clubs)

        for club in clubs:
            t0 = time.time()
            logger.info("  ▶ %s", club["club_name"])
            count = fetch_transfers_for_club(club["club_id"], club["club_name"])
            total_transfers += count
            elapsed = time.time() - t0
            logger.info("  ✓ %d transfers saved (%.1fs)", count, elapsed)

    logger.info("════════════════════")
    logger.info("Done: %d clubs, %d transfers total.", total_clubs, total_transfers)


if __name__ == "__main__":
    run_full_fetch()
