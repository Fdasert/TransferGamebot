"""Supabase REST layer — all DB calls live here."""
from __future__ import annotations

import json
import logging
from typing import Any

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

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
    row = {"user_id": user_id, "username": username, "display_name": display_name}
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


def get_leaderboard(limit: int = 10) -> list[dict]:
    res = (
        get_client()
        .table("users")
        .select("user_id, display_name, username, rating, games_played, wins, losses, is_calibrated")
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
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_transfer(transfer_id: int) -> dict | None:
    res = get_client().table("transfers").select("*").eq("id", transfer_id).execute()
    return res.data[0] if res.data else None


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
    get_client().table("pending_actions").upsert(row).execute()


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

    cal_a = user_a["calibration_games"] + 1
    cal_b = user_b["calibration_games"] + 1
    is_cal_a = cal_a >= 10
    is_cal_b = cal_b >= 10

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
