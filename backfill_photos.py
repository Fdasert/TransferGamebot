"""
Backfill photo_url for transfers that already have player_id.

Does nothing else — no club/squad/transfer fetching.
Run: python backfill_photos.py
"""

import logging
import time
import requests
from config import TRANSFERMARKT_API_URL
import database as db

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

BASE = TRANSFERMARKT_API_URL.rstrip("/")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TransferGameBot/1.0"})


def _photo(player_id: str) -> str | None:
    try:
        r = SESSION.get(f"{BASE}/players/{player_id}/profile", timeout=30)
        r.raise_for_status()
        d = r.json()
        return d.get("imageUrl") or d.get("image_url")
    except Exception as exc:
        logger.debug("Profile %s failed: %s", player_id, exc)
        return None


def run():
    client = db.get_client()

    # All unique player_ids where photo_url is still missing
    rows = (
        client.table("transfers")
        .select("player_id")
        .is_("photo_url", "null")
        .not_.is_("player_id", "null")
        .execute()
        .data
    )

    player_ids = list({r["player_id"] for r in rows})
    logger.info("Players without photo: %d", len(player_ids))

    updated = 0
    for i, pid in enumerate(player_ids, 1):
        url = _photo(pid)
        if url:
            client.table("transfers").update({"photo_url": url}).eq("player_id", pid).execute()
            updated += 1
            logger.info("[%d/%d] ✓ %s", i, len(player_ids), pid)
        else:
            logger.info("[%d/%d] — no photo for %s", i, len(player_ids), pid)
        time.sleep(0.3)

    logger.info("Done: %d/%d updated", updated, len(player_ids))


if __name__ == "__main__":
    run()
