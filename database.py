"""Supabase REST layer — all DB calls live here."""
from __future__ import annotations

import json
import logging
from typing import Any

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, CALIBRATION_GAMES, CUBE_SUPABASE_URL, CUBE_SUPABASE_KEY

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ── Users ────────────────────────────────────────────────────────────────────

def get_user(user_id: int) -> dict | None:
    res = get_client().table("users").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


def create_user(user_id: int, username: str | None, display_name: str) -> dict:
    row = {"user_id": user_id, "username": username, "display_name": display_name, "rating": 0}
    res = get_client().table("users").insert(row).execute()
    return res.data[0]


def update_user(user_id: int, **fields) -> None:
    get_client().table("users").update(fields).eq("user_id", user_id).execute()


def get_user_by_username(username: str) -> dict | None:
    clean = username.lstrip("@").lower()
    res = (
        get_client()
        .table("users")
        .select("*")
        .ilike("username", clean)
        .execute()
    )
    return res.data[0] if res.data else None


def get_all_users(exclude_user_id: int | None = None) -> list[dict]:
    """All registered users sorted by rating, optionally excluding one user."""
    res = (
        get_client()
        .table("users")
        .select("user_id, display_name, username, rating, games_played, is_calibrated")
        .order("rating", desc=True)
        .execute()
    )
    users = res.data or []
    if exclude_user_id is not None:
        users = [u for u in users if u["user_id"] != exclude_user_id]
    return users


def get_leaderboard(limit: int = 10) -> list[dict]:
    res = (
        get_client()
        .table("users")
        .select("user_id, display_name, username, rating, games_played, wins, losses, is_calibrated, calibration_games")
        .order("rating", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ── Leagues & Clubs ──────────────────────────────────────────────────────────

def get_leagues() -> list[dict]:
    res = get_client().table("leagues").select("*").execute()
    return res.data or []


def get_clubs_by_league(league_id: str) -> list[dict]:
    res = (
        get_client()
        .table("clubs")
        .select("club_id, club_name")
        .eq("league_id", league_id)
        .order("club_name")
        .execute()
    )
    return res.data or []


def upsert_club(club_id: str, club_name: str, league_id: str) -> None:
    from datetime import datetime, timezone
    row = {
        "club_id": club_id,
        "club_name": club_name,
        "league_id": league_id,
        "last_fetched": datetime.now(timezone.utc).isoformat(),
    }
    get_client().table("clubs").upsert(row).execute()


# ── Transfers ────────────────────────────────────────────────────────────────

def get_transfers_by_club(club_id: str, limit: int = 20) -> list[dict]:
    res = (
        get_client()
        .table("transfers")
        .select("*")
        .eq("club_id", club_id)
        .not_.is_("transfer_fee", "null")
        .gt("transfer_fee", 0)
        .order("transfer_fee", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_transfer(transfer_id: int) -> dict | None:
    res = get_client().table("transfers").select("*").eq("id", transfer_id).execute()
    return res.data[0] if res.data else None


def get_distractor_values(field: str, exclude: str, pool_size: int = 80) -> list[str]:
    """Return a deduplicated pool of values for `field` (excluding `exclude`) for use as MC distractors."""
    allowed = {"nationality", "from_club"}
    if field not in allowed:
        return []
    res = (
        get_client()
        .table("transfers")
        .select(field)
        .not_.is_(field, "null")
        .neq(field, "")
        .neq(field, exclude)
        .limit(pool_size)
        .execute()
    )
    seen: set[str] = set()
    result: list[str] = []
    for row in res.data or []:
        val = (row.get(field) or "").strip()
        if val and val not in seen:
            seen.add(val)
            result.append(val)
    return result


def upsert_transfer(data: dict) -> dict:
    res = (
        get_client()
        .table("transfers")
        .upsert(data, on_conflict="club_id,player_name,season")
        .execute()
    )
    return res.data[0] if res.data else {}


def count_transfers_for_club(club_id: str) -> int:
    res = (
        get_client()
        .table("transfers")
        .select("id", count="exact")
        .eq("club_id", club_id)
        .not_.is_("transfer_fee", "null")
        .gt("transfer_fee", 0)
        .execute()
    )
    return res.count or 0


# ── Pending Actions ──────────────────────────────────────────────────────────

def get_pending_action(user_id: int) -> dict | None:
    res = (
        get_client()
        .table("pending_actions")
        .select("action, data")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def set_pending_action(user_id: int, action: str, data: dict) -> None:
    from datetime import datetime, timezone
    row = {
        "user_id": user_id,
        "action": action,
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    get_client().table("pending_actions").upsert(row, on_conflict="user_id").execute()


def clear_pending_action(user_id: int) -> None:
    get_client().table("pending_actions").delete().eq("user_id", user_id).execute()


# ── Challenges ───────────────────────────────────────────────────────────────

def create_challenge(challenger_id: int, challenged_id: int) -> dict:
    row = {"challenger_id": challenger_id, "challenged_id": challenged_id}
    res = get_client().table("challenges").insert(row).execute()
    return res.data[0]


def get_challenge(challenge_id: int) -> dict | None:
    res = get_client().table("challenges").select("*").eq("id", challenge_id).execute()
    return res.data[0] if res.data else None


def update_challenge_status(challenge_id: int, status: str) -> None:
    get_client().table("challenges").update({"status": status}).eq("id", challenge_id).execute()


# ── Games ────────────────────────────────────────────────────────────────────

def create_game(player1_id: int, player2_id: int) -> dict:
    row = {"player1_id": player1_id, "player2_id": player2_id}
    res = get_client().table("games").insert(row).execute()
    return res.data[0]


def get_game(game_id: int) -> dict | None:
    res = get_client().table("games").select("*").eq("game_id", game_id).execute()
    return res.data[0] if res.data else None


def update_game(game_id: int, **fields) -> None:
    get_client().table("games").update(fields).eq("game_id", game_id).execute()


def finish_game(game_id: int, winner_id: int | None, p1_score: int, p2_score: int) -> None:
    from datetime import datetime, timezone
    get_client().table("games").update({
        "status": "finished",
        "winner_id": winner_id,
        "player1_score": p1_score,
        "player2_score": p2_score,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }).eq("game_id", game_id).execute()


# ── Game Rounds ──────────────────────────────────────────────────────────────

def create_round(game_id: int, round_num: int, picker_id: int, guesser_id: int) -> dict:
    row = {
        "game_id": game_id,
        "round_num": round_num,
        "picker_id": picker_id,
        "guesser_id": guesser_id,
    }
    res = get_client().table("game_rounds").insert(row).execute()
    return res.data[0]


def get_round(game_id: int, round_num: int) -> dict | None:
    res = (
        get_client()
        .table("game_rounds")
        .select("*")
        .eq("game_id", game_id)
        .eq("round_num", round_num)
        .execute()
    )
    return res.data[0] if res.data else None


def update_round(round_id: int, **fields) -> None:
    get_client().table("game_rounds").update(fields).eq("id", round_id).execute()


def get_user_total_guessing_score(user_id: int) -> int:
    """Sum of points_earned for all completed rounds where user was the guesser."""
    res = (
        get_client()
        .table("game_rounds")
        .select("points_earned")
        .eq("guesser_id", user_id)
        .eq("completed", True)
        .execute()
    )
    return sum(r.get("points_earned", 0) or 0 for r in (res.data or []))


def get_all_rounds(game_id: int) -> list[dict]:
    res = (
        get_client()
        .table("game_rounds")
        .select("*")
        .eq("game_id", game_id)
        .order("round_num")
        .execute()
    )
    return res.data or []


# ── ELO update after game ────────────────────────────────────────────────────

def get_coins(user_id: int) -> int:
    """Return current coin balance for a user."""
    user = get_user(user_id)
    return user.get("coins", 0) if user else 0


def add_coins(user_id: int, amount: int) -> int:
    """Increment coins for a user. Returns new balance."""
    user = get_user(user_id)
    current = user.get("coins", 0) if user else 0
    new_balance = current + amount
    get_client().table("users").update({"coins": new_balance}).eq("user_id", user_id).execute()
    return new_balance


def spend_coins(user_id: int, amount: int) -> tuple[bool, int]:
    """Deduct coins if sufficient. Returns (ok, new_balance).
    If insufficient, returns (False, current_balance) without changing anything."""
    user = get_user(user_id)
    current = user.get("coins", 0) if user else 0
    if current < amount:
        return False, current
    new_balance = current - amount
    get_client().table("users").update({"coins": new_balance}).eq("user_id", user_id).execute()
    return True, new_balance


# ── Global Roulette ──────────────────────────────────────────────────────────

def get_global_roulette_state() -> dict:
    """Returns the single global_roulette row."""
    res = get_client().table("global_roulette").select("*").eq("id", 1).execute()
    if res.data:
        return res.data[0]
    return {"id": 1, "round": 0, "pot": 0, "last_spin_at": None}


def get_global_roulette_bets(round_id: int) -> list[dict]:
    """All bets for the given round."""
    res = (
        get_client()
        .table("global_roulette_bets")
        .select("user_id, amount")
        .eq("round", round_id)
        .execute()
    )
    return res.data or []


def add_global_roulette_bet(user_id: int, amount: int) -> tuple[bool, int]:
    """Spend coins and record a bet in the current round. Returns (ok, new_balance)."""
    ok, new_balance = spend_coins(user_id, amount)
    if not ok:
        return False, new_balance

    state = get_global_roulette_state()
    round_id = state.get("round", 0)
    new_pot  = state.get("pot", 0) + amount

    get_client().table("global_roulette").update({"pot": new_pot}).eq("id", 1).execute()
    get_client().table("global_roulette_bets").insert(
        {"round": round_id, "user_id": user_id, "amount": amount}
    ).execute()
    return True, new_balance


def close_global_roulette_round(new_pot: int) -> None:
    """Advance to the next round and save the carry-over pot."""
    from datetime import datetime, timezone
    state     = get_global_roulette_state()
    new_round = state.get("round", 0) + 1
    get_client().table("global_roulette").update({
        "round":        new_round,
        "pot":          new_pot,
        "last_spin_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", 1).execute()


def get_pvp_bj_lobbies(exclude_uid: int | None = None) -> list[dict]:
    """Return all pending_actions with action='bj_pvp_host' and status='waiting'."""
    res = (
        get_client()
        .table("pending_actions")
        .select("user_id, data")
        .eq("action", "bj_pvp_host")
        .execute()
    )
    lobbies = [
        r for r in (res.data or [])
        if r.get("data", {}).get("status") == "waiting"
    ]
    if exclude_uid is not None:
        lobbies = [l for l in lobbies if l["user_id"] != exclude_uid]
    return lobbies


# ── FUT Market ───────────────────────────────────────────────────────────────

def create_fut_listing(seller_uid: int, club_id: int, price_coins: int) -> int:
    """Create a market listing. Returns listing id."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    res = get_client().table("fut_market_listings").insert({
        "seller_uid": seller_uid,
        "club_id": club_id,
        "price_coins": price_coins,
        "listed_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=48)).isoformat(),
        "status": "active",
    }).execute()
    return res.data[0]["id"]


def get_fut_listings(limit: int = 15, offset: int = 0) -> list[dict]:
    """Active non-expired listings."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    res = (
        get_client()
        .table("fut_market_listings")
        .select("id, seller_uid, club_id, price_coins, listed_at, expires_at")
        .eq("status", "active")
        .gt("expires_at", now)
        .order("listed_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return res.data or []


def get_my_fut_listings(seller_uid: int) -> list[dict]:
    """All active listings for this seller."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    res = (
        get_client()
        .table("fut_market_listings")
        .select("id, seller_uid, club_id, price_coins, listed_at, expires_at")
        .eq("seller_uid", seller_uid)
        .eq("status", "active")
        .gt("expires_at", now)
        .order("listed_at", desc=True)
        .execute()
    )
    return res.data or []


def get_fut_listing(listing_id: int) -> dict | None:
    """Single listing row."""
    res = (
        get_client()
        .table("fut_market_listings")
        .select("id, seller_uid, club_id, price_coins, listed_at, expires_at, status")
        .eq("id", listing_id)
        .execute()
    )
    return res.data[0] if res.data else None


def cancel_fut_listing(listing_id: int, seller_uid: int) -> bool:
    """Cancel listing if owned by seller and still active."""
    res = (
        get_client()
        .table("fut_market_listings")
        .update({"status": "cancelled"})
        .eq("id", listing_id)
        .eq("seller_uid", seller_uid)
        .eq("status", "active")
        .execute()
    )
    return bool(res.data)


def mark_listing_sold(listing_id: int) -> bool:
    """Mark a listing as sold (must still be active)."""
    res = (
        get_client()
        .table("fut_market_listings")
        .update({"status": "sold"})
        .eq("id", listing_id)
        .eq("status", "active")
        .execute()
    )
    return bool(res.data)


# ── FUT Trade Offers ─────────────────────────────────────────────────────────

def create_trade_offer(
    from_uid: int, to_uid: int,
    offer_club_ids: list[int], offer_coins: int,
    want_club_ids: list[int], want_coins: int,
) -> int:
    """Create a trade offer. Returns offer id."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    res = get_client().table("fut_trade_offers").insert({
        "from_uid": from_uid,
        "to_uid": to_uid,
        "offer_club_ids": offer_club_ids,
        "offer_coins": offer_coins,
        "want_club_ids": want_club_ids,
        "want_coins": want_coins,
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
    }).execute()
    return res.data[0]["id"]


def get_incoming_trade_offers(to_uid: int) -> list[dict]:
    """Pending non-expired offers addressed to this user."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    res = (
        get_client()
        .table("fut_trade_offers")
        .select("*")
        .eq("to_uid", to_uid)
        .eq("status", "pending")
        .gt("expires_at", now)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_outgoing_trade_offers(from_uid: int) -> list[dict]:
    """Pending offers sent by this user."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    res = (
        get_client()
        .table("fut_trade_offers")
        .select("*")
        .eq("from_uid", from_uid)
        .eq("status", "pending")
        .gt("expires_at", now)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_trade_offer(offer_id: int) -> dict | None:
    """Single trade offer row."""
    res = (
        get_client()
        .table("fut_trade_offers")
        .select("*")
        .eq("id", offer_id)
        .execute()
    )
    return res.data[0] if res.data else None


def mark_trade_offer_accepted(offer_id: int, to_uid: int) -> bool:
    """Mark offer as accepted (validates ownership and pending status)."""
    res = (
        get_client()
        .table("fut_trade_offers")
        .update({"status": "accepted"})
        .eq("id", offer_id)
        .eq("to_uid", to_uid)
        .eq("status", "pending")
        .execute()
    )
    return bool(res.data)


def decline_trade_offer(offer_id: int, to_uid: int) -> bool:
    res = (
        get_client()
        .table("fut_trade_offers")
        .update({"status": "declined"})
        .eq("id", offer_id)
        .eq("to_uid", to_uid)
        .eq("status", "pending")
        .execute()
    )
    return bool(res.data)


def cancel_trade_offer(offer_id: int, from_uid: int) -> bool:
    res = (
        get_client()
        .table("fut_trade_offers")
        .update({"status": "cancelled"})
        .eq("id", offer_id)
        .eq("from_uid", from_uid)
        .eq("status", "pending")
        .execute()
    )
    return bool(res.data)


# ── FUT Tournaments ──────────────────────────────────────────────────────────

def create_fut_tournament(host_uid: int, entry_fee: int) -> str:
    """Create tournament lobby, return tour_id."""
    import random
    import string
    from datetime import datetime, timezone
    tour_id = "DR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    get_client().table("fut_tournaments").insert({
        "id": tour_id,
        "host_uid": host_uid,
        "entry_fee": entry_fee,
        "status": "lobby",
        "slots": [],
        "matches": {},
        "round": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return tour_id


def get_fut_tournament(tour_id: str) -> dict | None:
    res = get_client().table("fut_tournaments").select("*").eq("id", tour_id).execute()
    return res.data[0] if res.data else None


def update_fut_tournament(tour_id: str, **fields) -> None:
    get_client().table("fut_tournaments").update(fields).eq("id", tour_id).execute()


def get_active_tournament_for_user(uid: int) -> dict | None:
    """Return a non-completed tournament where uid is host or in slots."""
    res = (
        get_client().table("fut_tournaments")
        .select("*").eq("host_uid", uid)
        .neq("status", "completed")
        .order("created_at", desc=True).limit(1).execute()
    )
    if res.data:
        return res.data[0]
    res2 = (
        get_client().table("fut_tournaments")
        .select("*").neq("status", "completed").execute()
    )
    for t in (res2.data or []):
        slots = t.get("slots") or []
        if any(s.get("uid") == uid for s in slots):
            return t
    return None


def apply_elo_result(
    user_a: dict,
    user_b: dict,
    new_rating_a: int,
    new_rating_b: int,
    a_won: bool | None,
) -> None:
    """Update ratings and win/loss counters."""
    a_id = user_a["user_id"]
    b_id = user_b["user_id"]

    # Only increment calibration counter until the threshold is reached
    cal_a = min(user_a["calibration_games"] + 1, CALIBRATION_GAMES)
    cal_b = min(user_b["calibration_games"] + 1, CALIBRATION_GAMES)
    is_cal_a = user_a["is_calibrated"] or cal_a >= CALIBRATION_GAMES
    is_cal_b = user_b["is_calibrated"] or cal_b >= CALIBRATION_GAMES

    update_user(
        a_id,
        rating=new_rating_a,
        games_played=user_a["games_played"] + 1,
        wins=user_a["wins"] + (1 if a_won is True else 0),
        losses=user_a["losses"] + (1 if a_won is False else 0),
        calibration_games=cal_a,
        is_calibrated=is_cal_a,
    )
    update_user(
        b_id,
        rating=new_rating_b,
        games_played=user_b["games_played"] + 1,
        wins=user_b["wins"] + (1 if a_won is False else 0),
        losses=user_b["losses"] + (1 if a_won is True else 0),
        calibration_games=cal_b,
        is_calibrated=is_cal_b,
    )


# ── Achievements ─────────────────────────────────────────────────────────────

def get_user_achievements(user_id: int) -> list[str]:
    """Return list of achievement_id strings the user has earned."""
    res = (
        get_client()
        .table("fut_achievements")
        .select("achievement_id")
        .eq("user_id", user_id)
        .execute()
    )
    return [r["achievement_id"] for r in (res.data or [])]


def award_achievement(user_id: int, achievement_id: str) -> bool:
    """Award achievement if not already earned. Returns True if newly awarded."""
    try:
        get_client().table("fut_achievements").insert({
            "user_id": user_id,
            "achievement_id": achievement_id,
        }).execute()
        return True
    except Exception:
        return False  # UNIQUE constraint — already earned


def get_total_exact_guesses(user_id: int) -> int:
    """Count all-time exact guesses for a user from game_rounds."""
    res = (
        get_client()
        .table("game_rounds")
        .select("id")
        .eq("guesser_id", user_id)
        .eq("accuracy_tier", "exact")
        .eq("completed", True)
        .execute()
    )
    return len(res.data or [])


def get_win_streak(user_id: int) -> int:
    user = get_user(user_id)
    return user.get("win_streak", 0) if user else 0


def set_win_streak(user_id: int, streak: int) -> None:
    update_user(user_id, win_streak=streak)


# ── Club allegiance ───────────────────────────────────────────────────────────

def increment_club_guess(user_id: int, club_id: str) -> int:
    """Increment correct-guess counter for a club. Returns new total."""
    res = (
        get_client().table("club_guess_counts")
        .select("correct_count")
        .eq("user_id", user_id)
        .eq("club_id", club_id)
        .execute()
    )
    if res.data:
        new_count = res.data[0]["correct_count"] + 1
        get_client().table("club_guess_counts").update(
            {"correct_count": new_count}
        ).eq("user_id", user_id).eq("club_id", club_id).execute()
    else:
        new_count = 1
        get_client().table("club_guess_counts").insert(
            {"user_id": user_id, "club_id": club_id, "correct_count": 1}
        ).execute()
    return new_count


def get_club_guess_count(user_id: int, club_id: str) -> int:
    """Return how many transfers from this club the user has guessed correctly."""
    res = (
        get_client().table("club_guess_counts")
        .select("correct_count")
        .eq("user_id", user_id)
        .eq("club_id", club_id)
        .execute()
    )
    return res.data[0]["correct_count"] if res.data else 0


def get_club_guess_counts(user_id: int) -> dict[str, int]:
    """Return {club_id: correct_count} for all clubs the user has guessed from."""
    res = (
        get_client().table("club_guess_counts")
        .select("club_id, correct_count")
        .eq("user_id", user_id)
        .order("correct_count", desc=True)
        .execute()
    )
    return {r["club_id"]: r["correct_count"] for r in (res.data or [])}


def get_unlocked_clubs(user_id: int, threshold: int = 5) -> list[str]:
    """Return club_ids where user has reached the unlock threshold."""
    res = (
        get_client().table("club_guess_counts")
        .select("club_id")
        .eq("user_id", user_id)
        .gte("correct_count", threshold)
        .execute()
    )
    return [r["club_id"] for r in (res.data or [])]


def set_club_allegiance(user_id: int, club_id: str | None) -> None:
    """Set or clear a user's club allegiance."""
    update_user(user_id, club_allegiance=club_id)


# ── Cosmetics ─────────────────────────────────────────────────────────────────

def get_user_cosmetics(user_id: int, cosmetic_type: str | None = None) -> list[str]:
    """Return list of cosmetic_ids of the given type (or all types) owned by user."""
    q = get_client().table("fut_cosmetics").select("cosmetic_id, cosmetic_type").eq("user_id", user_id)
    if cosmetic_type:
        q = q.eq("cosmetic_type", cosmetic_type)
    res = q.order("unlocked_at").execute()
    return [r["cosmetic_id"] for r in (res.data or [])]


def award_cosmetic(user_id: int, cosmetic_type: str, cosmetic_id: str) -> bool:
    """Award cosmetic if not already owned. Returns True if newly awarded."""
    try:
        get_client().table("fut_cosmetics").insert({
            "user_id": user_id,
            "cosmetic_type": cosmetic_type,
            "cosmetic_id": cosmetic_id,
        }).execute()
        return True
    except Exception:
        return False


def get_active_title(user_id: int) -> str | None:
    user = get_user(user_id)
    return user.get("active_title") if user else None


def set_active_title(user_id: int, title_id: str | None) -> None:
    update_user(user_id, active_title=title_id)


def revoke_achievement(user_id: int, achievement_id: str) -> bool:
    """Remove an achievement. Returns True if it existed."""
    try:
        res = (
            get_client()
            .table("fut_achievements")
            .delete()
            .eq("user_id", user_id)
            .eq("achievement_id", achievement_id)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def revoke_cosmetic(user_id: int, cosmetic_type: str, cosmetic_id: str) -> bool:
    """Remove a cosmetic. Returns True if it existed."""
    try:
        res = (
            get_client()
            .table("fut_cosmetics")
            .delete()
            .eq("user_id", user_id)
            .eq("cosmetic_type", cosmetic_type)
            .eq("cosmetic_id", cosmetic_id)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def revoke_all_cosmetics(user_id: int) -> None:
    """Remove all cosmetics and clear active title for a user."""
    get_client().table("fut_cosmetics").delete().eq("user_id", user_id).execute()
    update_user(user_id, active_title=None)


def revoke_all_achievements(user_id: int) -> None:
    """Remove all achievements for a user."""
    get_client().table("fut_achievements").delete().eq("user_id", user_id).execute()


# ── Cosmetic definitions (editable via debug panel) ───────────────────────────

def get_cosmetic_overrides() -> dict[str, dict]:
    """
    Returns DB overrides keyed by cosmetic_id.
    Each value: {cosmetic_type, emoji, label, body}
    """
    res = get_client().table("cosmetic_definitions").select("*").execute()
    return {r["cosmetic_id"]: r for r in (res.data or [])}


def upsert_cosmetic_def(cosmetic_id: str, cosmetic_type: str, **fields) -> None:
    """Save or update a cosmetic definition override."""
    from datetime import datetime, timezone
    res = get_client().table("cosmetic_definitions").upsert(
        {
            "cosmetic_id":   cosmetic_id,
            "cosmetic_type": cosmetic_type,
            "updated_at":    datetime.now(timezone.utc).isoformat(),
            **fields,
        },
        on_conflict="cosmetic_id,cosmetic_type",
    ).execute()
    if not res.data:
        raise RuntimeError(f"upsert_cosmetic_def returned no data for {cosmetic_id}/{cosmetic_type}")


def reset_cosmetic_def(cosmetic_id: str, cosmetic_type: str) -> None:
    """Remove a cosmetic definition override (reverts to hardcoded default)."""
    get_client().table("cosmetic_definitions").delete()\
        .eq("cosmetic_id", cosmetic_id)\
        .eq("cosmetic_type", cosmetic_type)\
        .execute()


# ── Cubeasses Supabase (кросс-бот обменник) ──────────────────────────────────

import os as _os

_cube_client: "Client | None" = None
_cube_client_url: str = ""

CROSS_RATE = 3      # 1 CUB = 3 FUT
CROSS_FEE  = 0.10   # 10% комиссия сжигается


def get_cube_client() -> "Client | None":
    """Supabase клиент для Cubeasses DB."""
    global _cube_client, _cube_client_url
    url = (CUBE_SUPABASE_URL or "").strip()
    key = (CUBE_SUPABASE_KEY or "").strip()
    if not url or not key:
        logger.warning("CUBE_SUPABASE_URL or CUBE_SUPABASE_KEY not set — exchange disabled")
        return None
    if _cube_client is None or _cube_client_url != url:
        logger.info("Creating Cubeasses Supabase client for url=%s", url[:40])
        _cube_client = create_client(url, key)
        _cube_client_url = url
    return _cube_client


def _cross_calc_fut(amount_in: int, direction: str) -> tuple[int, int]:
    """Возвращает (amount_out, commission) для конвертации в FUT-боте."""
    if direction == "fut_to_cube":
        gross      = amount_in / CROSS_RATE
        commission = max(0, round(gross * CROSS_FEE))
        return max(1, int(gross) - int(commission)), int(commission)
    else:  # cube_to_fut (для отображения)
        gross      = amount_in * CROSS_RATE
        commission = max(1, round(gross * CROSS_FEE))
        return gross - commission, commission


def create_fut_to_cube_transfer(user_id: int, amount_in: int) -> tuple[bool, int, str]:
    """
    FUT→Куб: списывает FUT-монеты, создаёт pending-запись в Cubeasses Supabase.
    Возвращает (ok, transfer_id, error).
    """
    cc = get_cube_client()
    if not cc:
        return False, 0, "Обменник временно недоступен. Обратитесь к администратору."
    if amount_in <= 0:
        return False, 0, "Сумма должна быть положительной."

    amount_out, commission = _cross_calc_fut(amount_in, "fut_to_cube")

    ok, _ = spend_coins(user_id, amount_in)
    if not ok:
        return False, 0, "Недостаточно FUT-монет."

    r = cc.table("cross_transfers").insert({
        "user_id":    user_id,
        "direction":  "fut_to_cube",
        "amount_in":  amount_in,
        "commission": commission,
        "amount_out": amount_out,
        "status":     "pending",
    }).execute()
    if not r.data:
        add_coins(user_id, amount_in)  # возвращаем монеты при ошибке БД
        return False, 0, "Ошибка базы данных."
    return True, r.data[0]["id"], ""


def get_cube_to_fut_pending(user_id: int) -> list[dict]:
    """Pending cube_to_fut переводы (забрать в FUT-боте)."""
    cc = get_cube_client()
    if not cc:
        return []
    r = (
        cc.table("cross_transfers")
        .select("*")
        .eq("user_id", user_id)
        .eq("direction", "cube_to_fut")
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    return r.data or []


def claim_cube_to_fut(user_id: int) -> tuple[bool, int, str]:
    """Забирает pending cube_to_fut переводы: добавляет FUT-монеты, маркирует claimed."""
    import datetime as _dt
    cc = get_cube_client()
    if not cc:
        return False, 0, "Обменник временно недоступен."
    transfers = get_cube_to_fut_pending(user_id)
    if not transfers:
        return False, 0, "Нет ожидающих переводов."

    total_out = sum(int(t["amount_out"]) for t in transfers)
    ids       = [t["id"] for t in transfers]
    now_iso   = _dt.datetime.now(_dt.timezone.utc).isoformat()

    cc.table("cross_transfers").update({
        "status":     "claimed",
        "claimed_at": now_iso,
    }).in_("id", ids).execute()

    add_coins(user_id, total_out)
    return True, total_out, ""


def get_fut_to_cube_pending(user_id: int) -> list[dict]:
    """Pending fut_to_cube переводы (для отображения в меню FUT-бота)."""
    cc = get_cube_client()
    if not cc:
        return []
    r = (
        cc.table("cross_transfers")
        .select("*")
        .eq("user_id", user_id)
        .eq("direction", "fut_to_cube")
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    return r.data or []


def cancel_fut_to_cube_transfer(transfer_id: int, user_id: int) -> tuple[bool, str]:
    """Отменяет pending fut_to_cube перевод и возвращает FUT-монеты."""
    cc = get_cube_client()
    if not cc:
        return False, "Обменник временно недоступен."
    r = (
        cc.table("cross_transfers")
        .select("*")
        .eq("id", transfer_id)
        .eq("user_id", user_id)
        .eq("status", "pending")
        .execute()
    )
    if not r.data:
        return False, "Перевод не найден."
    t = r.data[0]
    cc.table("cross_transfers").update({"status": "expired"}).eq("id", transfer_id).execute()
    add_coins(user_id, int(t["amount_in"]))  # возвращаем FUT-монеты
    return True, ""


# ── World Cup Predictions ─────────────────────────────────────────────────────

def wc_match_status(m: dict) -> str:
    """Вычисляет эффективный статус матча (lazy, без фоновых задач).

    upcoming — команды не определены (TBD плей-офф) или матч ещё рано
    open     — приём прогнозов (до начала матча)
    closed   — матч начался / закрыт админом, ждёт результата
    done     — результат внесён
    """
    from datetime import datetime, timezone
    home = m.get("home")
    away = m.get("away")
    if not home or not away or home in ("?", "TBD", "") or away in ("?", "TBD", ""):
        return "upcoming"
    if m.get("home_goals") is not None and m.get("away_goals") is not None:
        return "done"
    if m.get("locked"):
        return "closed"
    ko = m.get("kickoff")
    if ko:
        try:
            kt = datetime.fromisoformat(ko)
            if kt.tzinfo is None:
                kt = kt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= kt:
                return "closed"
        except Exception:
            pass
    return "open"


def _wc_inject_status(wc: dict | None) -> dict | None:
    """Проставляет вычисленный статус каждому матчу расписания (in-memory)."""
    if wc:
        for m in (wc.get("schedule") or []):
            m["status"] = wc_match_status(m)
    return wc


def get_active_wc() -> dict | None:
    res = (
        get_client().table("wc_cups")
        .select("*").neq("status", "finished")
        .order("created_at", desc=True).limit(1).execute()
    )
    return _wc_inject_status(res.data[0] if res.data else None)


def get_wc(wc_id: str) -> dict | None:
    res = get_client().table("wc_cups").select("*").eq("id", wc_id).execute()
    return _wc_inject_status(res.data[0] if res.data else None)


def create_wc(admin_uid: int, schedule: list, settings: dict) -> str:
    import random
    import string
    from datetime import datetime, timezone
    wc_id = "WC-" + "".join(random.choices(string.digits, k=4))
    get_client().table("wc_cups").insert({
        "id": wc_id,
        "created_by": admin_uid,
        "status": "active",
        "schedule": schedule,
        "settings": settings,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return wc_id


def update_wc(wc_id: str, **fields) -> None:
    get_client().table("wc_cups").update(fields).eq("id", wc_id).execute()


def wc_join(wc_id: str, uid: int, name: str) -> tuple[bool, str]:
    existing = (
        get_client().table("wc_participants")
        .select("user_id").eq("wc_id", wc_id).eq("user_id", uid).execute()
    )
    if existing.data:
        return False, "already_joined"
    try:
        get_client().table("wc_participants").insert({
            "wc_id": wc_id, "user_id": uid, "name": name,
            "total_points": 0, "exact_scores": 0,
        }).execute()
        return True, "ok"
    except Exception as e:
        return False, str(e)


def wc_get_participants(wc_id: str) -> list[dict]:
    res = (
        get_client().table("wc_participants").select("*")
        .eq("wc_id", wc_id)
        .order("total_points", desc=True)
        .order("exact_scores", desc=True)
        .execute()
    )
    return res.data or []


def wc_get_participant(wc_id: str, uid: int) -> dict | None:
    res = (
        get_client().table("wc_participants").select("*")
        .eq("wc_id", wc_id).eq("user_id", uid).execute()
    )
    return res.data[0] if res.data else None


def wc_submit_prediction(
    wc_id: str, uid: int, match_id: str,
    pred_winner: str, pred_home: int | None = None, pred_away: int | None = None,
) -> tuple[bool, str]:
    wc = get_wc(wc_id)
    if not wc:
        return False, "ЧМ не найден"
    match = next((m for m in (wc.get("schedule") or []) if m["id"] == match_id), None)
    if not match:
        return False, "Матч не найден"
    if match.get("status") != "open":
        return False, "Прогнозы на этот матч закрыты"
    if not wc_get_participant(wc_id, uid):
        return False, "Сначала вступи в ЧМ!"
    if pred_home is None or pred_away is None:
        return False, "По регламенту нужно указать точный счёт"
    # Регламент: счета не повторяются — проверяем, не занят ли счёт другим участником
    taken = (
        get_client().table("wc_predictions").select("user_id")
        .eq("wc_id", wc_id).eq("match_id", match_id)
        .eq("pred_home", pred_home).eq("pred_away", pred_away)
        .neq("user_id", uid)
        .execute()
    )
    if taken.data:
        return False, f"Счёт {pred_home}:{pred_away} уже занят другим участником!"
    try:
        existing = (
            get_client().table("wc_predictions").select("wc_id")
            .eq("wc_id", wc_id).eq("user_id", uid).eq("match_id", match_id).execute()
        )
        if existing.data:
            get_client().table("wc_predictions").update({
                "pred_winner": pred_winner,
                "pred_home": pred_home,
                "pred_away": pred_away,
            }).eq("wc_id", wc_id).eq("user_id", uid).eq("match_id", match_id).execute()
        else:
            get_client().table("wc_predictions").insert({
                "wc_id": wc_id, "user_id": uid, "match_id": match_id,
                "pred_winner": pred_winner,
                "pred_home": pred_home, "pred_away": pred_away,
                "points_earned": 0, "resolved": False,
            }).execute()
        return True, "ok"
    except Exception as e:
        err_s = str(e).lower()
        if "duplicate" in err_s or "unique" in err_s:
            return False, f"Счёт {pred_home}:{pred_away} уже занят другим участником!"
        return False, str(e)


def wc_get_match_predictions(wc_id: str, match_id: str) -> list[dict]:
    """Все прогнозы на конкретный матч (для проверки занятых счетов / просмотра)."""
    res = (
        get_client().table("wc_predictions").select("*")
        .eq("wc_id", wc_id).eq("match_id", match_id).execute()
    )
    return res.data or []


def wc_get_user_predictions(wc_id: str, uid: int) -> dict[str, dict]:
    res = (
        get_client().table("wc_predictions").select("*")
        .eq("wc_id", wc_id).eq("user_id", uid).execute()
    )
    return {p["match_id"]: p for p in (res.data or [])}


def _wc_score_pred(pred: dict, home_goals: int, away_goals: int) -> int:
    """Очки по регламенту: точный счёт — 5, исход — 3, угаданная разница — +1."""
    actual_winner = "home" if home_goals > away_goals else ("away" if away_goals > home_goals else "draw")
    actual_diff   = home_goals - away_goals
    ph = pred.get("pred_home")
    pa = pred.get("pred_away")
    if pred["pred_winner"] != actual_winner:
        return 0
    if ph is not None and pa is not None and ph == home_goals and pa == away_goals:
        return 5
    pts = 3
    if ph is not None and pa is not None and (ph - pa) == actual_diff:
        pts += 1
    return pts


def wc_set_match_result(wc_id: str, match_id: str, home_goals: int, away_goals: int) -> dict:
    wc = get_wc(wc_id)
    if not wc:
        return {"ok": False, "err": "WC not found"}

    schedule = wc.get("schedule") or []
    match_found = False
    for m in schedule:
        if m["id"] == match_id:
            m["home_goals"] = home_goals
            m["away_goals"] = away_goals
            m["status"] = "done"
            match_found = True
            break
    if not match_found:
        return {"ok": False, "err": "Match not found"}
    update_wc(wc_id, schedule=schedule)

    # Берём ВСЕ прогнозы (в т.ч. уже подведённые — для исправления результата)
    res = (
        get_client().table("wc_predictions").select("*")
        .eq("wc_id", wc_id).eq("match_id", match_id).execute()
    )
    predictions = res.data or []
    summary = {"ok": True, "total": len(predictions),
               "correct_winner": 0, "correct_diff": 0, "exact_scores": 0}

    for pred in predictions:
        old_pts = pred.get("points_earned", 0) if pred.get("resolved") else 0
        new_pts = _wc_score_pred(pred, home_goals, away_goals)

        if new_pts > 0:
            summary["correct_winner"] += 1
            if new_pts == 5:
                summary["exact_scores"] += 1
            elif new_pts == 4:
                summary["correct_diff"] += 1

        get_client().table("wc_predictions").update({
            "points_earned": new_pts, "resolved": True,
        }).eq("wc_id", wc_id).eq("user_id", pred["user_id"]).eq("match_id", match_id).execute()

        # Корректируем баланс участника на дельту (поддержка исправления)
        delta_pts   = new_pts - old_pts
        old_exact   = 1 if old_pts == 5 else 0
        new_exact   = 1 if new_pts == 5 else 0
        delta_exact = new_exact - old_exact
        if delta_pts != 0 or delta_exact != 0:
            part = wc_get_participant(wc_id, pred["user_id"])
            if part:
                get_client().table("wc_participants").update({
                    "total_points": part["total_points"] + delta_pts,
                    "exact_scores": max(0, part["exact_scores"] + delta_exact),
                }).eq("wc_id", wc_id).eq("user_id", pred["user_id"]).execute()

    return summary


def wc_set_lock(wc_id: str, match_id: str, locked: bool) -> bool:
    """Ручной override админа: закрыть (locked=True) / снять закрытие (False)."""
    wc = get_wc(wc_id)
    if not wc:
        return False
    schedule = wc.get("schedule") or []
    for m in schedule:
        if m["id"] == match_id:
            m["locked"] = locked
            update_wc(wc_id, schedule=schedule)
            return True
    return False


def wc_set_match_teams(wc_id: str, match_id: str,
                       home: str, home_flag: str,
                       away: str, away_flag: str,
                       kickoff: str | None = None) -> bool:
    """Задать команды для матча (плей-офф TBD → реальные команды)."""
    wc = get_wc(wc_id)
    if not wc:
        return False
    schedule = wc.get("schedule") or []
    for m in schedule:
        if m["id"] == match_id:
            m["home"] = home
            m["home_flag"] = home_flag
            m["away"] = away
            m["away_flag"] = away_flag
            if kickoff:
                m["kickoff"] = kickoff
            update_wc(wc_id, schedule=schedule)
            return True
    return False


def wc_add_match(wc_id: str, match: dict) -> bool:
    wc = get_wc(wc_id)
    if not wc:
        return False
    schedule = wc.get("schedule") or []
    schedule.append(match)
    update_wc(wc_id, schedule=schedule)
    return True
