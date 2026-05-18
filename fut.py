"""FUT-режим: пакеты карточек, Мой клуб, Сборка команды.

Пакеты:
  Bronze  — 1 500 монет  — 3 карты, OVR 82–84
  Silver  — 4 000 монет  — 3 карты, OVR 85–87
  Gold    — 12 000 монет — 3 карты, OVR 88–91
  Elite   — 30 000 монет — 3 карты, OVR 92–97
  Mega    — 60 000 монет — 5 карт,  OVR 88–97, гарант. 1× OVR 93+

Шансы выпадения:
  — Рейтинг: взвешенный (высокий OVR = редкость)
  — Спец-версии (TOTY/TOTS/…): в 10× реже

Мой клуб:
  — Список карточек-кнопок, сортировка OVR↓/OVR↑/Позиция
  — Тап → полная карточка со стат-барами
  — Продажа любой карточки, цена по OVR + ×2 за спец-версию

Команда:
  — Схемы: 4-3-3 / 4-4-2 / 4-2-3-1 / 3-5-2 / 5-3-2
  — Поле = клавиатура (каждая позиция = кнопка)
  — Химия: бонус за одну нацию/клуб в составе (0–100)
  — OVR команды = среднее 11 игроков
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  КОНСТАНТЫ
# ══════════════════════════════════════════════════════════════════════════════

PACKS: dict[str, dict] = {
    "bronze": {
        "name": "🥉 Бронзовый пак", "cost": 1_500,  "cards": 3,
        "min_rating": 82, "max_rating": 84, "guaranteed": None,
        "desc": "3 карты • OVR 82–84",
    },
    "silver": {
        "name": "🥈 Серебряный пак", "cost": 4_000,  "cards": 3,
        "min_rating": 85, "max_rating": 87, "guaranteed": None,
        "desc": "3 карты • OVR 85–87",
    },
    "gold": {
        "name": "🥇 Золотой пак",    "cost": 12_000, "cards": 3,
        "min_rating": 88, "max_rating": 91, "guaranteed": None,
        "desc": "3 карты • OVR 88–91",
    },
    "elite": {
        "name": "💎 Элитный пак",    "cost": 30_000, "cards": 3,
        "min_rating": 92, "max_rating": 97, "guaranteed": None,
        "desc": "3 карты • OVR 92–97",
    },
    "mega": {
        "name": "⚡ Мега пак",       "cost": 60_000, "cards": 5,
        "min_rating": 88, "max_rating": 97, "guaranteed": 93,
        "desc": "5 карт • OVR 88–97 • Гарант OVR 93+",
    },
}

RATING_WEIGHTS: dict[int, float] = {
    82: 65.0, 83: 25.0, 84: 10.0,
    85: 60.0, 86: 28.0, 87: 12.0,
    88: 50.0, 89: 28.0, 90: 15.0, 91:  7.0,
    92: 38.0, 93: 28.0, 94: 18.0, 95:  9.0, 96: 5.0, 97: 2.0,
}

SPECIAL_VERSIONS = {
    "TOTY", "TOTS", "FUT BIRTHDAY", "FUTTIES",
    "HEROES", "RTTK", "OTW", "FLASHBACK", "ICON",
}
SPECIAL_MULT = 0.10

_LVL_LEGENDARY = "legendary"
_LVL_EPIC      = "epic"
_LVL_RARE      = "rare"
_LVL_NORMAL    = "normal"

CLUB_PAGE_SIZE = 5
TEAM_PAGE_SIZE = 5

# ── Схемы расстановки ─────────────────────────────────────────────────────────

FORMATIONS: dict[str, dict] = {
    "433": {
        "label": "4-3-3",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "RB": "DEF",
            "CM1": "MID", "CM2": "MID", "CM3": "MID",
            "LW": "ATT", "ST": "ATT", "RW": "ATT",
        },
        "rows": [["LW", "ST", "RW"], ["CM1", "CM2", "CM3"], ["LB", "CB1", "CB2", "RB"], ["GK"]],
    },
    "442": {
        "label": "4-4-2",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "RB": "DEF",
            "LM": "MID", "CM1": "MID", "CM2": "MID", "RM": "MID",
            "ST1": "ATT", "ST2": "ATT",
        },
        "rows": [["ST1", "ST2"], ["LM", "CM1", "CM2", "RM"], ["LB", "CB1", "CB2", "RB"], ["GK"]],
    },
    "4231": {
        "label": "4-2-3-1",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "RB": "DEF",
            "CDM1": "MID", "CDM2": "MID",
            "LW": "ATT", "CAM": "MID", "RW": "ATT",
            "ST": "ATT",
        },
        "rows": [["ST"], ["LW", "CAM", "RW"], ["CDM1", "CDM2"], ["LB", "CB1", "CB2", "RB"], ["GK"]],
    },
    "352": {
        "label": "3-5-2",
        "slots": {
            "GK": "GK",
            "CB1": "DEF", "CB2": "DEF", "CB3": "DEF",
            "LM": "MID", "CM1": "MID", "CM2": "MID", "CM3": "MID", "RM": "MID",
            "ST1": "ATT", "ST2": "ATT",
        },
        "rows": [["ST1", "ST2"], ["LM", "CM1", "CM2", "CM3", "RM"], ["CB1", "CB2", "CB3"], ["GK"]],
    },
    "532": {
        "label": "5-3-2",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "CB3": "DEF", "RB": "DEF",
            "CM1": "MID", "CM2": "MID", "CM3": "MID",
            "ST1": "ATT", "ST2": "ATT",
        },
        "rows": [["ST1", "ST2"], ["CM1", "CM2", "CM3"], ["LB", "CB1", "CB2", "CB3", "RB"], ["GK"]],
    },
    "41212": {
        "label": "4-1-2-1-2 ◆",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "RB": "DEF",
            "CDM": "MID", "LM": "MID", "RM": "MID", "CAM": "MID",
            "ST1": "ATT", "ST2": "ATT",
        },
        "rows": [["ST1", "ST2"], ["CAM"], ["LM", "RM"], ["CDM"], ["LB", "CB1", "CB2", "RB"], ["GK"]],
    },
    "4321": {
        "label": "4-3-2-1 🎄",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "RB": "DEF",
            "CM1": "MID", "CM2": "MID", "CM3": "MID",
            "LAM": "ATT", "RAM": "ATT", "ST": "ATT",
        },
        "rows": [["ST"], ["LAM", "RAM"], ["CM1", "CM2", "CM3"], ["LB", "CB1", "CB2", "RB"], ["GK"]],
    },
    "343": {
        "label": "3-4-3",
        "slots": {
            "GK": "GK",
            "CB1": "DEF", "CB2": "DEF", "CB3": "DEF",
            "LM": "MID", "CM1": "MID", "CM2": "MID", "RM": "MID",
            "LW": "ATT", "ST": "ATT", "RW": "ATT",
        },
        "rows": [["LW", "ST", "RW"], ["LM", "CM1", "CM2", "RM"], ["CB1", "CB2", "CB3"], ["GK"]],
    },
    "451": {
        "label": "4-5-1",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "RB": "DEF",
            "LM": "MID", "CM1": "MID", "CM2": "MID", "CM3": "MID", "RM": "MID",
            "ST": "ATT",
        },
        "rows": [["ST"], ["LM", "CM1", "CM2", "CM3", "RM"], ["LB", "CB1", "CB2", "RB"], ["GK"]],
    },
    "4141": {
        "label": "4-1-4-1",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "RB": "DEF",
            "CDM": "MID",
            "LM": "MID", "CM1": "MID", "CM2": "MID", "RM": "MID",
            "ST": "ATT",
        },
        "rows": [["ST"], ["LM", "CM1", "CM2", "RM"], ["CDM"], ["LB", "CB1", "CB2", "RB"], ["GK"]],
    },
    "541": {
        "label": "5-4-1",
        "slots": {
            "GK": "GK",
            "LB": "DEF", "CB1": "DEF", "CB2": "DEF", "CB3": "DEF", "RB": "DEF",
            "LM": "MID", "CM1": "MID", "CM2": "MID", "RM": "MID",
            "ST": "ATT",
        },
        "rows": [["ST"], ["LM", "CM1", "CM2", "RM"], ["LB", "CB1", "CB2", "CB3", "RB"], ["GK"]],
    },
}

# Короткий ярлык слота (для пустых кнопок)
SLOT_LABEL: dict[str, str] = {
    "GK": "GK", "LB": "LB", "RB": "RB",
    "CB1": "CB", "CB2": "CB", "CB3": "CB",
    "LM": "LM", "RM": "RM",
    "CM1": "CM", "CM2": "CM", "CM3": "CM",
    "CDM": "CDM", "CDM1": "CDM", "CDM2": "CDM",
    "CAM": "CAM", "LAM": "CAM", "RAM": "CAM",
    "LW": "LW", "RW": "RW",
    "ST": "ST", "ST1": "ST", "ST2": "ST",
}

GROUP_ICON: dict[str, str] = {
    "GK": "🧤", "DEF": "🛡", "MID": "⚙️", "ATT": "⚽",
}

GROUP_NAME: dict[str, str] = {
    "GK": "Вратарь", "DEF": "Защитник", "MID": "Полузащитник", "ATT": "Нападающий",
}

# Позиция игрока → какие группы слотов он может занимать
POSITION_CAN_PLAY: dict[str, list[str]] = {
    "GK":  ["GK"],
    "CB":  ["DEF"], "LB": ["DEF"], "RB": ["DEF"],
    "LWB": ["DEF", "MID"], "RWB": ["DEF", "MID"],
    "CDM": ["MID"], "CM": ["MID"], "LM": ["MID"], "RM": ["MID"],
    "CAM": ["MID", "ATT"],
    "LW":  ["ATT", "MID"], "RW": ["ATT", "MID"],
    "LF":  ["ATT"], "RF": ["ATT"], "CF": ["ATT"], "ST": ["ATT"], "SS": ["ATT"],
}

_POS_ORDER: dict[str, int] = {
    "GK": 1,
    "CB": 2, "LB": 2, "RB": 2, "LWB": 2, "RWB": 2,
    "CDM": 3, "CM": 3, "CAM": 3, "LM": 3, "RM": 3,
    "LW": 4, "RW": 4, "LF": 4, "RF": 4, "CF": 4, "ST": 4, "SS": 4,
}

# Флаги наций (полный список из БД)
NATION_FLAGS: dict[str, str] = {
    "Albania": "🇦🇱", "Algeria": "🇩🇿", "Argentina": "🇦🇷",
    "Armenia": "🇦🇲", "Australia": "🇦🇺", "Austria": "🇦🇹",
    "Belgium": "🇧🇪", "Bolivia": "🇧🇴", "Bosnia and Herzegovina": "🇧🇦",
    "Brazil": "🇧🇷", "Bulgaria": "🇧🇬", "Burkina Faso": "🇧🇫",
    "Cameroon": "🇨🇲", "Canada": "🇨🇦", "Cape Verde Islands": "🇨🇻",
    "Chile": "🇨🇱", "Colombia": "🇨🇴", "Congo DR": "🇨🇩",
    "Côte d'Ivoire": "🇨🇮", "Croatia": "🇭🇷", "Czechia": "🇨🇿",
    "Denmark": "🇩🇰", "Ecuador": "🇪🇨", "Egypt": "🇪🇬",
    "England": "🇬🇧", "Finland": "🇫🇮", "France": "🇫🇷",
    "Gabon": "🇬🇦", "Georgia": "🇬🇪", "Germany": "🇩🇪",
    "Ghana": "🇬🇭", "Greece": "🇬🇷", "Guinea": "🇬🇳",
    "Haiti": "🇭🇹", "Honduras": "🇭🇳", "Hungary": "🇭🇺",
    "Iceland": "🇮🇸", "Italy": "🇮🇹", "Jamaica": "🇯🇲",
    "Japan": "🇯🇵", "Jordan": "🇯🇴", "Korea Republic": "🇰🇷",
    "Kosovo": "🇽🇰", "Malawi": "🇲🇼", "Mali": "🇲🇱",
    "Mexico": "🇲🇽", "Montenegro": "🇲🇪", "Morocco": "🇲🇦",
    "Netherlands": "🇳🇱", "New Zealand": "🇳🇿", "Nigeria": "🇳🇬",
    "Northern Ireland": "🇬🇧", "Norway": "🇳🇴", "Paraguay": "🇵🇾",
    "Peru": "🇵🇪", "Poland": "🇵🇱", "Portugal": "🇵🇹",
    "Republic of Ireland": "🇮🇪", "Romania": "🇷🇴", "Russia": "🇷🇺",
    "Saudi Arabia": "🇸🇦", "Scotland": "🇬🇧", "Senegal": "🇸🇳",
    "Serbia": "🇷🇸", "Sierra Leone": "🇸🇱", "Slovakia": "🇸🇰",
    "Slovenia": "🇸🇮", "South Africa": "🇿🇦", "Spain": "🇪🇸",
    "Suriname": "🇸🇷", "Sweden": "🇸🇪", "Switzerland": "🇨🇭",
    "Türkiye": "🇹🇷", "Turkey": "🇹🇷",          # алиас FIFA 19
    "Ukraine": "🇺🇦", "United States": "🇺🇸",
    "Uruguay": "🇺🇾", "Uzbekistan": "🇺🇿", "Wales": "🇬🇧",
    # Алиасы старых версий FIFA
    "Czech Republic": "🇨🇿",                     # FIFA 19 = Czechia
    "Holland": "🇳🇱",                             # FIFA 19 = Netherlands
}


def _flag(nation: str) -> str:
    return NATION_FLAGS.get(nation, "🌍")


# ══════════════════════════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _rarity(rating: int, version: str) -> str:
    v = version.upper()
    if v in SPECIAL_VERSIONS:  return "🌟 Спец"
    if rating >= 95:            return "🔮 Иконка"
    if rating >= 92:            return "💎 Редкая"
    if rating >= 88:            return "🥇 Золотая"
    if rating >= 85:            return "🥈 Серебряная"
    return "🥉 Бронзовая"


def _rarity_short(rating: int, version: str) -> str:
    v = version.upper()
    if v in SPECIAL_VERSIONS:  return "🌟"
    if rating >= 95:            return "🔮"
    if rating >= 92:            return "💎"
    if rating >= 88:            return "🥇"
    if rating >= 85:            return "🥈"
    return "🥉"


def _pos_icon(pos: str) -> str:
    p = pos.upper()
    if p == "GK":                                          return "🧤"
    if p in ("CB", "LB", "RB", "LWB", "RWB"):             return "🛡"
    if p in ("CDM", "CM", "CAM", "LM", "RM"):             return "⚙️"
    if p in ("LW", "RW", "LF", "RF", "CF", "ST", "SS"):   return "⚽"
    return "🎽"


def _stat_bar(value: int) -> str:
    filled = max(0, min(8, round(value / 100 * 8)))
    return "▓" * filled + "░" * (8 - filled)


def _chem_bar(chem: int) -> str:
    filled = max(0, min(10, round(chem / 100 * 10)))
    return "█" * filled + "░" * (10 - filled)


def _sell_price(rating: int, version: str) -> int:
    if rating >= 95:   base = 6_000
    elif rating >= 92: base = 2_500
    elif rating >= 88: base = 800
    elif rating >= 85: base = 300
    else:              base = 100
    if version.upper() in SPECIAL_VERSIONS:
        base *= 2
    return base


def _sort_label(sort: str) -> str:
    return {"od": "OVR ↓", "oa": "OVR ↑", "pos": "Позиция"}.get(sort, "OVR ↓")


def _short_name(name: str, max_len: int = 9) -> str:
    """Фамилия (последнее слово), не длиннее max_len."""
    parts = name.split()
    return (parts[-1] if parts else name)[:max_len]


def _excitement(cards: list[dict]) -> str:
    max_r = max(c["rating"] for c in cards)
    vers  = {c.get("version", "").upper() for c in cards}
    if bool(vers & {"TOTY", "TOTS"}) or max_r >= 96: return _LVL_LEGENDARY
    if bool(vers & SPECIAL_VERSIONS)  or max_r >= 94: return _LVL_EPIC
    if max_r >= 92:                                    return _LVL_RARE
    return _LVL_NORMAL


# ══════════════════════════════════════════════════════════════════════════════
#  ВЗВЕШЕННАЯ ВЫБОРКА
# ══════════════════════════════════════════════════════════════════════════════

def _weighted_sample(pool: list[dict], n: int) -> list[dict]:
    if not pool:
        return []
    available = list(pool)
    weights: list[float] = []
    for p in available:
        base = RATING_WEIGHTS.get(p["rating"], 5.0)
        if p.get("version", "").upper() in SPECIAL_VERSIONS:
            base *= SPECIAL_MULT
        weights.append(base)

    result: list[dict] = []
    for _ in range(min(n, len(available))):
        total = sum(weights)
        r = random.uniform(0, total)
        cumul, idx = 0.0, len(available) - 1
        for i, w in enumerate(weights):
            cumul += w
            if r <= cumul:
                idx = i
                break
        result.append(available[idx])
        available.pop(idx)
        weights.pop(idx)
    return result


# Женские лиги — исключаем из всех пулов карточек
_FEMALE_LEAGUE_KEYWORDS = ("women", "frauen", "féminin", "feminin", "damen", "mujer", "damall")

def _is_male_player(p: dict) -> bool:
    """Return True if the player is NOT from a female league."""
    league = (p.get("league") or "").lower()
    return not any(kw in league for kw in _FEMALE_LEAGUE_KEYWORDS)


def _draw_players(min_r: int, max_r: int, n: int) -> list[dict]:
    res = (
        db.get_client()
        .table("fut_players")
        .select("id, name, club, nation, position, rating, version, pac, sho, pas, dri, def, phy, league")
        .gte("rating", min_r).lte("rating", max_r)
        .execute()
    )
    pool = [p for p in (res.data or []) if _is_male_player(p)]
    return _weighted_sample(pool, n)


# ══════════════════════════════════════════════════════════════════════════════
#  DB — КЛУБ
# ══════════════════════════════════════════════════════════════════════════════

def _get_club_all(user_id: int) -> list[dict]:
    res = (
        db.get_client()
        .table("user_club")
        .select(
            "id, acquired_at, "
            "fut_players(id, name, club, nation, position, rating, version, pac, sho, pas, dri, def, phy)"
        )
        .eq("user_id", user_id)
        .execute()
    )
    cards = []
    for row in (res.data or []):
        p = row.get("fut_players") or {}
        cards.append({
            "club_id":  row["id"],
            "acquired": row.get("acquired_at", ""),
            "name":     p.get("name", "?"),
            "club":     p.get("club", "?"),
            "nation":   p.get("nation", "?"),
            "position": p.get("position", "?"),
            "rating":   p.get("rating", 0),
            "version":  p.get("version", ""),
            "pac": p.get("pac", 0), "sho": p.get("sho", 0),
            "pas": p.get("pas", 0), "dri": p.get("dri", 0),
            "def": p.get("def", 0), "phy": p.get("phy", 0),
        })
    return cards


def _sort_cards(cards: list[dict], sort: str) -> list[dict]:
    if sort == "oa":
        return sorted(cards, key=lambda c: c["rating"])
    if sort == "pos":
        return sorted(cards, key=lambda c: (_POS_ORDER.get(c["position"].upper(), 5), -c["rating"]))
    return sorted(cards, key=lambda c: -c["rating"])


def _get_card_by_id(club_id: int) -> dict | None:
    res = (
        db.get_client()
        .table("user_club")
        .select("id, fut_players(id, name, club, nation, position, rating, version, pac, sho, pas, dri, def, phy)")
        .eq("id", club_id)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    p = row.get("fut_players") or {}
    return {
        "club_id":  row["id"],
        "name":     p.get("name", "?"),
        "club":     p.get("club", "?"),
        "nation":   p.get("nation", "?"),
        "position": p.get("position", "?"),
        "rating":   p.get("rating", 0),
        "version":  p.get("version", ""),
        "pac": p.get("pac", 0), "sho": p.get("sho", 0),
        "pas": p.get("pas", 0), "dri": p.get("dri", 0),
        "def": p.get("def", 0), "phy": p.get("phy", 0),
    }


def _add_to_club(user_id: int, player_ids: list[int]) -> None:
    rows = [{"user_id": user_id, "player_id": pid} for pid in player_ids]
    db.get_client().table("user_club").insert(rows).execute()


def _delete_from_club(club_id: int) -> None:
    db.get_client().table("user_club").delete().eq("id", club_id).execute()


def _sell_duplicates(user_id: int) -> tuple[int, int]:
    res = (
        db.get_client()
        .table("user_club")
        .select("id, player_id")
        .eq("user_id", user_id)
        .order("acquired_at")
        .execute()
    )
    seen: set[int] = set()
    to_delete: list[int] = []
    for row in (res.data or []):
        pid = row["player_id"]
        if pid in seen:
            to_delete.append(row["id"])
        else:
            seen.add(pid)
    if not to_delete:
        return 0, 0
    # BUG-29: batch DELETE instead of N+1 individual calls
    db.get_client().table("user_club").delete().in_("id", to_delete).execute()
    earned = len(to_delete) * 50
    db.add_coins(user_id, earned)
    return len(to_delete), earned


# ══════════════════════════════════════════════════════════════════════════════
#  DB — КОМАНДА
# ══════════════════════════════════════════════════════════════════════════════

def _get_team(user_id: int) -> dict | None:
    res = (
        db.get_client()
        .table("fut_team")
        .select("formation, slots")
        .eq("user_id", user_id)
        .execute()
    )
    return res.data[0] if res.data else None


def _save_team(user_id: int, formation: str, slots: dict) -> None:
    db.get_client().table("fut_team").upsert(
        {"user_id": user_id, "formation": formation, "slots": slots},
        on_conflict="user_id",
    ).execute()


# ══════════════════════════════════════════════════════════════════════════════
#  РАСЧЁТ КОМАНДЫ
# ══════════════════════════════════════════════════════════════════════════════

def _team_ovr(cards: list[dict]) -> int:
    if not cards:
        return 0
    return round(sum(c["rating"] for c in cards) / len(cards))


def _team_chemistry(cards: list[dict]) -> int:
    """Химия 0–100: бонус за совпадение нации (+1) и клуба (+2) с каждым соседом."""
    if len(cards) < 2:
        return 0
    total = 0
    for i, c in enumerate(cards):
        nat_links  = sum(1 for j, o in enumerate(cards) if j != i and o["nation"] == c["nation"])
        club_links = sum(1 for j, o in enumerate(cards) if j != i and o["club"]   == c["club"])
        total += min(10, nat_links + club_links * 2)
    return round(total / (len(cards) * 10) * 100)


# ══════════════════════════════════════════════════════════════════════════════
#  ФОРМАТИРОВАНИЕ КАРТОЧЕК
# ══════════════════════════════════════════════════════════════════════════════

def _card_detail_text(p: dict) -> str:
    rar = _rarity(p["rating"], p.get("version", ""))
    v   = p.get("version", "").upper()
    ver_line = f"  _✦ {p['version']}_\n" if v in SPECIAL_VERSIONS else ""
    return (
        f"{rar}   OVR *{p['rating']}*\n"
        f"{ver_line}\n"
        f"{_pos_icon(p['position'])}  *{p['name'].upper()}*\n"
        f"`{p['position']}`  •  {_flag(p['nation'])} {p['nation']}  •  {p['club']}\n\n"
        f"📊 *Характеристики*\n"
        f"`PAC` *{p['pac']:>2}*  {_stat_bar(p['pac'])}\n"
        f"`SHO` *{p['sho']:>2}*  {_stat_bar(p['sho'])}\n"
        f"`PAS` *{p['pas']:>2}*  {_stat_bar(p['pas'])}\n"
        f"`DRI` *{p['dri']:>2}*  {_stat_bar(p['dri'])}\n"
        f"`DEF` *{p['def']:>2}*  {_stat_bar(p['def'])}\n"
        f"`PHY` *{p['phy']:>2}*  {_stat_bar(p['phy'])}\n"
    )


def _pack_result_text(pack_name: str, cards: list[dict], cost: int, new_bal: int) -> str:
    level = _excitement(cards)
    if level == _LVL_LEGENDARY:
        header = f"🏆 *ЛЕГЕНДАРНЫЙ ПАК!* 🏆\n_{pack_name}_\n"
    elif level == _LVL_EPIC:
        header = f"🔥 *ЭПИЧЕСКИЙ ПАК!* 🔥\n_{pack_name}_\n"
    elif level == _LVL_RARE:
        header = f"💎 *{pack_name}*\n"
    else:
        header = f"📦 *{pack_name}*\n"

    lines = [header]
    for i, p in enumerate(cards, 1):
        icon = _pos_icon(p["position"])
        rar  = _rarity(p["rating"], p.get("version", ""))
        v    = p.get("version", "").upper()
        if v in SPECIAL_VERSIONS or p["rating"] >= 95:
            lines.append(f"⭐⭐⭐ {icon} *{p['name']}*   {rar}   OVR *{p['rating']}* ⭐⭐⭐")
        elif p["rating"] >= 92:
            lines.append(f"✨ {icon} *{p['name']}*   {rar}   OVR *{p['rating']}*")
        else:
            lines.append(f"{i}. {icon} *{p['name']}*   {rar}   OVR *{p['rating']}*")
        lines.append(f"    {p['nation']} • {p['club']} • {p['position']}")

    lines.append(f"\n💸 Потрачено: *{_fmt(cost)} 💰*")
    lines.append(f"💼 Баланс: *{_fmt(new_bal)} 💰*")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  АНИМАЦИЯ ОТКРЫТИЯ ПАКА
# ══════════════════════════════════════════════════════════════════════════════

async def _animate_open(query, pack_name: str, cards: list[dict], cost: int, new_bal: int) -> None:
    level = _excitement(cards)
    slots = "🎴 " * len(cards)

    await query.edit_message_text(
        f"📦 *{pack_name}*\n\n{slots}\n_Перемешиваем колоду..._", parse_mode="Markdown")
    await asyncio.sleep(1.2)

    await query.edit_message_text(
        f"📦 *{pack_name}*\n\n✨ ✨ ✨\n_Тянем карточки..._", parse_mode="Markdown")
    await asyncio.sleep(1.2)

    if level == _LVL_LEGENDARY:
        await query.edit_message_text(
            "🌟 *ЧТО-ТО НЕВЕРОЯТНОЕ!* 🌟\n\n⚡ ⚡ ⚡ ⚡ ⚡\n_Это должно быть..._",
            parse_mode="Markdown")
        await asyncio.sleep(1.4)
        await query.edit_message_text(
            "🏆 *Л Е Г Е Н Д А* 🏆\n\n🔱 🔱 🔱 🔱 🔱\n_Открываем..._",
            parse_mode="Markdown")
        await asyncio.sleep(1.4)
    elif level == _LVL_EPIC:
        await query.edit_message_text(
            "🔥 *РЕДЧАЙШАЯ КАРТА ЗАМЕЧЕНА!* 🔥\n\n💎 💎 💎 💎\n_Открываем..._",
            parse_mode="Markdown")
        await asyncio.sleep(1.4)
    elif level == _LVL_RARE:
        await query.edit_message_text(
            "💎 *ОЙ, ЧТО ЭТО?* 💎\n\n✨ ✨ ✨ ✨\n_Почти..._",
            parse_mode="Markdown")
        await asyncio.sleep(1.1)

    await query.edit_message_text(
        _pack_result_text(pack_name, cards, cost, new_bal),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Ещё пак",  callback_data="fut_packs"),
             InlineKeyboardButton("🏟 Мой клуб", callback_data="fut_club_0_od")],
            [InlineKeyboardButton("◀ FUT меню",  callback_data="fut_menu")],
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  КЛАВИАТУРА ПОЛЯ (КОМАНДА)
# ══════════════════════════════════════════════════════════════════════════════

def _build_team_kb(form_key: str, slots: dict, card_map: dict[int, dict]) -> InlineKeyboardMarkup:
    """Поле как клавиатура: каждая позиция — кнопка.
    Заполненный слот: иконка + фамилия + OVR.
    Пустой слот: иконка группы + обозначение позиции.
    """
    form = FORMATIONS[form_key]
    kb: list[list[InlineKeyboardButton]] = []

    for row in form["rows"]:
        kb_row = []
        for slot in row:
            club_id = slots.get(slot)
            cid_int = int(club_id) if club_id is not None else None
            card    = card_map.get(cid_int) if cid_int is not None else None
            if card:
                label = f"{_pos_icon(card['position'])} {_short_name(card['name'])} {card['rating']}"
            else:
                grp   = form["slots"][slot]
                label = f"{GROUP_ICON.get(grp, '❓')} {SLOT_LABEL.get(slot, slot)}"
            kb_row.append(InlineKeyboardButton(
                label, callback_data=f"fut_team_slot_{slot}_0"
            ))
        kb.append(kb_row)

    kb.append([
        InlineKeyboardButton("🔄 Схема",   callback_data="fut_team_form"),
        InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu"),
    ])
    return InlineKeyboardMarkup(kb)


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS — МЕНЮ И ПАКИ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)
    res   = db.get_client().table("user_club").select("id", count="exact").eq("user_id", uid).execute()
    total = res.count or 0

    await q.edit_message_text(
        "⚽ *FUT КЛУБ*\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n"
        f"🃏 Карточек в клубе: *{total}*\n\n"
        "Открывай паки, собирай игроков и строй свою команду!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Открыть пак", callback_data="fut_packs"),
             InlineKeyboardButton("🏟 Мой клуб",    callback_data="fut_club_0_od")],
            [InlineKeyboardButton("🧩 Команда",     callback_data="fut_team"),
             InlineKeyboardButton("⚔️ Матчи",       callback_data="fut_match")],
            [InlineKeyboardButton("🛒 Рынок",       callback_data="fut_market"),
             InlineKeyboardButton("🎲 Драфт",       callback_data="fut_draft")],
            [InlineKeyboardButton("◀ В меню",       callback_data="menu_back")],
        ]),
    )


async def cb_fut_packs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)

    rows = []
    for key, pack in PACKS.items():
        can = coins >= pack["cost"]
        lbl = f"{'✅' if can else '🚫'} {pack['name']} — {_fmt(pack['cost'])} 💰"
        rows.append([InlineKeyboardButton(lbl, callback_data=f"fut_buy_{key}" if can else "fut_no_coins")])
    rows.append([InlineKeyboardButton("◀ Назад", callback_data="fut_menu")])

    pack_list = "\n".join(
        f"*{p['name']}* — {_fmt(p['cost'])} 💰\n  _{p['desc']}_"
        for p in PACKS.values()
    )
    await q.edit_message_text(
        f"📦 *ПАКИ*\n\n{pack_list}\n\n💰 Твой баланс: *{_fmt(coins)}* монет",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_no_coins(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("Недостаточно монет!", show_alert=True)


async def cb_fut_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q        = update.callback_query
    uid      = q.from_user.id
    pack_key = q.data[len("fut_buy_"):]

    pack = PACKS.get(pack_key)
    if not pack:
        await q.answer("Неизвестный пак.", show_alert=True); return

    ok, _ = db.spend_coins(uid, pack["cost"])
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return

    await q.answer()

    cards: list[dict] = []
    guar = pack.get("guaranteed")
    if guar:
        hi = _draw_players(guar, pack["max_rating"], 1)
        if hi:
            cards.extend(hi)
        cards.extend(_draw_players(pack["min_rating"], pack["max_rating"], pack["cards"] - len(cards)))
    else:
        cards = _draw_players(pack["min_rating"], pack["max_rating"], pack["cards"])

    if not cards:
        db.add_coins(uid, pack["cost"])
        await q.edit_message_text(
            "❌ Не удалось найти игроков в базе. Монеты возвращены.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ Паки", callback_data="fut_packs")]]),
        )
        return

    _add_to_club(uid, [c["id"] for c in cards])
    new_bal = db.get_coins(uid)
    await _animate_open(q, pack["name"], cards, pack["cost"], new_bal)


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS — МОЙ КЛУБ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_club_{offset}_{sort}"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    tail   = q.data[len("fut_club_"):]
    parts  = tail.split("_")
    offset = int(parts[0])
    sort   = parts[1] if len(parts) > 1 else "od"

    all_cards = _sort_cards(_get_club_all(uid), sort)
    total     = len(all_cards)

    if total == 0:
        await q.edit_message_text(
            "🏟 *МОЙ КЛУБ*\n\nУ тебя пока нет карточек.\nОткрой пак — и они появятся здесь!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Открыть пак", callback_data="fut_packs")],
                [InlineKeyboardButton("◀ FUT меню",     callback_data="fut_menu")],
            ]),
        )
        return

    offset     = max(0, min(offset, ((total - 1) // CLUB_PAGE_SIZE) * CLUB_PAGE_SIZE))
    page_cards = all_cards[offset: offset + CLUB_PAGE_SIZE]
    pages      = (total + CLUB_PAGE_SIZE - 1) // CLUB_PAGE_SIZE
    cur_page   = offset // CLUB_PAGE_SIZE + 1

    card_buttons = []
    for c in page_cards:
        icon  = _pos_icon(c["position"])
        rstar = _rarity_short(c["rating"], c["version"])
        label = f"{icon} {c['name'][:18]}  {rstar} {c['rating']}"
        card_buttons.append([
            InlineKeyboardButton(label, callback_data=f"fut_card_{c['club_id']}_{offset}_{sort}")
        ])

    sort_row = [
        InlineKeyboardButton(f"{'▶ ' if sort == 'od'  else ''}OVR↓",    callback_data=f"fut_club_{offset}_od"),
        InlineKeyboardButton(f"{'▶ ' if sort == 'oa'  else ''}OVR↑",    callback_data=f"fut_club_{offset}_oa"),
        InlineKeyboardButton(f"{'▶ ' if sort == 'pos' else ''}Позиция", callback_data=f"fut_club_{offset}_pos"),
    ]

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_club_{offset - CLUB_PAGE_SIZE}_{sort}"))
    if offset + CLUB_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_club_{offset + CLUB_PAGE_SIZE}_{sort}"))

    kb = card_buttons + [sort_row]
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🗑 Продать дубликаты", callback_data="fut_sell_dupes")])
    kb.append([
        InlineKeyboardButton("📦 Паки",    callback_data="fut_packs"),
        InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu"),
    ])

    await q.edit_message_text(
        f"🏟 *МОЙ КЛУБ*  _стр. {cur_page}/{pages}_  •  Всего: *{total}*\n"
        f"_Сортировка: {_sort_label(sort)}_\n\n"
        "Нажми на карточку, чтобы увидеть подробности:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_card_{club_id}_{offset}_{sort}"""
    q   = update.callback_query
    await q.answer()

    tail    = q.data[len("fut_card_"):]
    parts   = tail.split("_")
    club_id = int(parts[0])
    offset  = int(parts[1]) if len(parts) > 1 else 0
    sort    = parts[2]       if len(parts) > 2 else "od"

    card = _get_card_by_id(club_id)
    if not card:
        await q.answer("Карточка не найдена.", show_alert=True); return

    price = _sell_price(card["rating"], card["version"])

    await q.edit_message_text(
        _card_detail_text(card),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"💰 Продать за {_fmt(price)} монет",
                callback_data=f"fut_sell_confirm_{club_id}_{offset}_{sort}",
            )],
            [InlineKeyboardButton("◀ Назад в клуб", callback_data=f"fut_club_{offset}_{sort}")],
        ]),
    )


async def cb_fut_sell_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_sell_confirm_{club_id}_{offset}_{sort} — выполнить продажу."""
    q   = update.callback_query
    uid = q.from_user.id

    tail    = q.data[len("fut_sell_confirm_"):]
    parts   = tail.split("_")
    club_id = int(parts[0])
    offset  = int(parts[1]) if len(parts) > 1 else 0
    sort    = parts[2]       if len(parts) > 2 else "od"

    card = _get_card_by_id(club_id)
    if not card:
        await q.answer("Карточка не найдена.", show_alert=True); return

    price = _sell_price(card["rating"], card["version"])
    _delete_from_club(club_id)
    db.add_coins(uid, price)

    await q.answer(f"✅ Продано! +{_fmt(price)} 💰")
    q.data = f"fut_club_{offset}_{sort}"
    await cb_fut_club(update, ctx)


async def cb_fut_sell_dupes(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id

    sold, earned = _sell_duplicates(uid)
    if sold == 0:
        await q.answer("Дубликатов нет — все игроки уникальны!", show_alert=True); return

    await q.answer(f"🗑 Продано {sold} дублей • +{_fmt(earned)} 💰")
    q.data = "fut_club_0_od"
    await cb_fut_club(update, ctx)


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS — КОМАНДА
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_team(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass   # уже отвечено вызывающим хендлером
    uid = q.from_user.id

    team = _get_team(uid)
    if not team:
        # Нет команды — сразу выбор схемы в 2 столбца
        items = [
            InlineKeyboardButton(f["label"], callback_data=f"fut_team_setform_{key}")
            for key, f in FORMATIONS.items()
        ]
        rows = [items[i:i+2] for i in range(0, len(items), 2)]
        rows.append([InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")])
        await q.edit_message_text(
            "🧩 *СБОРКА КОМАНДЫ*\n\nУ тебя ещё нет команды.\nВыбери схему расстановки:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    form_key = team["formation"]
    slots    = team.get("slots") or {}
    form     = FORMATIONS.get(form_key, FORMATIONS["433"])

    # Загружаем карточки из слотов
    club_ids = [int(v) for v in slots.values() if v is not None]
    card_map: dict[int, dict] = {}
    for cid in club_ids:
        c = _get_card_by_id(cid)
        if c:
            card_map[cid] = c

    filled   = list(card_map.values())
    ovr      = _team_ovr(filled)
    chem     = _team_chemistry(filled)
    filled_n = len(filled)
    total_n  = len(form["slots"])

    ovr_str  = f"*{ovr}*" if filled_n > 0 else "—"
    chem_str = f"*{chem}*  {_chem_bar(chem)}" if filled_n > 1 else "—"

    await q.edit_message_text(
        f"🧩 *МОЯ КОМАНДА*  •  _{form['label']}_\n\n"
        f"👥 Состав: *{filled_n}/{total_n}*\n"
        f"⭐ OVR команды: {ovr_str}\n"
        f"🔗 Химия: {chem_str}\n\n"
        "_Нажми на позицию, чтобы выбрать игрока:_",
        parse_mode="Markdown",
        reply_markup=_build_team_kb(form_key, slots, card_map),
    )


async def cb_fut_team_form(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    # Показываем схемы в два столбца
    items = [
        InlineKeyboardButton(f["label"], callback_data=f"fut_team_setform_{key}")
        for key, f in FORMATIONS.items()
    ]
    rows = [items[i:i+2] for i in range(0, len(items), 2)]
    rows.append([InlineKeyboardButton("◀ Назад", callback_data="fut_team")])

    await q.edit_message_text(
        "🔄 *СХЕМА РАССТАНОВКИ*\n\nВыбери схему:\n_Текущий состав будет сброшен_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_team_setform(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q        = update.callback_query
    uid      = q.from_user.id
    form_key = q.data[len("fut_team_setform_"):]

    if form_key not in FORMATIONS:
        await q.answer("Неизвестная схема.", show_alert=True); return

    _save_team(uid, form_key, {})
    await q.answer(f"Схема {FORMATIONS[form_key]['label']} выбрана!")
    q.data = "fut_team"
    await cb_fut_team(update, ctx)


async def cb_fut_team_slot(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор игрока для позиции. fut_team_slot_{slot}_{page}"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    tail = q.data[len("fut_team_slot_"):]
    slot = tail.rsplit("_", 1)[0]
    page = int(tail.rsplit("_", 1)[1])

    team = _get_team(uid)
    if not team:
        await q.answer("Сначала создай команду.", show_alert=True); return

    form  = FORMATIONS.get(team["formation"], FORMATIONS["433"])
    grp   = form["slots"].get(slot)
    if not grp:
        await q.answer("Неизвестная позиция.", show_alert=True); return

    slots = team.get("slots") or {}

    # Кто сейчас стоит на этом слоте (если есть)
    current_club_id = slots.get(slot)
    current_card    = _get_card_by_id(int(current_club_id)) if current_club_id else None

    # Игроки уже занятые в ДРУГИХ слотах — их нельзя выбрать повторно
    already_assigned = {
        int(v) for k, v in slots.items()
        if k != slot and v is not None
    }

    all_cards  = _sort_cards(_get_club_all(uid), "od")
    compatible = [
        c for c in all_cards
        if grp in POSITION_CAN_PLAY.get(c["position"].upper(), [])
        and c["club_id"] not in already_assigned
    ]
    total  = len(compatible)
    offset = page * TEAM_PAGE_SIZE

    if total == 0:
        kb = []
        if current_card:
            kb.append([InlineKeyboardButton(
                f"❌ Снять {_short_name(current_card['name'])}",
                callback_data=f"fut_team_remove_{slot}",
            )])
        kb += [
            [InlineKeyboardButton("📦 Паки",   callback_data="fut_packs")],
            [InlineKeyboardButton("◀ Команда", callback_data="fut_team")],
        ]
        await q.edit_message_text(
            f"❌ Нет доступных игроков для *{SLOT_LABEL.get(slot, slot)}*.\n\n"
            "_Все подходящие уже в составе, или их нет в клубе._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    page_cards = compatible[offset: offset + TEAM_PAGE_SIZE]
    pages      = (total + TEAM_PAGE_SIZE - 1) // TEAM_PAGE_SIZE

    # Заголовок — показываем текущего игрока если слот занят
    if current_card:
        rar_cur = _rarity_short(current_card["rating"], current_card["version"])
        header = (
            f"👤 *{SLOT_LABEL.get(slot, slot)}* — {GROUP_NAME.get(grp, grp)}\n"
            f"Сейчас: {_pos_icon(current_card['position'])} "
            f"*{current_card['name']}*  {rar_cur} {current_card['rating']}\n"
            f"_Стр. {page + 1}/{pages} • Доступных: {total}_\n\n"
            "Выбери замену:"
        )
    else:
        header = (
            f"👤 *{SLOT_LABEL.get(slot, slot)}* — {GROUP_NAME.get(grp, grp)}\n"
            f"_Стр. {page + 1}/{pages} • Доступных: {total}_\n\n"
            "Выбери игрока:"
        )

    card_btns = []
    # Кнопка «снять игрока» первой, если слот занят
    if current_card:
        card_btns.append([InlineKeyboardButton(
            f"❌ Снять {_short_name(current_card['name'])}",
            callback_data=f"fut_team_remove_{slot}",
        )])
    for c in page_cards:
        rar = _rarity_short(c["rating"], c["version"])
        lbl = f"{_pos_icon(c['position'])} {c['name'][:15]}  {_flag(c['nation'])}  {rar}{c['rating']}"
        card_btns.append([
            InlineKeyboardButton(lbl, callback_data=f"fut_team_pick_{slot}_{c['club_id']}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_team_slot_{slot}_{page - 1}"))
    if offset + TEAM_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_team_slot_{slot}_{page + 1}"))

    kb = card_btns
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Поле", callback_data="fut_team")])

    await q.edit_message_text(
        header,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_team_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Снять игрока с позиции. fut_team_remove_{slot}"""
    q   = update.callback_query
    uid = q.from_user.id
    slot = q.data[len("fut_team_remove_"):]

    team = _get_team(uid)
    if not team:
        await q.answer("Команда не найдена.", show_alert=True); return

    slots = dict(team.get("slots") or {})
    if slot in slots:
        del slots[slot]
        _save_team(uid, team["formation"], slots)

    await q.answer("Игрок снят с позиции")
    q.data = "fut_team"
    await cb_fut_team(update, ctx)


async def cb_fut_team_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Назначить игрока на позицию. fut_team_pick_{slot}_{club_id}"""
    q   = update.callback_query
    uid = q.from_user.id

    tail    = q.data[len("fut_team_pick_"):]
    slot    = tail.rsplit("_", 1)[0]
    club_id = int(tail.rsplit("_", 1)[1])

    team = _get_team(uid)
    if not team:
        await q.answer("Сначала создай команду.", show_alert=True); return

    slots = dict(team.get("slots") or {})

    # Проверка: этот игрок уже стоит на другой позиции?
    already_assigned = {int(v) for k, v in slots.items() if k != slot and v is not None}
    if club_id in already_assigned:
        await q.answer("❌ Этот игрок уже стоит на другой позиции!", show_alert=True)
        return

    slots[slot] = club_id
    _save_team(uid, team["formation"], slots)

    card = _get_card_by_id(club_id)
    name = card["name"] if card else "?"
    await q.answer(f"✅ {name} → {SLOT_LABEL.get(slot, slot)}")

    q.data = "fut_team"
    await cb_fut_team(update, ctx)


# ══════════════════════════════════════════════════════════════════════════════
#  МАТЧИ — КОНСТАНТЫ И DB
# ══════════════════════════════════════════════════════════════════════════════

MATCH_K_FACTOR       = 40
MATCH_K_CALIBRATION  = 80   # первые 5 матчей — быстрое размещение
MATCH_CALIB_GAMES    = 5
MATCH_MIN_PLACED     = 5    # минимум расставленных игроков для матча

# Интерактивные моменты: выбор игрока (polling-подход, без asyncio.Event)
# uid → строка выбора (или None = ожидаем)
_interaction_choices: dict[int, str | None] = {}


class _MatchMoment:
    """Координирует выбор двух игроков в один интерактивный момент (polling)."""
    def __init__(self, moment_type: str, attacker_uid: int, keeper_uid: int):
        self.type         = moment_type
        self.attacker_uid = attacker_uid
        self.keeper_uid   = keeper_uid
        self.att_choice: str | None = None
        self.kpr_choice: str | None = None

    def submit(self, uid: int, choice: str) -> None:
        if uid == self.attacker_uid:
            self.att_choice = choice
        else:
            self.kpr_choice = choice

    def is_ready(self) -> bool:
        return self.att_choice is not None and self.kpr_choice is not None

    async def wait_result(self, timeout: float = 35.0) -> dict:
        """Ждём пока оба сделают выбор. Авто-заполняем при таймауте."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if self.is_ready():
                break
            await asyncio.sleep(0.3)
        if not self.att_choice:
            self.att_choice = random.choice(["left", "center", "right"])
        if not self.kpr_choice:
            self.kpr_choice = random.choice(["left", "center", "right"])
        return {"att": self.att_choice, "kpr": self.kpr_choice}

_match_moments: dict[str, "_MatchMoment"] = {}


def _get_fut_rating(user_id: int) -> int:
    u = db.get_user(user_id)
    return (u or {}).get("fut_rating", 0) or 0


def _get_fut_games(user_id: int) -> int:
    u = db.get_user(user_id)
    return (u or {}).get("fut_games_played", 0) or 0


def _set_fut_rating(user_id: int, new_rating: int) -> None:
    db.get_client().table("users").update(
        {"fut_rating": max(0, new_rating)}
    ).eq("user_id", user_id).execute()


def _increment_fut_games(user_id: int) -> None:
    u = db.get_user(user_id)
    played = ((u or {}).get("fut_games_played") or 0) + 1
    db.get_client().table("users").update({"fut_games_played": played}).eq("user_id", user_id).execute()


def _save_fut_match(p1: int, p2: int, s1: int, s2: int,
                    r1b: int, r2b: int, r1c: int, r2c: int) -> None:
    db.get_client().table("fut_matches").insert({
        "player1_id": p1, "player2_id": p2,
        "score1": s1, "score2": s2,
        "r1_before": r1b, "r2_before": r2b,
        "r1_change": r1c, "r2_change": r2c,
    }).execute()


def _get_opponents(my_uid: int) -> list[dict]:
    """Пользователи у которых есть команда (кроме себя), отсортированные по fut_rating."""
    teams = db.get_client().table("fut_team").select("user_id, slots").execute().data or []
    eligible = []
    for t in teams:
        uid = t["user_id"]
        if uid == my_uid:
            continue
        slots = t.get("slots") or {}
        placed = sum(1 for v in slots.values() if v is not None)
        if placed < MATCH_MIN_PLACED:
            continue
        u = db.get_user(uid)
        if not u:
            continue
        eligible.append({
            "user_id":    uid,
            "name":       u.get("display_name") or u.get("username") or f"User{uid}",
            "username":   u.get("username") or "",
            "fut_rating": (u.get("fut_rating") or 0),
            "fut_games":  (u.get("fut_games_played") or 0),
            "placed":     placed,
        })
    return sorted(eligible, key=lambda x: -x["fut_rating"])


def _get_match_history(user_id: int, limit: int = 5) -> list[dict]:
    res = (
        db.get_client()
        .table("fut_matches")
        .select("*")
        .or_(f"player1_id.eq.{user_id},player2_id.eq.{user_id}")
        .order("played_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ══════════════════════════════════════════════════════════════════════════════
#  МАТЧИ — РАСЧЁТ И СИМУЛЯЦИЯ
# ══════════════════════════════════════════════════════════════════════════════

def _team_cards_placed(user_id: int) -> list[dict]:
    """Карточки только расставленных в команде позиций."""
    team = _get_team(user_id)
    if not team:
        return []
    slots = team.get("slots") or {}
    club_ids = {int(v) for v in slots.values() if v is not None}
    if not club_ids:
        return []
    all_cards = _get_club_all(user_id)
    return [c for c in all_cards if c["club_id"] in club_ids]


def _calc_strength(user_id: int) -> dict:
    """
    Возвращает {att, def_, ovr, chem, placed}.
    att  = средний (PAC+SHO+DRI)/3 для ATT+MID позиций + химия-бонус
    def_ = средний (DEF+PHY)/2    для DEF+GK позиций  + химия-бонус
    """
    team = _get_team(user_id)
    if not team:
        return {"att": 70, "def_": 70, "ovr": 70, "chem": 0, "placed": 0}

    formation = team.get("formation", "433")
    form = FORMATIONS.get(formation, FORMATIONS["433"])
    slots = team.get("slots") or {}
    all_cards = _get_club_all(user_id)
    by_id = {c["club_id"]: c for c in all_cards}

    att_vals, def_vals, gk_vals = [], [], []
    placed_cards = []

    for slot_name, group in form["slots"].items():
        club_id = slots.get(slot_name)
        if club_id is None:
            continue
        card = by_id.get(int(club_id))
        if card is None:
            continue
        placed_cards.append(card)
        if group in ("ATT", "MID"):
            att_vals.append((card["pac"] + card["sho"] + card["dri"]) / 3)
        if group in ("DEF", "MID"):
            def_vals.append((card["def"] + card["phy"]) / 2)
        if group == "GK":
            gk_vals.append((card["def"] + card["phy"] + card["pas"]) / 3)

    chem = _team_chemistry(placed_cards)
    bonus = 1 + (chem / 100) * 0.12  # до +12% за 100% химию

    att  = round((sum(att_vals) / max(len(att_vals), 1)) * bonus) if att_vals else 70
    def_ = round(((sum(def_vals) / max(len(def_vals), 1)) * 0.7 +
                  (sum(gk_vals)  / max(len(gk_vals),  1)) * 0.3) * bonus) if def_vals or gk_vals else 70
    ovr  = _team_ovr(placed_cards)

    # Дополнительные данные для комментария
    scorers = []
    all_players_short = []
    gk_name = "Вратарь"
    pas_sum = 0

    for slot_name, group in form["slots"].items():
        club_id2 = slots.get(slot_name)
        if club_id2 is None:
            continue
        card2 = by_id.get(int(club_id2))
        if card2 is None:
            continue
        short = _short_name(card2["name"])
        all_players_short.append(short)
        pas_sum += card2.get("pas", 75)
        if group in ("ATT", "MID"):
            scorers.append(short)
        if group == "GK":
            gk_name = short

    pas_avg = round(pas_sum / max(len(placed_cards), 1))

    return {
        "att": att, "def_": def_, "ovr": ovr, "chem": chem,
        "placed": len(placed_cards),
        "scorers":    scorers or all_players_short or ["Игрок"],
        "all_names":  all_players_short or ["Игрок"],
        "gk_name":    gk_name,
        "pas_avg":    pas_avg,
    }


# ── Комментарий ────────────────────────────────────────────────────────────────

_SAVES    = ["Сейв!", "Вратарь тянет!", "В перекладину!", "Не пройти!", "Отличный блок!"]
_MISSES   = ["Выше ворот!", "Мимо!", "Штанга!", "Какой момент упущен!", "Чуть не хватило!"]
_PRESSURE = ["Давление продолжается", "Острая атака", "Опасный момент", "Навес в штрафную"]
_DANGER   = ["Острый момент!", "Один на один с вратарём!", "Выход на ворота!"]

# ── Пулы фраз для комментатора (A) ────────────────────────────────────────────

_COMM_KICKOFF = [
    "Судья даёт свисток — и игра пошла!",
    "Первый пас сделан — матч стартовал!",
    "Стадион приветствует выход команд!",
    "Оба тренера отдали все установки — осталось только играть!",
    "Трибуны полны, атмосфера накалена — начинаем!",
    "Добро пожаловать в прямой эфир — матч начался!",
]

_COMM_EARLY = [
    "Обе команды осторожничают в начале встречи.",
    "Первые минуты прошли в равной борьбе.",
    "Никто не хочет рисковать — игра пока разведывательная.",
    "Команды изучают друг друга, нащупывая слабые места.",
    "Мяч летает по центру поля — атаки пока блокируются.",
    "Игра только набирает обороты — терпение!",
    "Первые атаки разбиваются о крепкую оборону.",
    "Плотный прессинг с обеих сторон — идёт борьба за инициативу.",
    "Команды аккуратны в передачах — ошибок стараются не допускать.",
    "Напряжённый старт — обе команды в тонусе.",
]

_COMM_LEADING = [
    "Ведущая команда умело контролирует мяч.",
    "Преимущество позволяет немного сбавить темп.",
    "Команда в лидерах играет уверенно и спокойно.",
    "Соперник вынужден идти вперёд, открывая пространство.",
    "Тактика работает — ведущая команда держит счёт!",
    "Контроль мяча и выжидание — классическая тактика лидера.",
]

_COMM_TRAILING = [
    "Нужен гол — команда прибавляет в интенсивности!",
    "Время поджимает. Атаки следуют одна за другой!",
    "Отчаянный поиск гола — всё поставлено на карту.",
    "Тренер делает ставку на атаку — все вперёд!",
    "Каждая минута без гола — как игла в сердце болельщика.",
    "Надо забивать! Команда бросается в атаку!",
    "Риск оправдан — другого выхода нет!",
]

_COMM_DRAW_LATE = [
    "Счёт равный — всё решится в эти минуты!",
    "Ни одна команда не уступает — великолепный матч!",
    "Напряжение зашкаливает при равном счёте!",
    "Любой момент может стать решающим!",
    "Обе команды хотят только победы — никаких компромиссов!",
    "Одно очко мало для обоих — ищем гол-победитель!",
]

_COMM_HT = [
    "Судья даёт свисток — перерыв.",
    "Команды уходят в раздевалку для разбора полётов.",
    "Тренеры будут работать над тактикой в перерыве.",
    "Напряжённый первый тайм позади.",
    "Болельщики обсуждают увиденное за чашкой кофе.",
    "Пятнадцать минут отдыха — и снова в бой!",
]

_COMM_SECOND_HALF = [
    "Второй тайм — время героев!",
    "Всё только начинается — второй тайм покажет победителя.",
    "Команды вышли с новыми силами.",
    "Тренеры внесли коррективы — посмотрим, помогут ли.",
    "Второй тайм всегда богат на сюрпризы!",
    "Свежие ноги, свежие идеи — поехали!",
]

_COMM_CLIMAX = [
    "🔥 Концовка на пределе нервов!",
    "⏰ Последние минуты — самые важные!",
    "Стадион затаил дыхание!",
    "Сердца болельщиков бьются чаще с каждой минутой!",
    "Каждый удар может стать решающим!",
    "Нервы натянуты как струна — кто выдержит?",
    "Добавленное время покажет, кто настоящий чемпион!",
]


def _simulate_match(sa: dict, sb: dict) -> dict:
    """
    Детальная симуляция матча — 5-минутные блоки (9 в каждом тайме).
    Каждый блок генерирует 0-2 события с реальными именами игроков.
    События с пометкой *(соп)* — голы/моменты соперника (команды B).
    """
    GOAL_BASE = 0.20   # шанс гола за 5 мин при равных
    CARD_PROB = 0.04   # желтая карточка за блок
    PEN_PROB  = 0.04   # пенальти за тайм

    score_a = score_b = 0
    h1_score_a = h1_score_b = 0
    poss_a = poss_b = 0
    shots_a = shots_b = 0
    corners_a = corners_b = 0
    passes_a = passes_b = 0
    acc_a_sum = acc_b_sum = 0.0
    acc_blk_a = acc_blk_b = 0
    yellows_a = yellows_b = 0
    red_a = red_b = False
    eff_a = eff_b = 70.0  # defaults for injury time
    total_eff = 140.0

    events: list[tuple[int, str]] = []

    sc_a = sa.get("scorers", ["Игрок"])
    sc_b = sb.get("scorers", ["Игрок"])
    nm_a = sa.get("all_names", ["Игрок"])
    nm_b = sb.get("all_names", ["Игрок"])

    def _chance(att: float, def_: float, scorers: list, is_penalty: bool,
                minute: int, is_a: bool) -> tuple[str, str] | None:
        nonlocal score_a, score_b, shots_a, shots_b, corners_a, corners_b
        goal_prob = (att / max(att + def_, 1)) * (0.70 if is_penalty else GOAL_BASE * 2)
        r = random.random()
        name = random.choice(scorers)
        side = "" if is_a else " *(соп)*"
        if r < goal_prob:
            if is_a:
                score_a += 1; shots_a += 1
            else:
                score_b += 1; shots_b += 1
            prefix = "🟡→⚽" if is_penalty else "⚽"
            sc_str = f"{score_a}:{score_b}"
            return (f"{prefix} *{minute}'* — *{name}*!  _{sc_str}_{side}", "goal")
        elif r < goal_prob + 0.28:
            if is_a: shots_a += 1
            else:    shots_b += 1
            return (f"🧤 *{minute}'* — {name}: {random.choice(_SAVES)}{side}", "save")
        elif r < goal_prob + 0.50:
            return (f"💨 *{minute}'* — {name}: {random.choice(_MISSES)}{side}", "miss")
        else:
            if is_a: corners_a += 1
            else:    corners_b += 1
            return (f"🚩 *{minute}'* — Угловой{side}", "corner")

    for half in range(2):
        pen_minute_a = (random.randint(half * 45 + 10, half * 45 + 44)
                        if random.random() < PEN_PROB else None)
        pen_minute_b = (random.randint(half * 45 + 10, half * 45 + 44)
                        if random.random() < PEN_PROB else None)

        for blk in range(9):
            minute = half * 45 + (blk + 1) * 5

            if pen_minute_a and abs(minute - pen_minute_a) < 5:
                pen_minute_a = None
                ev = _chance(sa["att"], sb["def_"], sc_a, True, minute, True)
                if ev: events.append((minute, ev[0]))
            if pen_minute_b and abs(minute - pen_minute_b) < 5:
                pen_minute_b = None
                ev = _chance(sb["att"], sa["def_"], sc_b, True, minute, False)
                if ev: events.append((minute, ev[0]))

            eff_a = (sa["att"] + sa["def_"]) * (0.80 if red_a else 1.0)
            eff_b = (sb["att"] + sb["def_"]) * (0.80 if red_b else 1.0)
            total_eff = eff_a + eff_b or 1
            a_has_ball = random.random() < (eff_a / total_eff)

            if a_has_ball:
                poss_a += 5
                p = random.randint(9, 16)
                passes_a += p
                acc = min(0.93, 0.62 + sa.get("pas_avg", 70) / 400)
                acc_a_sum += acc; acc_blk_a += 1
                if random.random() < 0.38:
                    ev = _chance(sa["att"], sb["def_"], sc_a, False, minute, True)
                    if ev: events.append((minute, ev[0]))
                else:
                    if random.random() < 0.20:
                        events.append((minute, f"⚙️ *{minute}'* — {random.choice(_PRESSURE)}"))
                if random.random() < CARD_PROB and yellows_a < 3 and nm_a:
                    yellows_a += 1
                    name = random.choice(nm_a)
                    events.append((minute, f"🟨 *{minute}'* — {name} (предупреждение)"))
                    if yellows_a == 2 and random.random() < 0.25:
                        red_a = True
                        events.append((minute, f"🟥 *{minute}'* — {name} — УДАЛЁН!"))
            else:
                poss_b += 5
                p = random.randint(9, 16)
                passes_b += p
                acc = min(0.93, 0.62 + sb.get("pas_avg", 70) / 400)
                acc_b_sum += acc; acc_blk_b += 1
                if random.random() < 0.38:
                    ev = _chance(sb["att"], sa["def_"], sc_b, False, minute, False)
                    if ev: events.append((minute, ev[0]))
                else:
                    if random.random() < 0.20:
                        events.append((minute, f"⚙️ *{minute}'* — {random.choice(_DANGER)}"))
                if random.random() < CARD_PROB and yellows_b < 3 and nm_b:
                    yellows_b += 1
                    name = random.choice(nm_b)
                    events.append((minute, f"🟨 *{minute}'* — {name} (предупреждение соп)"))
                    if yellows_b == 2 and random.random() < 0.25:
                        red_b = True
                        events.append((minute, f"🟥 *{minute}'* — {name} — УДАЛЁН! (соп)"))

        # Компенсированное время
        if abs(score_a - score_b) <= 1:
            inj = half * 45 + random.randint(47, 50)
            if random.random() < 0.30:
                is_a = random.random() < (eff_a / total_eff)
                ev = _chance(
                    sa["att"] if is_a else sb["att"],
                    sb["def_"] if is_a else sa["def_"],
                    sc_a if is_a else sc_b, False, inj, is_a,
                )
                if ev: events.append((inj, f"⏱ {ev[0]}"))

        # Фиксируем счёт первого тайма
        if half == 0:
            h1_score_a = score_a
            h1_score_b = score_b

    events.sort(key=lambda x: x[0])

    total_poss = poss_a + poss_b or 1
    acc_a = round((acc_a_sum / max(acc_blk_a, 1)) * 100)
    acc_b = round((acc_b_sum / max(acc_blk_b, 1)) * 100)

    h1_evs = [(m, t) for m, t in events if m <= 45]
    h2_evs = [(m, t) for m, t in events if m > 45]

    return {
        "score_a":   score_a,    "score_b":   score_b,
        "h1_a":      h1_score_a, "h1_b":      h1_score_b,
        "poss_a":    round(poss_a / total_poss * 100),
        "poss_b":    round(poss_b / total_poss * 100),
        "passes_a":  passes_a,   "passes_b":  passes_b,
        "acc_a":     acc_a,      "acc_b":     acc_b,
        "corners_a": corners_a,  "corners_b": corners_b,
        "shots_a":   shots_a,    "shots_b":   shots_b,
        "yellows_a": yellows_a,  "yellows_b": yellows_b,
        "h1_events": h1_evs,
        "h2_events": h2_evs,
        "all_events": events,
    }


def _match_coins(goals_scored: int, goals_conceded: int) -> int:
    """Монеты по счёту: базовые + за голы + за победу/ничью."""
    base       = 50
    goal_bonus = goals_scored * 60
    margin_bon = max(0, goals_scored - goals_conceded) * 25
    if goals_scored > goals_conceded:
        result_bon = 200
    elif goals_scored == goals_conceded:
        result_bon = 75
    else:
        result_bon = 0
    return base + goal_bonus + margin_bon + result_bon


def _elo_delta(ra: int, rb: int, result: float, games_played: int) -> int:
    """result: 1 = победа, 0.5 = ничья, 0 = поражение.
    Первые MATCH_CALIB_GAMES — калибровка с удвоенным K."""
    k = MATCH_K_CALIBRATION if games_played < MATCH_CALIB_GAMES else MATCH_K_FACTOR
    exp = 1 / (1 + 10 ** ((rb - ra) / 400))
    return round(k * (result - exp))


# ══════════════════════════════════════════════════════════════════════════════
#  МАТЧИ — ФОРМАТИРОВАНИЕ
# ══════════════════════════════════════════════════════════════════════════════

def _calib_label(games: int) -> str:
    if games < MATCH_CALIB_GAMES:
        return f" _(калибровка {games}/{MATCH_CALIB_GAMES})_"
    return ""


def _match_preview_text(my_name: str, opp_name: str, sa: dict, sb: dict,
                        my_rating: int, opp_rating: int, my_games: int, opp_games: int) -> str:
    mc = _calib_label(my_games)
    oc = _calib_label(opp_games)
    return (
        f"⚔️ *Матч*\n\n"
        f"🔵 *{my_name}*{mc}\n"
        f"   OVR *{sa['ovr']}*  •  ATT *{sa['att']}*  •  DEF *{sa['def_']}*  "
        f"•  Хим *{sa['chem']}%*  •  ⭐ *{my_rating}*\n\n"
        f"🔴 *{opp_name}*{oc}\n"
        f"   OVR *{sb['ovr']}*  •  ATT *{sb['att']}*  •  DEF *{sb['def_']}*  "
        f"•  Хим *{sb['chem']}%*  •  ⭐ *{opp_rating}*\n\n"
        f"_Отправить вызов?_"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  МАТЧИ — ИНТЕРАКТИВ
# ══════════════════════════════════════════════════════════════════════════════

async def _wait_interaction(user_id: int, timeout: float = 30.0) -> str | None:
    """Ждём выбора через polling (каждые 0.3с). None = таймаут."""
    _interaction_choices[user_id] = None
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        v = _interaction_choices.get(user_id)
        if v is not None:
            _interaction_choices.pop(user_id, None)
            return v
        await asyncio.sleep(0.3)
    _interaction_choices.pop(user_id, None)
    return None


async def _wait_interaction_with_countdown(
    user_id: int,
    base_prompt: str,
    kb,
    show_fn,
    timeout: float = 30.0,
) -> tuple[str | None, bool]:
    """
    Polling-ожидание выбора с обновлением таймера в сообщении.
    Возвращает (choice, is_auto).
    """
    _interaction_choices[user_id] = None
    deadline = asyncio.get_event_loop().time() + timeout
    last_tick = int(timeout) + 1
    choice = None

    while asyncio.get_event_loop().time() < deadline:
        v = _interaction_choices.get(user_id)
        if v is not None:
            _interaction_choices.pop(user_id, None)
            choice = v
            break

        secs_left = max(0, int(deadline - asyncio.get_event_loop().time()))
        # Обновляем счётчик при каждой смене секунды (все секунды ≤ 15)
        if secs_left != last_tick and (secs_left <= 15 or secs_left % 5 == 0):
            last_tick = secs_left
            bar = "🟥" * min(secs_left, 10) + "⬛" * (10 - min(secs_left, 10))
            await show_fn(f"{base_prompt}\n\n{bar} *{secs_left}с*", kb=kb)

        await asyncio.sleep(0.3)

    _interaction_choices.pop(user_id, None)
    return choice, choice is None


async def cb_fut_interact(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Принимает выбор игрока в интерактивный момент. fut_int_{choice}"""
    q      = update.callback_query
    uid    = q.from_user.id
    choice = q.data[len("fut_int_"):]

    # Пишем выбор — _wait_interaction подхватит на следующем poll-цикле
    _interaction_choices[uid] = choice

    # Также submit к shared момент если есть активный для этого игрока
    for moment in list(_match_moments.values()):
        if uid in (moment.attacker_uid, moment.keeper_uid):
            moment.submit(uid, choice)
            break

    await q.answer("✅ Выбор сделан!")


# ══════════════════════════════════════════════════════════════════════════════
#  МАТЧИ — АНИМАЦИЯ
# ══════════════════════════════════════════════════════════════════════════════

_BOT_UID_SENTINEL = -1  # псевдо-uid для «бот-соперника» в драфте/турнире


def _make_shared_moments_pvp(
    uid_a: int, uid_b: int,
    sa_a: dict, sa_b: dict,
    match_key: str,
) -> list[dict]:
    """Создаёт интерактивные моменты для матча двух живых игроков.
    Регистрирует _MatchMoment в глобальном _match_moments.
    Возвращает список moment-cfg для _run_match_animation."""
    moment_pool   = ["penalty", "1v1", "freekick"]
    shared: list[dict] = []
    n_h1 = 1 if random.random() < 0.55 else 0
    n_h2 = 1 if random.random() < 0.55 else 0
    for half_num, n in ((1, n_h1), (2, n_h2)):
        for _ in range(n):
            mtype    = random.choice(moment_pool)
            minute   = random.randint(28, 42) if half_num == 1 else random.randint(58, 72)
            attacker = random.choice([uid_a, uid_b])
            keeper   = uid_b if attacker == uid_a else uid_a
            mid      = f"{match_key}_{half_num}_{mtype}"
            _match_moments[mid] = _MatchMoment(mtype, attacker, keeper)
            att_str  = sa_a["att"] if attacker == uid_a else sa_b["att"]
            def_str  = sa_a["def_"] if keeper == uid_a else sa_b["def_"]
            shared.append({
                "half": half_num, "minute": minute, "type": mtype,
                "attacker_uid": attacker, "keeper_uid": keeper, "moment_id": mid,
                "att_str": att_str, "def_str": def_str,
            })
    return shared


def _make_shared_moments_vs_bot(
    human_uid: int,
    human_sa: dict,
    bot_sa: dict,
    match_key: str,
) -> list[dict]:
    """Создаёт интерактивные моменты для матча человека против бота.
    Бот сразу делает случайный выбор — анимация разрешится как только
    игрок нажмёт кнопку (или истечёт таймер).
    Возвращает список moment-cfg для _run_match_animation (только human_uid получает анимацию)."""
    BOT_UID = _BOT_UID_SENTINEL
    moment_pool   = ["penalty", "1v1", "freekick"]
    shared: list[dict] = []
    n_h1 = 1 if random.random() < 0.55 else 0
    n_h2 = 1 if random.random() < 0.55 else 0
    for half_num, n in ((1, n_h1), (2, n_h2)):
        for _ in range(n):
            mtype    = random.choice(moment_pool)
            minute   = random.randint(28, 42) if half_num == 1 else random.randint(58, 72)
            attacker = random.choice([human_uid, BOT_UID])
            keeper   = BOT_UID if attacker == human_uid else human_uid
            mid      = f"{match_key}_{half_num}_{mtype}"
            moment   = _MatchMoment(mtype, attacker, keeper)
            _match_moments[mid] = moment

            att_str  = human_sa["att"] if attacker == human_uid else bot_sa["att"]
            def_str  = human_sa["def_"] if keeper == human_uid else bot_sa["def_"]

            # Бот немедленно делает выбор
            BOT_CHOICES = {
                "penalty":  ["left", "center", "right"],
                "1v1":      {"att": ["shot", "dribble"], "kpr": ["attack", "stay"]},
                "freekick": {"att": ["top", "bottom"],   "kpr": ["up", "down"]},
            }
            if mtype == "1v1":
                bot_role = "att" if attacker == BOT_UID else "kpr"
                bot_choice = random.choice(BOT_CHOICES["1v1"][bot_role])
            elif mtype == "freekick":
                bot_role = "att" if attacker == BOT_UID else "kpr"
                bot_choice = random.choice(BOT_CHOICES["freekick"][bot_role])
            else:  # penalty — те же опции для атаки и вратаря
                bot_choice = random.choice(BOT_CHOICES["penalty"])
            moment.submit(BOT_UID, bot_choice)

            shared.append({
                "half": half_num, "minute": minute, "type": mtype,
                "attacker_uid": attacker, "keeper_uid": keeper, "moment_id": mid,
                "att_str": att_str, "def_str": def_str,
            })
    return shared


async def _run_match_animation(
    bot, chat_id: int, message_id: int | None,
    my_name: str, opp_name: str,
    my_uid: int,
    stats: dict,
    r_delta: int, coins: int,
    shared_moments: list[dict] | None = None,
    after_kb: InlineKeyboardMarkup | None = None,
    my_sa: dict | None = None,
    opp_sa: dict | None = None,
) -> None:
    """Анимирует матч: A (пулы комментариев) + B (имена игроков) + D (кинематограф)."""

    sent_id = message_id

    # ── B: имена игроков из SA-дикта ─────────────────────────────────────────
    _my_scorers  = (my_sa  or {}).get("scorers",  [my_name])
    _my_gk       = (my_sa  or {}).get("gk_name",  "Вратарь")
    _opp_scorers = (opp_sa or {}).get("scorers",  [opp_name])
    _opp_gk      = (opp_sa or {}).get("gk_name",  "Вратарь")

    async def _show(text: str, kb=None):
        nonlocal sent_id
        try:
            if sent_id:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=sent_id,
                    text=text, parse_mode="Markdown", reply_markup=kb,
                )
            else:
                msg = await bot.send_message(
                    chat_id=chat_id, text=text,
                    parse_mode="Markdown", reply_markup=kb,
                )
                sent_id = msg.message_id
        except Exception:
            pass

    # ── Интерактивный момент — A + B + D ─────────────────────────────────────
    async def _interactive_shared(moment_cfg: dict) -> tuple[int, tuple[int, int]]:
        moment: _MatchMoment = _match_moments.get(moment_cfg["moment_id"])
        if not moment:
            return 0, (0, 0)

        mtype        = moment_cfg["type"]
        minute       = moment_cfg["minute"]
        is_attacker  = (my_uid == moment.attacker_uid)
        att_str: int = moment_cfg.get("att_str", 80)
        def_str: int = moment_cfg.get("def_str", 80)
        edge = max(-0.15, min(0.15, (att_str - def_str) / 200))

        ATT_OPTS = {
            "penalty":  [("↖️ Влево", "left"), ("⬆️ Центр", "center"), ("↗️ Вправо", "right")],
            "1v1":      [("⚽ Бить!", "shot"), ("🎯 Обводка!", "dribble")],
            "freekick": [("⬆️ Верхний угол", "top"), ("⬇️ Нижний угол", "bottom")],
        }
        KPR_OPTS = {
            "penalty":  [("↖️ Влево", "left"), ("⬆️ Центр", "center"), ("↗️ Вправо", "right")],
            "1v1":      [("⚡ Выйти навстречу", "attack"), ("🧤 Держать ворота", "stay")],
            "freekick": [("⬆️ Прыгнуть вверх", "up"), ("⬇️ Прыгнуть вниз", "down")],
        }

        _is_you = (my_name == "Ты")
        # B: имена для момента
        _att_player = random.choice(_my_scorers if is_attacker else _opp_scorers)
        _kpr_player = _opp_gk if is_attacker else _my_gk

        # Тексты-подсказки с реальными именами (A+B)
        ATT_BASE = {
            "penalty":  (
                f"🟡 *{minute}'* — *ПЕНАЛЬТИ!*\n\n"
                f"💥 *{_att_player}* {'выходишь' if _is_you else 'выходит'} к точке!\n"
                f"*{_kpr_player}* в воротах... Куда бьёшь?"
            ),
            "1v1":      (
                f"🔥 *{minute}'* — *ОДИН НА ОДИН!*\n\n"
                f"⚡ *{_att_player}* {'врываешься' if _is_you else 'врывается'} в штрафную!\n"
                f"*{_kpr_player}* выходит навстречу. Что делаешь?"
            ),
            "freekick": (
                f"⚡ *{minute}'* — *ШТРАФНОЙ!*\n\n"
                f"🎯 *{_att_player}* {'разбегаешься' if _is_you else 'разбегается'}!\n"
                f"*{_kpr_player}* строит стенку. Куда бьёшь?"
            ),
        }
        KPR_BASE = {
            "penalty":  (
                f"🟡 *{minute}'* — *Пенальти против тебя!*\n\n"
                f"😰 Нападающий соперника идёт к точке!\n"
                f"*{_kpr_player}* готовится... Куда {'прыгаешь' if _is_you else 'прыгает'}?"
            ),
            "1v1":      (
                f"🔥 *{minute}'* — *Один на один!*\n\n"
                f"😤 Нападающий соперника выходит на *{_kpr_player}*!\n"
                f"Что {'делаешь' if _is_you else 'делает'} вратарь?"
            ),
            "freekick": (
                f"⚡ *{minute}'* — *Штрафной против тебя!*\n\n"
                f"😬 Соперник готовится к удару!\n"
                f"*{_kpr_player}* строит стенку. Куда {'прыгаешь' if _is_you else 'прыгает'}?"
            ),
        }

        opts      = ATT_OPTS[mtype] if is_attacker else KPR_OPTS[mtype]
        base_text = ATT_BASE[mtype] if is_attacker else KPR_BASE[mtype]

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(lbl, callback_data=f"fut_int_{val}") for lbl, val in opts
        ]])

        choice, auto = await _wait_interaction_with_countdown(
            user_id=my_uid,
            base_prompt=base_text,
            kb=kb,
            show_fn=_show,
            timeout=30.0,
        )
        if auto:
            choice = random.choice([v for _, v in opts])
        moment.submit(my_uid, choice)

        await _show("✅ *Выбор сделан!* Ждём соперника...")
        result = await moment.wait_result(timeout=10.0)
        att_c = result["att"]
        kpr_c = result["kpr"]

        # ── Вычисляем исход ────────────────────────────────────────────────────
        match_dir = False
        if mtype == "penalty":
            if att_c != kpr_c:
                prob = max(0.55, min(0.97, 0.82 + edge))
            else:
                prob = max(0.05, min(0.35, 0.15 + edge))
            goal = random.random() < prob
        elif mtype == "1v1":
            if att_c == "shot":
                base_p = 0.68 if kpr_c == "attack" else 0.40
            else:
                base_p = 0.60 if kpr_c == "stay" else 0.25
            goal = random.random() < max(0.05, min(0.95, base_p + edge))
        else:  # freekick
            match_dir = (att_c == "top" and kpr_c == "up") or (att_c == "bottom" and kpr_c == "down")
            base_p = 0.18 if match_dir else 0.52
            goal = random.random() < max(0.05, min(0.90, base_p + edge))

        # ── D: Кинематографическая последовательность ─────────────────────────
        if mtype == "penalty":
            _cine1 = (
                f"📍 *{_att_player}* устанавливает мяч на точку...\n"
                f"_Стадион замер в ожидании_"
            )
            _kpr_dir = {"left": "влево", "right": "вправо", "center": "в центр"}.get(kpr_c, "")
            _cine2 = (
                f"💨 Разбег! *{_att_player}* бьёт!\n"
                f"🧤 *{_kpr_player}* прыгает {_kpr_dir}..."
            )
        elif mtype == "1v1":
            _action = "бьёт по воротам" if att_c == "shot" else "идёт в обводку"
            _kpr_act = "выходит навстречу" if kpr_c == "attack" else "держит позицию"
            _cine1 = (
                f"⚡ *{_att_player}* врывается в штрафную!\n"
                f"_Один шанс — всё или ничего!_"
            )
            _cine2 = (
                f"🏃 *{_att_player}* {_action}!\n"
                f"🧤 *{_kpr_player}* {_kpr_act}..."
            )
        else:  # freekick
            _kpr_jump = "вверх" if kpr_c == "up" else "вниз"
            _cine1 = (
                f"🎯 *{_att_player}* разбегается к мячу...\n"
                f"_Тишина на стадионе. Стенка выстроена._"
            )
            _cine2 = (
                f"💥 Удар! *{_kpr_player}* прыгает {_kpr_jump}..."
            )

        await _show(_cine1)
        await asyncio.sleep(0.8)
        await _show(_cine2)
        await asyncio.sleep(0.7)

        # ── Человекочитаемые описания выборов ────────────────────────────────
        ATT_3 = {
            "left":    "бьёт *влево* ↖️",   "center": "бьёт *в центр* ⬆️",
            "right":   "бьёт *вправо* ↗️",
            "shot":    "наносит *удар* ⚽",   "dribble": "идёт *в обводку* 🎯",
            "top":     "целит *в верхний угол* ⬆️",
            "bottom":  "целит *в нижний угол* ⬇️",
        }
        ATT_2 = {
            "left":    "бьёшь *влево* ↖️",  "center": "бьёшь *в центр* ⬆️",
            "right":   "бьёшь *вправо* ↗️",
            "shot":    "наносишь *удар* ⚽",  "dribble": "идёшь *в обводку* 🎯",
            "top":     "целишь *в верхний угол* ⬆️",
            "bottom":  "целишь *в нижний угол* ⬇️",
        }
        KPR_3 = {
            "left":    "прыгает *влево* ↖️",  "center": "остаётся *в центре* ⬆️",
            "right":   "прыгает *вправо* ↗️",
            "attack":  "выходит *навстречу* ⚡", "stay": "держит *позицию* 🧤",
            "up":      "прыгает *вверх* ⬆️",   "down": "прыгает *вниз* ⬇️",
        }
        KPR_2 = {
            "left":    "прыгаешь *влево* ↖️", "center": "остаёшься *в центре* ⬆️",
            "right":   "прыгаешь *вправо* ↗️",
            "attack":  "выходишь *навстречу* ⚡", "stay": "держишь *позицию* 🧤",
            "up":      "прыгаешь *вверх* ⬆️",  "down": "прыгаешь *вниз* ⬇️",
        }

        auto_tag = " _(авто)_" if auto else ""

        if is_attacker:
            att_lbl = (ATT_2 if my_name == "Ты" else ATT_3).get(att_c, att_c)
            kpr_lbl = KPR_3.get(kpr_c, kpr_c)
        else:
            att_lbl = ATT_3.get(att_c, att_c)
            kpr_lbl = (KPR_2 if my_name == "Ты" else KPR_3).get(kpr_c, kpr_c)

        setup = (
            f"⚽ *{_att_player}* {att_lbl}\n"
            f"🧤 *{_kpr_player}* {kpr_lbl}"
        )

        # ── Текст результата (B: имена в восклицаниях) ────────────────────────
        if goal:
            bonus = 150 if mtype == "penalty" else 100
            if is_attacker:
                excl = random.choice([
                    f"*{_att_player}* — в девятку! 💥",
                    "Чистый гол! 🚀",
                    f"*{_kpr_player}* не угадал! 🎉",
                    f"*{_att_player}* — мастер класс! 🔥",
                    "Мяч в сетке! Что за гол! ⚽",
                    "ГОООЛ! Стадион взрывается! 🏟",
                ])
                result_txt = (
                    f"⚽ *ГОЛ!*{auto_tag}\n\n"
                    f"{setup}\n\n"
                    f"🔥 {excl}\n"
                    f"💰 Бонус: *+{bonus}* монет!"
                )
            else:
                excl = random.choice([
                    "Не угадал... 😔",
                    f"*{_att_player}* оказался хитрее 😤",
                    "Обидный гол 😞",
                    f"*{_att_player}* не оставил шансов 😤",
                ])
                result_txt = (
                    f"😤 *Гол в твои ворота!*{auto_tag}\n\n"
                    f"{setup}\n\n"
                    f"{excl}"
                )
                bonus = 0
        else:
            if is_attacker:
                if mtype == "penalty":
                    fail = (
                        f"*{_kpr_player}* угадал угол! 🧤" if att_c == kpr_c
                        else random.choice([
                            f"*{_att_player}* — рядом со штангой! 😬",
                            "Мяч над перекладиной! 💨",
                            f"*{_kpr_player}* вытянул руку! 🧤",
                        ])
                    )
                elif mtype == "1v1":
                    if att_c == "shot":
                        fail = (
                            f"*{_kpr_player}* угадал и взял! 🧤" if kpr_c == "attack"
                            else random.choice(["В штангу! 💥", "Мимо! 💨"])
                        )
                    else:
                        fail = (
                            f"*{_kpr_player}* читает обводку! 🧤" if kpr_c == "attack"
                            else random.choice([
                                "Слишком медленно! 😬",
                                f"*{_kpr_player}* перекрыл угол! 🧤",
                            ])
                        )
                else:  # freekick
                    fail = (
                        f"*{_kpr_player}* угадал направление! 🧤" if match_dir
                        else random.choice([
                            "В стенку! 💨", "Над перекладиной! 💨",
                            f"*{_kpr_player}* легко взял! 🧤",
                        ])
                    )
                result_txt = (
                    f"❌ *Не получилось!*{auto_tag}\n\n"
                    f"{setup}\n\n"
                    f"{fail}"
                )
                bonus = 0
            else:
                if mtype == "penalty":
                    excl = (
                        f"*{_kpr_player}* угадал угол! 🎯" if att_c == kpr_c
                        else random.choice([
                            f"*{_kpr_player}* — невероятный рефлекс! 🏆",
                            f"*{_kpr_player}* — потрясающий сейв! 🔥",
                        ])
                    )
                elif mtype == "1v1":
                    excl = (
                        f"*{_kpr_player}* выходит и накрывает! ⚡" if kpr_c == "attack"
                        else random.choice([
                            f"*{_kpr_player}* — правильная позиция! 🧤",
                            f"*{_kpr_player}* сужает угол! 🏆",
                        ])
                    )
                else:  # freekick
                    excl = (
                        f"*{_kpr_player}* угадал направление! 🎯" if match_dir
                        else random.choice([
                            f"*{_kpr_player}* — рефлекс на высшем уровне! 🏆",
                            f"*{_kpr_player}* — великолепный сейв! 🔥",
                        ])
                    )
                bonus = 100
                result_txt = (
                    f"🧤 *СЕЙВ!*{auto_tag}\n\n"
                    f"{setup}\n\n"
                    f"🔵 {excl}\n"
                    f"💰 Бонус: *+{bonus}* монет!"
                )

        await _show(result_txt)
        await asyncio.sleep(2.5)
        if goal:
            return bonus, (1, 0) if is_attacker else (0, 1)
        return bonus, (0, 0)

    # ── Разбиваем shared_moments по таймам ────────────────────────────────────
    moments = shared_moments or []
    h1_moments = [m for m in moments if m.get("half") == 1]
    h2_moments = [m for m in moments if m.get("half") == 2]
    bonus_total = 0

    score_a   = stats["score_a"]
    score_b   = stats["score_b"]
    h1_a      = stats["h1_a"]
    h1_b      = stats["h1_b"]
    h1_events = stats["h1_events"]
    h2_events = stats["h2_events"]
    poss_a    = stats["poss_a"]
    poss_b    = stats["poss_b"]

    # ── Старт — A+B: имя звезды + kickoff-фраза ───────────────────────────────
    _real_names = [n for n in _my_scorers if n not in (my_name, "Игрок", "Бот")]
    if _real_names:
        _star = random.choice(_real_names)
        ko_line = f"_Все взоры на *{_star}* — главная звезда атаки!_"
    else:
        ko_line = f"_{random.choice(_COMM_KICKOFF)}_"
    await _show(
        f"⚽ *Матч начинается!*\n\n"
        f"🔵 *{my_name}*\n"
        f"🔴 *{opp_name}*\n\n"
        f"{ko_line}"
    )
    await asyncio.sleep(1.5)

    # ── 1-й тайм — 0' — A: ранняя фраза комментатора ─────────────────────────
    await _show(
        f"⏱ *1-й тайм — 0:00*\n\n"
        f"🔵 *{my_name}*  *0* : *0*  🔴 *{opp_name}*\n\n"
        f"_{random.choice(_COMM_EARLY)}_"
    )
    await asyncio.sleep(2.0)

    # ── 1-й тайм — 25' — A+B: события + шаут-аут игрока ─────────────────────
    early_evs = [(m, t) for m, t in h1_events if m <= 25]
    shown = "\n".join(t for _, t in early_evs[-2:]) if early_evs else f"_{random.choice(_COMM_EARLY)}_"
    # B: shoutout реального игрока
    _shout = ""
    if _real_names:
        _pl = random.choice(_real_names)
        _shout = "\n" + random.choice([
            f"⚡ *{_pl}* активно ищет голевой момент!",
            f"🎯 *{_pl}* создаёт давление на оборону!",
            f"🔥 *{_pl}* опасен в каждой атаке!",
            f"💡 *{_pl}* диктует темп игры!",
        ])
    await _show(
        f"⏱ *1-й тайм — 25:00*\n\n"
        f"🔵 *{my_name}*  *0* : *0*  🔴 *{opp_name}*\n\n"
        f"{shown}{_shout}"
    )
    await asyncio.sleep(2.0)

    # ── Интерактив 1-го тайма ─────────────────────────────────────────────────
    inter_h1_a = inter_h1_b = 0
    for m_cfg in h1_moments:
        b, (da, db) = await _interactive_shared(m_cfg)
        bonus_total += b
        score_a += da; score_b += db
        inter_h1_a += da; inter_h1_b += db

    # Actual halftime score = pre-simulated h1 + interactive h1 goals
    ht_a = h1_a + inter_h1_a
    ht_b = h1_b + inter_h1_b

    # ── 1-й тайм — 40' — A: напряжение концовки тайма ───────────────────────────
    late_h1 = [(m, t) for m, t in h1_events if 25 < m <= 45]
    if late_h1:
        shown2 = "\n".join(t for _, t in late_h1[-2:])
        _tens = random.choice([
            "_Заканчивается первый тайм — мяч неустанно в движении!_",
            "_Напряжение нарастает — скоро перерыв!_",
            "_Судья смотрит на часы — добавленное время близко!_",
            "_Обе команды ищут гол до перерыва!_",
            "_Каждая атака может изменить всё!_",
        ])
        await _show(
            f"⏱ *1-й тайм — 40:00*\n\n"
            f"🔵 *{my_name}*  *?* : *?*  🔴 *{opp_name}*\n\n"
            f"{shown2}\n\n{_tens}"
        )
        await asyncio.sleep(1.8)

    # ── Перерыв — 45' — A: ситуационный комментарий по счёту ─────────────────
    if ht_a > ht_b:
        ht_lead = (
            f"\n🔵 *{my_name}* ведёт! "
            + random.choice(_COMM_LEADING)
        )
    elif ht_b > ht_a:
        ht_lead = (
            f"\n🔴 *{opp_name}* ведёт! "
            + random.choice(_COMM_TRAILING)
        )
    else:
        ht_lead = f"\n_{random.choice(_COMM_DRAW_LATE)}_"
    await _show(
        f"🕐 *Перерыв — 45'*\n\n"
        f"🔵 *{my_name}*  *{ht_a}* : *{ht_b}*  🔴 *{opp_name}*{ht_lead}\n\n"
        f"📊 Владение 1-го тайма: *{poss_a}%* — *{poss_b}%*\n"
        f"_{random.choice(_COMM_HT)}_"
    )
    await asyncio.sleep(2.2)

    # ── 2-й тайм — 45' — A: свежий старт ─────────────────────────────────────
    sh_comm = random.choice(_COMM_SECOND_HALF)
    if ht_a != ht_b:
        leading = my_name if ht_a > ht_b else opp_name
        tension = f"_{leading} ведёт! {sh_comm}_"
    else:
        tension = f"_{sh_comm}_"
    await _show(
        f"⏱ *2-й тайм — 45:00*\n\n"
        f"🔵 *{my_name}*  *{ht_a}* : *{ht_b}*  🔴 *{opp_name}*\n\n"
        f"{tension}"
    )
    await asyncio.sleep(2.0)

    # ── 2-й тайм — 65' — A+B: ситуационный + игрок под давлением ────────────
    mid2_evs = [(m, t) for m, t in h2_events if m <= 65]
    if mid2_evs:
        shown3 = "\n".join(t for _, t in mid2_evs[-2:])
        if ht_a > ht_b:
            _sit = random.choice(_COMM_LEADING)
        elif ht_b > ht_a:
            _sit = random.choice(_COMM_TRAILING)
        else:
            _sit = random.choice(_COMM_DRAW_LATE)
        # B: shoutout игрока при ничьей или проигрыше
        _mid_shout = ""
        if _real_names and ht_a <= ht_b:
            _pl2 = random.choice(_real_names)
            _mid_shout = f"\n🔥 *{_pl2}* рвётся к воротам!"
        await _show(
            f"⏱ *2-й тайм — 65:00*\n\n"
            f"🔵 *{my_name}*  *{ht_a}* : *{ht_b}*  🔴 *{opp_name}*\n\n"
            f"{shown3}\n\n_{_sit}_{_mid_shout}"
        )
        await asyncio.sleep(2.0)

    # ── Интерактив 2-го тайма ─────────────────────────────────────────────────
    for m_cfg in h2_moments:
        b, (da, db) = await _interactive_shared(m_cfg)
        bonus_total += b
        score_a += da; score_b += db

    # ── Концовка — 80'+ — A+B: кульминация с именем ───────────────────────────
    late2_evs = [(m, t) for m, t in h2_events if m > 65]
    if late2_evs:
        shown4 = "\n".join(t for _, t in late2_evs[-2:])
        _climax = random.choice(_COMM_CLIMAX)
        _end_shout = ""
        if score_a > score_b and _real_names:
            _end_shout = f"\n💪 *{random.choice(_real_names)}* закрывает игру!"
        elif score_a < score_b and _real_names:
            _end_shout = f"\n🔥 *{random.choice(_real_names)}* ищет спасительный гол!"
        await _show(
            f"🔥 *Горячая концовка!*\n\n"
            f"🔵 *{my_name}*  *{score_a}* : *{score_b}*  🔴 *{opp_name}*\n\n"
            f"{shown4}\n\n{_climax}{_end_shout}"
        )
        await asyncio.sleep(1.8)

    # ── Финальный свисток ─────────────────────────────────────────────────────
    if score_a > score_b:
        result_hdr = "🏆 *ПОБЕДА!*"
        emoji_row  = "🥇🎉🏆"
    elif score_a == score_b:
        result_hdr = "🤝 *Ничья*"
        emoji_row  = "🤝"
    else:
        result_hdr = "💀 *Поражение*"
        emoji_row  = "😤"

    acc_a_str = f"{stats['acc_a']}%"
    acc_b_str = f"{stats['acc_b']}%"
    pos_a_str = f"{poss_a}%"
    pos_b_str = f"{poss_b}%"

    total_c   = coins + bonus_total
    bonus_str = f"  _(+{bonus_total} бонус)_" if bonus_total else ""
    extra_lines = ""
    if r_delta != 0:
        r_str = f"+{r_delta}" if r_delta >= 0 else str(r_delta)
        extra_lines += f"📈 Рейтинг:   *{r_str}* ⭐\n"
    if total_c != 0:
        c_str = f"+{total_c}"
        extra_lines += f"💰 Монеты:    *{c_str}* 💰{bonus_str}\n"

    kb = after_kb or InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Ещё матч", callback_data="fut_match"),
         InlineKeyboardButton("🏟 Команда",  callback_data="fut_team")],
        [InlineKeyboardButton("◀ FUT меню",  callback_data="fut_menu")],
    ])

    await _show(
        f"{result_hdr}  {emoji_row}\n\n"
        f"🔵 *{my_name}*   *{score_a}* : *{score_b}*   🔴 *{opp_name}*\n\n"
        f"📊 *Статистика матча*\n"
        f"```\n"
        f"{'':>14}{'🔵':^7}{'🔴':^7}\n"
        f"{'Владение':>14}{pos_a_str:^7}{pos_b_str:^7}\n"
        f"{'Удары':>14}{stats['shots_a']:^7}{stats['shots_b']:^7}\n"
        f"{'Передачи':>14}{stats['passes_a']:^7}{stats['passes_b']:^7}\n"
        f"{'Точность':>14}{acc_a_str:^7}{acc_b_str:^7}\n"
        f"{'Угловые':>14}{stats['corners_a']:^7}{stats['corners_b']:^7}\n"
        f"```\n"
        + extra_lines,
        kb=kb,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  МАТЧИ — ХЕНДЛЕРЫ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_match(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Главное меню матчей. fut_match"""
    q   = update.callback_query
    uid = q.from_user.id
    try:
        await q.answer()
    except Exception:
        pass

    sa = _calc_strength(uid)
    if sa["placed"] < MATCH_MIN_PLACED:
        await q.edit_message_text(
            f"⚔️ *Матчи*\n\n"
            f"Для игры нужно расставить минимум *{MATCH_MIN_PLACED} игроков* в команде.\n"
            f"Сейчас расставлено: *{sa['placed']}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏟 Собрать команду", callback_data="fut_team")],
                [InlineKeyboardButton("◀ FUT меню",        callback_data="fut_menu")],
            ]),
        )
        return

    opponents  = _get_opponents(uid)
    my_rating  = _get_fut_rating(uid)
    my_games   = _get_fut_games(uid)
    calib_str  = _calib_label(my_games)

    lines = [
        f"⚔️ *Матчи*\n",
        f"Твоя команда: OVR *{sa['ovr']}* | ATT *{sa['att']}* | DEF *{sa['def_']}* | "
        f"Хим *{sa['chem']}%* | ⭐ *{my_rating}*{calib_str}\n",
    ]

    if not opponents:
        lines.append("_Пока нет соперников с командой. Позови друзей!_")
        kb = [[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]
    else:
        lines.append("*Выбери соперника:*")
        kb_rows = []
        for opp in opponents[:8]:
            calib = "🔰" if opp["fut_games"] < MATCH_CALIB_GAMES else ""
            label = f"⭐{opp['fut_rating']} {calib} {opp['name'][:16]}"
            kb_rows.append([InlineKeyboardButton(label, callback_data=f"fut_challenge_{opp['user_id']}")])
        kb_rows.append([
            InlineKeyboardButton("📋 История",  callback_data="fut_match_history"),
            InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu"),
        ])
        kb = kb_rows

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_challenge(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Предпросмотр матча + подтверждение. fut_challenge_{opp_uid}"""
    q      = update.callback_query
    uid    = q.from_user.id
    opp_id = int(q.data[len("fut_challenge_"):])
    try:
        await q.answer()
    except Exception:
        pass

    opp_user = db.get_user(opp_id)
    if not opp_user:
        await q.answer("Игрок не найден.", show_alert=True); return

    sa = _calc_strength(uid)
    sb = _calc_strength(opp_id)
    my_rating  = _get_fut_rating(uid)
    opp_rating = _get_fut_rating(opp_id)
    my_games   = _get_fut_games(uid)
    opp_games  = _get_fut_games(opp_id)
    my_name    = q.from_user.first_name or "Ты"
    opp_name   = opp_user.get("display_name") or opp_user.get("username") or f"User{opp_id}"

    await q.edit_message_text(
        _match_preview_text(my_name, opp_name, sa, sb, my_rating, opp_rating, my_games, opp_games),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Вызвать!", callback_data=f"fut_send_{opp_id}")],
            [InlineKeyboardButton("◀ Назад",    callback_data="fut_match")],
        ]),
    )


async def cb_fut_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет вызов сопернику. fut_send_{opp_uid}"""
    q      = update.callback_query
    uid    = q.from_user.id
    opp_id = int(q.data[len("fut_send_"):])
    try:
        await q.answer("Вызов отправлен! ✅")
    except Exception:
        pass

    # Проверяем нет ли уже ожидающего вызова
    existing = db.get_pending_action(opp_id)
    if existing and existing.get("action") == "fut_challenge":
        await q.edit_message_text(
            "⏳ У этого игрока уже есть входящий вызов. Попробуй позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_match")]
            ]),
        )
        return

    opp_user = db.get_user(opp_id)
    my_name  = q.from_user.first_name or "Игрок"
    opp_name = (opp_user or {}).get("display_name") or f"User{opp_id}"

    sa = _calc_strength(uid)
    my_rating = _get_fut_rating(uid)

    # Сохраняем вызов в pending_actions для соперника
    db.set_pending_action(opp_id, "fut_challenge", {
        "challenger_id":   uid,
        "challenger_name": my_name,
        "challenger_rating": my_rating,
        "challenger_ovr":  sa["ovr"],
        "challenger_att":  sa["att"],
        "challenger_def":  sa["def_"],
        "challenger_chem": sa["chem"],
    })

    # Уведомление сопернику
    try:
        await ctx.bot.send_message(
            chat_id=opp_id,
            text=(
                f"⚔️ *Входящий вызов!*\n\n"
                f"🔴 *{my_name}* вызывает тебя на матч!\n\n"
                f"   OVR *{sa['ovr']}*  •  ATT *{sa['att']}*  •  DEF *{sa['def_']}*  "
                f"•  ⭐ *{my_rating}*"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять",  callback_data=f"fut_accept_{uid}"),
                 InlineKeyboardButton("❌ Отклонить", callback_data=f"fut_decline_{uid}")],
            ]),
        )
    except Exception as e:
        logger.warning(f"Не смог отправить вызов {opp_id}: {e}")

    await q.edit_message_text(
        f"✅ Вызов отправлен *{opp_name}*!\n\n"
        f"_Ждём ответа..._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]
        ]),
    )


async def cb_fut_accept(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Принять вызов и сыграть матч. fut_accept_{challenger_uid}"""
    q             = update.callback_query
    accepter_id   = q.from_user.id
    challenger_id = int(q.data[len("fut_accept_"):])
    try:
        await q.answer("Матч начинается! ⚽")
    except Exception:
        pass

    # Данные вызова
    pending = db.get_pending_action(accepter_id)
    if not pending or pending.get("action") != "fut_challenge":
        await q.edit_message_text(
            "⏳ Вызов устарел или уже принят.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]
            ]),
        )
        return

    db.clear_pending_action(accepter_id)
    data = pending.get("data", {})

    # Имена
    ch_name  = data.get("challenger_name", f"User{challenger_id}")
    my_name  = q.from_user.first_name or "Соперник"

    # Силы команд (пересчитываем актуально, включая имена игроков для комментария)
    sa = _calc_strength(challenger_id)  # challenger (тот кто вызвал)
    sb = _calc_strength(accepter_id)    # accepter

    # Рейтинги
    ra = data.get("challenger_rating", 1000)
    rb = _get_fut_rating(accepter_id)

    # Симуляция двух таймов
    match_stats = _simulate_match(sa, sb)  # A = challenger, B = accepter
    score_ch = match_stats["score_a"]
    score_ac = match_stats["score_b"]

    # Результат
    if score_ch > score_ac:
        result_ch, result_ac = 1.0, 0.0
    elif score_ch == score_ac:
        result_ch = result_ac = 0.5
    else:
        result_ch, result_ac = 0.0, 1.0

    # Монеты по счёту
    coins_ch = _match_coins(score_ch, score_ac)
    coins_ac = _match_coins(score_ac, score_ch)

    # ELO (с учётом калибровки)
    games_ch = _get_fut_games(challenger_id)
    games_ac = _get_fut_games(accepter_id)
    delta_ch = _elo_delta(ra, rb, result_ch, games_ch)
    delta_ac = _elo_delta(rb, ra, result_ac, games_ac)

    # Обновляем рейтинг, монеты, счётчик матчей
    _set_fut_rating(challenger_id, ra + delta_ch)
    _set_fut_rating(accepter_id,   rb + delta_ac)
    _increment_fut_games(challenger_id)
    _increment_fut_games(accepter_id)
    db.add_coins(challenger_id, coins_ch)
    db.add_coins(accepter_id,   coins_ac)

    # Сохраняем матч
    _save_fut_match(challenger_id, accepter_id, score_ch, score_ac,
                    ra, rb, delta_ch, delta_ac)

    # Статистика для accepter (A и B меняются местами)
    stats_ac = {
        "score_a":   score_ac,
        "score_b":   score_ch,
        "h1_a":      match_stats["h1_b"],
        "h1_b":      match_stats["h1_a"],
        "poss_a":    match_stats["poss_b"],
        "poss_b":    match_stats["poss_a"],
        "passes_a":  match_stats["passes_b"],
        "passes_b":  match_stats["passes_a"],
        "acc_a":     match_stats["acc_b"],
        "acc_b":     match_stats["acc_a"],
        "corners_a": match_stats["corners_b"],
        "corners_b": match_stats["corners_a"],
        "shots_a":   match_stats["shots_b"],
        "shots_b":   match_stats["shots_a"],
        "yellows_a": match_stats["yellows_b"],
        "yellows_b": match_stats["yellows_a"],
        "h1_events": match_stats["h1_events"],   # события показываем как нейтральный комментарий
        "h2_events": match_stats["h2_events"],
        "all_events": match_stats["all_events"],
    }

    # ── Создаём shared интерактивные моменты ──────────────────────────────────
    match_key   = f"{challenger_id}_{accepter_id}"
    n_h1 = 1 if random.random() < 0.55 else 0
    n_h2 = 1 if random.random() < 0.55 else 0
    moment_pool = ["penalty", "1v1", "freekick"]
    shared_moments: list[dict] = []

    for half_num, n in ((1, n_h1), (2, n_h2)):
        for _ in range(n):
            mtype    = random.choice(moment_pool)
            minute   = random.randint(28, 42) if half_num == 1 else random.randint(58, 72)
            attacker = random.choice([challenger_id, accepter_id])
            keeper   = accepter_id if attacker == challenger_id else challenger_id
            mid      = f"{match_key}_{half_num}_{mtype}"
            _match_moments[mid] = _MatchMoment(mtype, attacker, keeper)
            # Силы команд для расчёта вероятностей в момент
            att_str = sa["att"] if attacker == challenger_id else sb["att"]
            def_str = sa["def_"] if keeper == challenger_id else sb["def_"]
            shared_moments.append({
                "half": half_num, "minute": minute, "type": mtype,
                "attacker_uid": attacker, "keeper_uid": keeper, "moment_id": mid,
                "att_str": att_str, "def_str": def_str,
            })

    # Анимации запускаем как фоновые задачи через create_task —
    # это критически важно: если awaiting gather, бот НЕ обрабатывает
    # другие апдейты (нажатия кнопок) пока идёт анимация.
    # create_task возвращает управление боту сразу, анимации идут параллельно.
    async def _animations_and_cleanup():
        await asyncio.gather(
            _run_match_animation(
                bot=ctx.bot,
                chat_id=accepter_id,
                message_id=q.message.message_id,
                my_name=my_name,
                opp_name=ch_name,
                my_uid=accepter_id,
                stats=stats_ac,
                r_delta=delta_ac,
                coins=coins_ac,
                shared_moments=shared_moments,
                my_sa=sb,    # accepter is "my" perspective
                opp_sa=sa,   # challenger is opponent
            ),
            _run_match_animation(
                bot=ctx.bot,
                chat_id=challenger_id,
                message_id=None,
                my_name=ch_name,
                opp_name=my_name,
                my_uid=challenger_id,
                stats=match_stats,
                r_delta=delta_ch,
                coins=coins_ch,
                shared_moments=shared_moments,
                my_sa=sa,    # challenger is "my" perspective
                opp_sa=sb,   # accepter is opponent
            ),
            return_exceptions=True,
        )
        for mid in [m["moment_id"] for m in shared_moments]:
            _match_moments.pop(mid, None)

    asyncio.create_task(_animations_and_cleanup())


async def cb_fut_decline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Отклонить вызов. fut_decline_{challenger_uid}"""
    q             = update.callback_query
    accepter_id   = q.from_user.id
    challenger_id = int(q.data[len("fut_decline_"):])
    try:
        await q.answer("Вызов отклонён.")
    except Exception:
        pass

    db.clear_pending_action(accepter_id)
    my_name = q.from_user.first_name or "Соперник"

    await q.edit_message_text(
        "❌ Вызов отклонён.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]
        ]),
    )

    # Уведомляем challenger
    try:
        await ctx.bot.send_message(
            chat_id=challenger_id,
            text=f"❌ *{my_name}* отклонил твой вызов.",
            parse_mode="Markdown",
        )
    except Exception:
        pass


async def cb_fut_match_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """История матчей. fut_match_history"""
    q   = update.callback_query
    uid = q.from_user.id
    try:
        await q.answer()
    except Exception:
        pass

    matches = _get_match_history(uid, limit=10)
    if not matches:
        await q.edit_message_text(
            "📋 *История матчей*\n\n_Матчей пока нет._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_match")]
            ]),
        )
        return

    my_rating = _get_fut_rating(uid)
    lines = [f"📋 *История матчей*  ⭐ {my_rating}\n"]
    for m in matches:
        is_p1   = m["player1_id"] == uid
        s_me    = m["score1"] if is_p1 else m["score2"]
        s_opp   = m["score2"] if is_p1 else m["score1"]
        delta   = m["r1_change"] if is_p1 else m["r2_change"]
        opp_id  = m["player2_id"] if is_p1 else m["player1_id"]
        opp_u   = db.get_user(opp_id)
        opp_n   = (opp_u or {}).get("display_name") or f"User{opp_id}"

        if s_me > s_opp:    icon = "🏆"
        elif s_me == s_opp: icon = "🤝"
        else:                icon = "💀"

        d_str = f"+{delta}" if delta >= 0 else str(delta)
        lines.append(f"{icon} {s_me}:{s_opp}  vs *{opp_n[:14]}*  ({d_str} ⭐)")

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ Назад", callback_data="fut_match")]
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — КОНСТАНТЫ И УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════════════════

MARKET_FEE        = 0.05   # 5% комиссия с продажи
MARKET_PAGE       = 8      # карточек на страницу
MAX_CARDS_PER_OFFER = 3
MAX_ACTIVE_LISTINGS = 5


def _card_line(card: dict) -> str:
    pos  = card.get("position", "?")
    rat  = card.get("rating", 0)
    name = card.get("name", "?")
    ver  = card.get("version", "")
    return f"{rat} {pos} {name} ({ver})" if ver else f"{rat} {pos} {name}"


def _card_emoji(rating: int) -> str:
    if rating >= 85: return "🟡"
    if rating >= 80: return "🟢"
    if rating >= 75: return "⚪"
    return "🟤"


def _transfer_card(club_id: int, new_owner_uid: int) -> bool:
    """Move a card (user_club row) to new owner. Returns False if card not found."""
    res = db.get_client().table("user_club").select("id, player_id, user_id").eq("id", club_id).execute()
    if not res.data:
        return False
    db.get_client().table("user_club").update({"user_id": new_owner_uid}).eq("id", club_id).execute()
    return True


def _listing_card_text(card: dict, listing: dict) -> str:
    """Full listing detail text."""
    from datetime import datetime, timezone
    expires_raw = listing.get("expires_at", "")
    try:
        exp_dt  = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        now_dt  = datetime.now(timezone.utc)
        hours_left = max(0, int((exp_dt - now_dt).total_seconds() // 3600))
        exp_str = f"{hours_left}ч"
    except Exception:
        exp_str = "?"
    price = listing.get("price_coins", 0)
    fee   = max(1, round(price * MARKET_FEE))
    seller_gets = price - fee
    return (
        _card_detail_text(card) +
        f"\n💰 *Цена:* {_fmt(price)} монет\n"
        f"💸 *Продавец получит:* {_fmt(seller_gets)} (−5% комиссия)\n"
        f"⏳ *Истекает через:* {exp_str}\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — ГЛАВНОЕ МЕНЮ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_market(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market$"""
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "🛒 *Трансферный рынок*\n\n"
        "Купи или продай игроков.\n"
        "5% комиссия с продажи.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Обзор рынка",   callback_data="fut_market_browse_0"),
             InlineKeyboardButton("📋 Мои лоты",      callback_data="fut_market_my")],
            [InlineKeyboardButton("🤝 Предложения",   callback_data="fut_trade"),
             InlineKeyboardButton("💰 Продать карту", callback_data="fut_market_sell")],
            [InlineKeyboardButton("◀ FUT меню",       callback_data="fut_menu")],
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — ОБЗОР ЛИСТИНГОВ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_market_browse(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_browse_(\d+)$"""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    offset = int(q.data[len("fut_market_browse_"):])

    raw_listings = db.get_fut_listings(limit=MARKET_PAGE, offset=offset)

    # Fetch card info for each listing
    listings: list[tuple[dict, dict]] = []
    for lst in raw_listings:
        card = _get_card_by_id(lst["club_id"])
        if card:
            listings.append((lst, card))

    if not listings and offset == 0:
        await q.edit_message_text(
            "🛒 *Обзор рынка*\n\n_На рынке пока нет предложений._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Продать карту", callback_data="fut_market_sell")],
                [InlineKeyboardButton("◀ Назад",          callback_data="fut_market")],
            ]),
        )
        return

    card_btns = []
    for lst, card in listings:
        emoji = _card_emoji(card["rating"])
        lbl   = f"{emoji} {_card_line(card)} — {_fmt(lst['price_coins'])} 💰"[:64]
        card_btns.append([InlineKeyboardButton(lbl, callback_data=f"fut_market_view_{lst['id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Назад", callback_data=f"fut_market_browse_{offset - MARKET_PAGE}"))
    if len(raw_listings) == MARKET_PAGE:
        nav.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"fut_market_browse_{offset + MARKET_PAGE}"))

    kb = card_btns
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Рынок", callback_data="fut_market")])

    page_num = offset // MARKET_PAGE + 1
    await q.edit_message_text(
        f"🛒 *Рынок* — стр. {page_num}\n_Нажми на лот для подробностей_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — ПРОСМОТР ЛОТА
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_market_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_view_(\d+)$"""
    q          = update.callback_query
    await q.answer()
    uid        = q.from_user.id
    listing_id = int(q.data[len("fut_market_view_"):])

    listing = db.get_fut_listing(listing_id)
    if not listing or listing.get("status") != "active":
        await q.answer("Лот не найден или снят.", show_alert=True)
        return

    card = _get_card_by_id(listing["club_id"])
    if not card:
        await q.answer("Карточка не найдена.", show_alert=True)
        return

    text  = _listing_card_text(card, listing)
    price = listing["price_coins"]

    if listing["seller_uid"] == uid:
        action_row = [InlineKeyboardButton("❌ Снять с продажи", callback_data=f"fut_market_cancel_{listing_id}")]
    else:
        action_row = [InlineKeyboardButton(f"💳 Купить за {_fmt(price)} монет", callback_data=f"fut_market_buy_{listing_id}")]

    await q.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            action_row,
            [InlineKeyboardButton("◀ К рынку", callback_data="fut_market_browse_0")],
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — ПОКУПКА
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_market_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_buy_(\d+)$  — подтверждение покупки"""
    q          = update.callback_query
    await q.answer()
    uid        = q.from_user.id
    listing_id = int(q.data[len("fut_market_buy_"):])

    listing = db.get_fut_listing(listing_id)
    if not listing or listing.get("status") != "active":
        await q.answer("Лот не найден.", show_alert=True)
        return

    if listing["seller_uid"] == uid:
        await q.answer("Нельзя купить собственный лот.", show_alert=True)
        return

    card    = _get_card_by_id(listing["club_id"])
    price   = listing["price_coins"]
    balance = db.get_coins(uid)

    card_name = _card_line(card) if card else "?"
    await q.edit_message_text(
        f"💳 *Подтверждение покупки*\n\n"
        f"Карта: {card_name}\n"
        f"Цена: *{_fmt(price)}* монет\n"
        f"Твой баланс: *{_fmt(balance)}* монет\n\n"
        f"{'✅ Достаточно монет' if balance >= price else '❌ Недостаточно монет'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Купить", callback_data=f"fut_market_buy_ok_{listing_id}")] if balance >= price else [],
            [InlineKeyboardButton("◀ Назад",  callback_data=f"fut_market_view_{listing_id}")],
        ]),
    )


async def cb_fut_market_buy_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_buy_ok_(\d+)$  — выполнить покупку"""
    q          = update.callback_query
    await q.answer()
    uid        = q.from_user.id
    listing_id = int(q.data[len("fut_market_buy_ok_"):])

    listing = db.get_fut_listing(listing_id)
    if not listing or listing.get("status") != "active":
        await q.edit_message_text(
            "❌ Лот уже не активен.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ Рынок", callback_data="fut_market")]]),
        )
        return

    if listing["seller_uid"] == uid:
        await q.answer("Нельзя купить собственный лот.", show_alert=True)
        return

    price     = listing["price_coins"]
    club_id   = listing["club_id"]
    seller_id = listing["seller_uid"]

    ok, _ = db.spend_coins(uid, price)
    if not ok:
        await q.edit_message_text(
            "❌ Недостаточно монет для покупки.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ Рынок", callback_data="fut_market")]]),
        )
        return

    sold = db.mark_listing_sold(listing_id)
    if not sold:
        # Race condition — кто-то успел купить раньше; вернём деньги
        db.add_coins(uid, price)
        await q.edit_message_text(
            "❌ Лот был продан другому игроку. Монеты возвращены.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ Рынок", callback_data="fut_market")]]),
        )
        return

    _transfer_card(club_id, uid)

    fee          = max(1, round(price * MARKET_FEE))
    seller_gets  = price - fee
    db.add_coins(seller_id, seller_gets)

    card = _get_card_by_id(club_id)
    card_name = _card_line(card) if card else "?"

    # Уведомляем продавца
    try:
        seller_user = db.get_user(seller_id)
        buyer_name  = q.from_user.first_name or f"User{uid}"
        await ctx.bot.send_message(
            chat_id=seller_id,
            text=(
                f"💰 *Продажа!*\n\n"
                f"Карта *{card_name}* куплена пользователем {buyer_name}.\n"
                f"Ты получил *{_fmt(seller_gets)}* монет (−5% комиссия)."
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass

    await q.edit_message_text(
        f"✅ *Покупка успешна!*\n\n"
        f"Карта *{card_name}* добавлена в твой клуб.\n"
        f"Потрачено: *{_fmt(price)}* монет.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏟 Мой клуб",  callback_data="fut_club_0_od"),
             InlineKeyboardButton("🛒 Рынок",     callback_data="fut_market")],
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — ПРОДАЖА (выставление лота)
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_market_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_sell$"""
    q = update.callback_query
    await q.answer()
    await _show_sell_page(update, ctx, offset=0)


async def cb_fut_market_sell_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_sellp_(\d+)$"""
    q   = update.callback_query
    await q.answer()
    offset = int(q.data[len("fut_market_sellp_"):])
    await _show_sell_page(update, ctx, offset=offset)


async def _show_sell_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE, offset: int) -> None:
    q   = update.callback_query
    uid = q.from_user.id

    # Карточки уже выставленные на рынок — исключаем
    my_listings = db.get_my_fut_listings(uid)
    listed_ids  = {lst["club_id"] for lst in my_listings}

    all_cards = _sort_cards(_get_club_all(uid), "od")
    available = [c for c in all_cards if c["club_id"] not in listed_ids]

    if not available:
        await q.edit_message_text(
            "🛒 *Выставить на продажу*\n\n"
            "_Все карточки уже выставлены на рынок или клуб пуст._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Рынок", callback_data="fut_market")]
            ]),
        )
        return

    total      = len(available)
    page_cards = available[offset: offset + MARKET_PAGE]
    pages      = (total + MARKET_PAGE - 1) // MARKET_PAGE
    cur_page   = offset // MARKET_PAGE + 1

    card_btns = []
    for c in page_cards:
        emoji = _card_emoji(c["rating"])
        lbl   = f"{emoji} {_card_line(c)}"[:60]
        card_btns.append([InlineKeyboardButton(lbl, callback_data=f"fut_market_sell_pick_{c['club_id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_market_sellp_{offset - MARKET_PAGE}"))
    if offset + MARKET_PAGE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_market_sellp_{offset + MARKET_PAGE}"))

    kb = card_btns
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Рынок", callback_data="fut_market")])

    await q.edit_message_text(
        f"💰 *Выбери карточку для продажи*\n_Стр. {cur_page}/{pages}_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_market_sell_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_sell_pick_(\d+)$"""
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id
    club_id = int(q.data[len("fut_market_sell_pick_"):])

    card = _get_card_by_id(club_id)
    if not card:
        await q.answer("Карточка не найдена.", show_alert=True)
        return

    db.set_pending_action(uid, "fut_market_price", {"club_id": club_id})

    await q.edit_message_text(
        f"💰 *Выставить на продажу*\n\n"
        f"{_card_detail_text(card)}\n"
        f"Введи цену в монетах *(минимум 100)*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="fut_market")]
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — МОИ ЛОТЫ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_market_my(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_my$"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    my_listings = db.get_my_fut_listings(uid)

    if not my_listings:
        await q.edit_message_text(
            "📋 *Мои лоты*\n\n_У тебя нет активных лотов._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Выставить карту", callback_data="fut_market_sell")],
                [InlineKeyboardButton("◀ Рынок",            callback_data="fut_market")],
            ]),
        )
        return

    card_btns = []
    for lst in my_listings:
        card  = _get_card_by_id(lst["club_id"])
        name  = _card_line(card) if card else f"Карта #{lst['club_id']}"
        price = _fmt(lst["price_coins"])
        card_btns.append([
            InlineKeyboardButton(f"{name} — {price} 💰", callback_data=f"fut_market_view_{lst['id']}"),
            InlineKeyboardButton("❌", callback_data=f"fut_market_cancel_{lst['id']}"),
        ])

    card_btns.append([InlineKeyboardButton("◀ Рынок", callback_data="fut_market")])

    await q.edit_message_text(
        f"📋 *Мои лоты* ({len(my_listings)}/{MAX_ACTIVE_LISTINGS})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(card_btns),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТРАНСФЕРНЫЙ РЫНОК — СНЯТИЕ ЛОТА
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_market_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_cancel_(\d+)$  — подтверждение снятия"""
    q          = update.callback_query
    await q.answer()
    listing_id = int(q.data[len("fut_market_cancel_"):])

    await q.edit_message_text(
        "❌ *Снять лот?*\n\nКарта вернётся в твой клуб.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, снять",  callback_data=f"fut_market_cancel_ok_{listing_id}"),
             InlineKeyboardButton("◀ Нет",        callback_data=f"fut_market_view_{listing_id}")],
        ]),
    )


async def cb_fut_market_cancel_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_market_cancel_ok_(\d+)$"""
    q          = update.callback_query
    await q.answer()
    uid        = q.from_user.id
    listing_id = int(q.data[len("fut_market_cancel_ok_"):])

    ok = db.cancel_fut_listing(listing_id, uid)
    if ok:
        await q.edit_message_text(
            "✅ Лот снят с рынка. Карта в твоём клубе.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Мои лоты", callback_data="fut_market_my"),
                 InlineKeyboardButton("◀ Рынок",    callback_data="fut_market")],
            ]),
        )
    else:
        await q.edit_message_text(
            "❌ Не удалось снять лот (уже продан или не твой).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ Рынок", callback_data="fut_market")]]),
        )


# ══════════════════════════════════════════════════════════════════════════════
#  ТОРГОВЫЕ ПРЕДЛОЖЕНИЯ — УТИЛИТЫ
# ══════════════════════════════════════════════════════════════════════════════

async def _show_trade_builder(uid: int, data: dict, q, ctx) -> None:
    """Отображает текущее состояние строящегося предложения."""
    to_name       = data.get("to_name", "?")
    offer_ids     = data.get("offer_club_ids", [])
    offer_coins   = data.get("offer_coins", 0)

    card_lines = []
    for cid in offer_ids:
        card = _get_card_by_id(cid)
        if card:
            card_lines.append(f"• {_card_line(card)}")
        else:
            card_lines.append(f"• Карта #{cid}")

    cards_str = "\n".join(card_lines) if card_lines else "• Нет карточек"

    text = (
        f"🤝 *Новое предложение → {to_name}*\n\n"
        f"Ты предлагаешь:\n{cards_str}\n"
        f"• {_fmt(offer_coins)} 💰\n"
    )

    can_send = bool(offer_ids) or offer_coins > 0

    kb = [
        [InlineKeyboardButton("➕ Добавить карточку", callback_data="fut_trade_addcard_0"),
         InlineKeyboardButton("💰 Монеты",            callback_data="fut_trade_setcoins")],
        [InlineKeyboardButton("📤 Отправить",         callback_data="fut_trade_send")] if can_send else [],
        [InlineKeyboardButton("❌ Отмена",             callback_data="fut_trade_cancel_build")],
    ]
    kb = [row for row in kb if row]

    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ══════════════════════════════════════════════════════════════════════════════
#  ТОРГОВЫЕ ПРЕДЛОЖЕНИЯ — МЕНЮ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_trade(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade$"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    incoming = db.get_incoming_trade_offers(uid)
    n_in     = len(incoming)

    await q.edit_message_text(
        "🤝 *Прямые предложения*\n\n"
        "Предложи сделку любому игроку.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Новое предложение", callback_data="fut_trade_new")],
            [InlineKeyboardButton(f"📥 Входящие ({n_in})", callback_data="fut_trade_inbox"),
             InlineKeyboardButton("📨 Исходящие",          callback_data="fut_trade_outbox")],
            [InlineKeyboardButton("◀ Рынок",               callback_data="fut_market")],
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТОРГОВЫЕ ПРЕДЛОЖЕНИЯ — СОЗДАНИЕ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_trade_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_new$  — redirect to page 0"""
    q = update.callback_query
    await q.answer()
    await _show_trade_player_list(q, q.from_user.id, offset=0)


async def cb_fut_trade_new_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_newp_(\d+)$"""
    q      = update.callback_query
    await q.answer()
    offset = int(q.data[len("fut_trade_newp_"):])
    await _show_trade_player_list(q, q.from_user.id, offset=offset)


async def _show_trade_player_list(q, uid: int, offset: int) -> None:
    """Показывает пагинированный список игроков для выбора получателя трейда."""
    # BUG-33: get_all_users already excludes uid — redundant inner filter removed
    eligible = db.get_all_users(exclude_user_id=uid)

    PAGE = 8
    total      = len(eligible)
    page_users = eligible[offset: offset + PAGE]

    if not page_users:
        await q.edit_message_text(
            "🤝 *Новое предложение*\n\n_Нет других игроков._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_trade")]
            ]),
        )
        return

    kb = []
    for u in page_users:
        name  = (u.get("display_name") or u.get("username") or f"User{u['user_id']}")[:20]
        label = f"👤 {name}"
        kb.append([InlineKeyboardButton(label, callback_data=f"fut_trade_target_{u['user_id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_trade_newp_{offset - PAGE}"))
    if offset + PAGE < total:
        nav.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"fut_trade_newp_{offset + PAGE}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Отмена", callback_data="fut_trade")])

    cur_page = offset // PAGE + 1
    pages    = (total + PAGE - 1) // PAGE
    await q.edit_message_text(
        f"🤝 *Новое предложение*\n_Выбери игрока ({cur_page}/{pages}):_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_trade_target(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_target_(\d+)$  — игрок выбран, начинаем билдер"""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    to_uid = int(q.data[len("fut_trade_target_"):])

    if to_uid == uid:
        await q.answer("Нельзя отправить предложение самому себе.", show_alert=True)
        return

    target = db.get_user(to_uid)
    if not target:
        await q.answer("Игрок не найден.", show_alert=True)
        return

    to_name = target.get("display_name") or target.get("username") or f"User{to_uid}"
    build_data = {
        "to_uid":         to_uid,
        "to_name":        to_name,
        "offer_club_ids": [],
        "offer_coins":    0,
    }
    db.set_pending_action(uid, "fut_trade_build", build_data)
    await _show_trade_builder(uid, build_data, q, ctx)


async def cb_fut_trade_addcard(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_addcard_(\d+)$"""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    offset = int(q.data[len("fut_trade_addcard_"):])

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_trade_build":
        await q.answer("Сессия истекла.", show_alert=True)
        return

    data      = pending.get("data", {})
    offer_ids = set(data.get("offer_club_ids", []))

    all_cards = _sort_cards(_get_club_all(uid), "od")
    available = [c for c in all_cards if c["club_id"] not in offer_ids]
    total     = len(available)
    page_cards = available[offset: offset + MARKET_PAGE]

    card_btns = []
    for c in page_cards:
        emoji = _card_emoji(c["rating"])
        lbl   = f"{emoji} {_card_line(c)}"[:60]
        card_btns.append([InlineKeyboardButton(lbl, callback_data=f"fut_trade_togglecard_{c['club_id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_trade_addcard_{offset - MARKET_PAGE}"))
    if offset + MARKET_PAGE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_trade_addcard_{offset + MARKET_PAGE}"))

    kb = card_btns
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Назад к предложению", callback_data="fut_trade_builder")])

    await q.edit_message_text(
        f"➕ *Выбери карточку для предложения*\n"
        f"_(Максимум {MAX_CARDS_PER_OFFER} карт)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_trade_togglecard(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_togglecard_(\d+)$"""
    q       = update.callback_query
    uid     = q.from_user.id
    club_id = int(q.data[len("fut_trade_togglecard_"):])

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_trade_build":
        await q.answer("Сессия истекла.", show_alert=True)
        return

    data      = pending.get("data", {})
    offer_ids = list(data.get("offer_club_ids", []))

    if club_id in offer_ids:
        offer_ids.remove(club_id)
        await q.answer("Карточка убрана из предложения.")
    else:
        if len(offer_ids) >= MAX_CARDS_PER_OFFER:
            await q.answer(f"Максимум {MAX_CARDS_PER_OFFER} карт в предложении.", show_alert=True)
            return
        offer_ids.append(club_id)
        await q.answer("Карточка добавлена в предложение.")

    data["offer_club_ids"] = offer_ids
    db.set_pending_action(uid, "fut_trade_build", data)
    await _show_trade_builder(uid, data, q, ctx)


async def cb_fut_trade_builder(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_builder$  — вернуться к построителю"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_trade_build":
        await q.answer("Сессия истекла.", show_alert=True)
        return
    await _show_trade_builder(uid, pending.get("data", {}), q, ctx)


async def cb_fut_trade_setcoins(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_setcoins$"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_trade_build":
        await q.answer("Сессия истекла.", show_alert=True)
        return

    # сохраняем текущие данные предложения, переходим к вводу монет
    build_data = pending.get("data", {})
    db.set_pending_action(uid, "fut_trade_coins", build_data)

    balance = db.get_coins(uid)
    await q.edit_message_text(
        f"💰 *Монеты в предложении*\n\n"
        f"Твой баланс: *{_fmt(balance)}* монет\n"
        f"Введи количество монет (0 — без монет):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="fut_trade_builder")]
        ]),
    )


async def cb_fut_trade_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_send$"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_trade_build":
        await q.answer("Сессия истекла.", show_alert=True)
        return

    data        = pending.get("data", {})
    to_uid      = data.get("to_uid")
    to_name     = data.get("to_name", "?")
    offer_ids   = data.get("offer_club_ids", [])
    offer_coins = data.get("offer_coins", 0)

    if not offer_ids and offer_coins <= 0:
        await q.answer("Предложение пустое — добавь карточки или монеты.", show_alert=True)
        return

    # BUG-27: escrow coins at send time so recipient can't be misled
    if offer_coins > 0:
        ok, _ = db.spend_coins(uid, offer_coins)
        if not ok:
            await q.answer("Недостаточно монет.", show_alert=True)
            return

    db.create_trade_offer(
        from_uid=uid, to_uid=to_uid,
        offer_club_ids=offer_ids, offer_coins=offer_coins,
        want_club_ids=[], want_coins=0,
    )
    db.clear_pending_action(uid)

    my_name = q.from_user.first_name or f"User{uid}"
    try:
        await ctx.bot.send_message(
            chat_id=to_uid,
            text=(
                f"📬 *Новое предложение от {my_name}!*\n\n"
                f"Зайди в FUT → 🛒 Рынок → 🤝 Предложения, чтобы посмотреть."
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass

    await q.edit_message_text(
        f"✅ *Предложение отправлено {to_name}!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ Рынок", callback_data="fut_market")]
        ]),
    )


async def cb_fut_trade_cancel_build(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_cancel_build$  — отмена построителя"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    db.clear_pending_action(uid)
    q.data = "fut_trade"
    await cb_fut_trade(update, ctx)


# ══════════════════════════════════════════════════════════════════════════════
#  ТОРГОВЫЕ ПРЕДЛОЖЕНИЯ — ВХОДЯЩИЕ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_trade_inbox(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_inbox$"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    offers = db.get_incoming_trade_offers(uid)

    if not offers:
        await q.edit_message_text(
            "📥 *Входящие предложения*\n\n_Нет новых предложений._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_trade")]
            ]),
        )
        return

    rows = []
    for offer in offers:
        from_user = db.get_user(offer["from_uid"])
        from_name = (from_user or {}).get("display_name") or f"User{offer['from_uid']}"
        n_cards   = len(offer.get("offer_club_ids") or [])
        coins     = offer.get("offer_coins", 0)
        summary   = f"{n_cards} карт" + (f" + {_fmt(coins)} 💰" if coins else "")
        rows.append([InlineKeyboardButton(
            f"{from_name[:16]}: {summary}",
            callback_data=f"fut_trade_view_{offer['id']}",
        )])

    rows.append([InlineKeyboardButton("◀ Назад", callback_data="fut_trade")])

    await q.edit_message_text(
        f"📥 *Входящие предложения* ({len(offers)})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_trade_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_view_(\d+)$"""
    q        = update.callback_query
    await q.answer()
    uid      = q.from_user.id
    offer_id = int(q.data[len("fut_trade_view_"):])

    offer = db.get_trade_offer(offer_id)
    if not offer:
        await q.answer("Предложение не найдено.", show_alert=True)
        return

    from_user = db.get_user(offer["from_uid"])
    from_name = (from_user or {}).get("display_name") or f"User{offer['from_uid']}"
    offer_ids = offer.get("offer_club_ids") or []
    coins     = offer.get("offer_coins", 0)

    card_lines = []
    for cid in offer_ids:
        card = _get_card_by_id(cid)
        if card:
            card_lines.append(f"• {_card_line(card)}")

    cards_str = "\n".join(card_lines) if card_lines else "• Нет карточек"

    text = (
        f"🤝 *Предложение от {from_name}*\n\n"
        f"Предлагает:\n{cards_str}\n"
        f"• {_fmt(coins)} 💰\n"
    )

    is_receiver = (offer.get("to_uid") == uid)
    status      = offer.get("status", "")

    if is_receiver and status == "pending":
        kb = [
            [InlineKeyboardButton("✅ Принять",   callback_data=f"fut_trade_accept_{offer_id}"),
             InlineKeyboardButton("❌ Отклонить", callback_data=f"fut_trade_decline_{offer_id}")],
            [InlineKeyboardButton("◀ Назад",      callback_data="fut_trade_inbox")],
        ]
    else:
        kb = [[InlineKeyboardButton("◀ Назад", callback_data="fut_trade_inbox")]]

    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_trade_accept(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_accept_(\d+)$"""
    q        = update.callback_query
    await q.answer()
    uid      = q.from_user.id
    offer_id = int(q.data[len("fut_trade_accept_"):])

    offer = db.get_trade_offer(offer_id)
    if not offer or offer.get("status") != "pending":
        await q.edit_message_text(
            "❌ Предложение уже не активно.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ Назад", callback_data="fut_trade")]]),
        )
        return

    if offer.get("to_uid") != uid:
        await q.answer("Это предложение не для тебя.", show_alert=True)
        return

    from_uid  = offer["from_uid"]
    offer_ids = offer.get("offer_club_ids") or []
    coins     = offer.get("offer_coins", 0)

    # BUG-26: verify cards still belong to from_uid before transferring
    if offer_ids:
        res = db.get_client().table("user_club").select("id, user_id").in_("id", offer_ids).execute()
        owned = {row["id"] for row in (res.data or []) if row["user_id"] == from_uid}
        invalid = [cid for cid in offer_ids if cid not in owned]
        if invalid:
            db.mark_trade_offer_accepted(offer_id, uid)  # close the offer so it can't be retried
            await q.edit_message_text(
                "❌ Сделка невозможна: часть карточек была продана или передана отправителем.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ Назад", callback_data="fut_trade")]]),
            )
            return

    # BUG-27: coins were escrowed (deducted) at send time — just credit accepter
    if coins > 0:
        db.add_coins(uid, coins)

    # Переносим карточки от from_uid → uid
    for cid in offer_ids:
        _transfer_card(cid, uid)

    db.mark_trade_offer_accepted(offer_id, uid)

    my_name = q.from_user.first_name or f"User{uid}"
    try:
        await ctx.bot.send_message(
            chat_id=from_uid,
            text=f"✅ *{my_name}* принял твоё торговое предложение!",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    await q.edit_message_text(
        "✅ *Предложение принято!* Карточки перешли в твой клуб.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏟 Мой клуб", callback_data="fut_club_0_od"),
             InlineKeyboardButton("◀ Рынок",     callback_data="fut_market")],
        ]),
    )


async def cb_fut_trade_decline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_decline_(\d+)$"""
    q        = update.callback_query
    await q.answer()
    uid      = q.from_user.id
    offer_id = int(q.data[len("fut_trade_decline_"):])

    # BUG-27: refund escrowed coins to sender on decline
    offer = db.get_trade_offer(offer_id)
    ok = db.decline_trade_offer(offer_id, uid)
    if ok and offer and offer.get("offer_coins", 0) > 0:
        db.add_coins(offer["from_uid"], offer["offer_coins"])

    msg = "✅ Предложение отклонено." if ok else "❌ Не удалось отклонить предложение."

    await q.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ Входящие", callback_data="fut_trade_inbox")]
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТОРГОВЫЕ ПРЕДЛОЖЕНИЯ — ИСХОДЯЩИЕ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_trade_outbox(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_outbox$"""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    offers = db.get_outgoing_trade_offers(uid)

    if not offers:
        await q.edit_message_text(
            "📨 *Исходящие предложения*\n\n_Нет активных предложений._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_trade")]
            ]),
        )
        return

    rows = []
    for offer in offers:
        to_user  = db.get_user(offer["to_uid"])
        to_name  = (to_user or {}).get("display_name") or f"User{offer['to_uid']}"
        n_cards  = len(offer.get("offer_club_ids") or [])
        coins    = offer.get("offer_coins", 0)
        summary  = f"{n_cards} карт" + (f" + {_fmt(coins)} 💰" if coins else "")
        rows.append([
            InlineKeyboardButton(f"→ {to_name[:16]}: {summary}", callback_data=f"fut_trade_view_{offer['id']}"),
            InlineKeyboardButton("❌", callback_data=f"fut_trade_cancel_{offer['id']}"),
        ])

    rows.append([InlineKeyboardButton("◀ Назад", callback_data="fut_trade")])

    await q.edit_message_text(
        f"📨 *Исходящие предложения* ({len(offers)})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_trade_cancel_offer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_trade_cancel_(\d+)$  — отменить исходящее предложение"""
    q        = update.callback_query
    await q.answer()
    uid      = q.from_user.id
    offer_id = int(q.data[len("fut_trade_cancel_"):])

    # BUG-27: refund escrowed coins back to sender on cancel
    offer = db.get_trade_offer(offer_id)
    ok = db.cancel_trade_offer(offer_id, uid)
    if ok and offer and offer.get("offer_coins", 0) > 0:
        db.add_coins(uid, offer["offer_coins"])

    msg = "✅ Предложение отменено." if ok else "❌ Не удалось отменить."

    await q.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ Исходящие", callback_data="fut_trade_outbox")]
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ТЕКСТОВЫЙ ХЕНДЛЕР — ввод цены/получателя/монет (pending_action)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_fut_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Вызывается из основного text-хендлера бота.
    Возвращает True если обработал, False если не наш pending_action.
    """
    uid     = update.effective_user.id
    text    = (update.message.text or "").strip()
    pending = db.get_pending_action(uid)
    if not pending:
        return False

    action = pending.get("action")

    # ── Ввод цены для листинга ────────────────────────────────────────────────
    if action == "fut_market_price":
        data    = pending.get("data", {})
        club_id = data.get("club_id")

        try:
            price = int(text.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("❌ Введи целое число, например: 5000")
            return True

        if price < 100:
            await update.message.reply_text("❌ Минимальная цена — 100 монет.")
            return True

        # Проверяем лимит листингов
        my_listings = db.get_my_fut_listings(uid)
        if len(my_listings) >= MAX_ACTIVE_LISTINGS:
            await update.message.reply_text(
                f"❌ Максимум {MAX_ACTIVE_LISTINGS} активных лотов. Сначала сними один."
            )
            db.clear_pending_action(uid)
            return True

        # Проверяем не выставлена ли эта карточка уже
        if any(lst["club_id"] == club_id for lst in my_listings):
            await update.message.reply_text("❌ Эта карточка уже выставлена на продажу.")
            db.clear_pending_action(uid)
            return True

        db.create_fut_listing(uid, club_id, price)
        db.clear_pending_action(uid)

        card     = _get_card_by_id(club_id)
        card_name = _card_line(card) if card else f"Карта #{club_id}"

        await update.message.reply_text(
            f"✅ Карта *{card_name}* выставлена за *{_fmt(price)} монет*!\n"
            f"Лот активен 48 часов.",
            parse_mode="Markdown",
        )
        return True

    # ── Ввод монет для предложения ────────────────────────────────────────────
    if action == "fut_trade_coins":
        build_data = pending.get("data", {})

        try:
            coins = int(text.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("❌ Введи целое число >= 0")
            return True

        if coins < 0:
            await update.message.reply_text("❌ Количество монет не может быть отрицательным.")
            return True

        if coins > 0:
            balance = db.get_coins(uid)
            if balance < coins:
                await update.message.reply_text(
                    f"❌ Недостаточно монет. Баланс: {_fmt(balance)} 💰"
                )
                return True

        build_data["offer_coins"] = coins
        db.set_pending_action(uid, "fut_trade_build", build_data)

        to_name  = build_data.get("to_name", "?")
        offer_ids = build_data.get("offer_club_ids", [])
        card_lines = []
        for cid in offer_ids:
            card = _get_card_by_id(cid)
            if card:
                card_lines.append(f"• {_card_line(card)}")
        cards_str = "\n".join(card_lines) if card_lines else "• Нет карточек"

        can_send = bool(offer_ids) or coins > 0
        kb = [
            [InlineKeyboardButton("➕ Добавить карточку", callback_data="fut_trade_addcard_0"),
             InlineKeyboardButton("💰 Монеты",            callback_data="fut_trade_setcoins")],
            [InlineKeyboardButton("📤 Отправить",         callback_data="fut_trade_send")] if can_send else [],
            [InlineKeyboardButton("❌ Отмена",             callback_data="fut_trade_cancel_build")],
        ]
        kb = [row for row in kb if row]

        await update.message.reply_text(
            f"🤝 *Новое предложение → {to_name}*\n\n"
            f"Ты предлагаешь:\n{cards_str}\n"
            f"• {_fmt(coins)} 💰",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return True

    return False


# ══════════════════════════════════════════════════════════════════════════════
#  ДРАФТ — КОНСТАНТЫ
# ══════════════════════════════════════════════════════════════════════════════

DRAFT_MIN_OVR   = 82
DRAFT_MATCHES   = 3         # solo: number of matches
DRAFT_PICK_N    = 3         # choices per slot
DRAFT_ENTRY_FEE = 300       # coins entry fee

# Rewards per wins (solo)
DRAFT_REWARDS: dict[int, tuple[int, bool]] = {
    0: (100,   False),   # (coins, exclusive_pack)
    1: (400,   False),
    2: (900,   False),
    3: (2000,  True),    # 3/3: big coins + exclusive pack (3 cards added to club)
}
DRAFT_PACK_CARDS   = 3    # cards in exclusive pack
DRAFT_PACK_MIN_OVR = 83   # minimum OVR for pack cards

# Position group → fut_players positions mapping
DRAFT_POS_MAP: dict[str, list[str]] = {
    "GK":  ["GK"],
    "DEF": ["CB", "LB", "RB", "LWB", "RWB"],
    "MID": ["CDM", "CM", "CAM", "LM", "RM"],
    "ATT": ["LW", "RW", "CF", "ST"],
}

# Multi-draft rooms (module-level, in-memory)
_draft_rooms: dict[str, dict] = {}


# ══════════════════════════════════════════════════════════════════════════════
#  ДРАФТ — ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════════════════════════════════

def _draft_get_options(group: str, exclude_ids: set[int]) -> list[dict]:
    """Query fut_players for DRAFT_PICK_N random players matching the group."""
    valid_positions = DRAFT_POS_MAP.get(group, [])
    res = (
        db.get_client().table("fut_players")
        .select("id, name, club, nation, position, rating, version, pac, sho, pas, dri, def, phy, league")
        .gte("rating", DRAFT_MIN_OVR)
        .in_("position", valid_positions)
        .execute()
    )
    players = [p for p in (res.data or []) if p["id"] not in exclude_ids and _is_male_player(p)]
    return random.sample(players, min(DRAFT_PICK_N, len(players)))


def _draft_build_sa(picks: dict) -> dict:
    """Build att/def_/ovr/chem/placed from picks dict {slot_name: player_data}."""
    att_vals: list[float] = []
    def_vals: list[float] = []
    gk_vals:  list[float] = []
    scorers:  list[str]   = []
    all_names: list[str]  = []
    pas_sum = 0

    for slot_name, player in picks.items():
        pos   = player.get("position", "")
        group = DRAFT_POS_MAP.get("GK", [])
        # Determine group from slot FORMATIONS context if possible, else from position
        if pos == "GK":
            gk_vals.append((player["def"] + player["phy"] + player["pas"]) / 3)
        elif pos in ("CB", "LB", "RB", "LWB", "RWB"):
            def_vals.append((player["def"] + player["phy"]) / 2)
        elif pos in ("CDM", "CM", "CAM", "LM", "RM"):
            att_vals.append((player["pac"] + player["sho"] + player["dri"]) / 3)
            def_vals.append((player["def"] + player["phy"]) / 2)
        else:  # ATT
            att_vals.append((player["pac"] + player["sho"] + player["dri"]) / 3)

        short = _short_name(player.get("name", "Игрок"))
        all_names.append(short)
        if pos != "GK":
            scorers.append(short)
        pas_sum += player.get("pas", 75)

    att  = round(sum(att_vals) / len(att_vals) * 1.05) if att_vals else 75
    if def_vals or gk_vals:
        d_avg = sum(def_vals) / max(len(def_vals), 1) if def_vals else 75
        g_avg = sum(gk_vals)  / max(len(gk_vals),  1) if gk_vals  else 75
        def_  = round(d_avg * 0.7 + g_avg * 0.3)
    else:
        def_ = 75
    ovr     = round(sum(p["rating"] for p in picks.values()) / max(len(picks), 1))
    chem    = 70
    placed  = len(picks)
    pas_avg = round(pas_sum / max(placed, 1))
    gk_name = next(
        (_short_name(p["name"]) for p in picks.values() if p.get("position") == "GK"),
        "Вратарь",
    )

    return {
        "att": att, "def_": def_, "ovr": ovr, "chem": chem, "placed": placed,
        "scorers":   scorers   or all_names or ["Игрок"],
        "all_names": all_names or ["Игрок"],
        "gk_name":  gk_name,
        "pas_avg":  pas_avg,
    }


def _draft_bot_sa(min_ovr: int, max_ovr: int) -> dict:
    """Build a random bot team SA by sampling fut_players in the OVR range."""
    res = (
        db.get_client().table("fut_players")
        .select("position, pac, sho, pas, dri, def, phy, rating, league")
        .gte("rating", min_ovr).lte("rating", max_ovr)
        .execute()
    )
    players = [p for p in (res.data or []) if _is_male_player(p)]
    if not players:
        return {"att": min_ovr - 5, "def_": min_ovr - 5, "ovr": min_ovr,
                "chem": 60, "placed": 11,
                "scorers": ["Бот"], "all_names": ["Бот"], "gk_name": "Бот", "pas_avg": 70}

    sample = random.sample(players, min(11, len(players)))
    att_vals, def_vals, gk_vals = [], [], []
    pas_sum = 0
    for p in sample:
        pos = p.get("position", "")
        if pos == "GK":
            gk_vals.append((p["def"] + p["phy"] + p["pas"]) / 3)
        elif pos in ("CB", "LB", "RB", "LWB", "RWB"):
            def_vals.append((p["def"] + p["phy"]) / 2)
        elif pos in ("CDM", "CM", "CAM", "LM", "RM"):
            att_vals.append((p["pac"] + p["sho"] + p["dri"]) / 3)
            def_vals.append((p["def"] + p["phy"]) / 2)
        else:
            att_vals.append((p["pac"] + p["sho"] + p["dri"]) / 3)
        pas_sum += p.get("pas", 70)

    att  = round(sum(att_vals) / len(att_vals)) if att_vals else min_ovr - 5
    if def_vals or gk_vals:
        d_avg = sum(def_vals) / max(len(def_vals), 1) if def_vals else min_ovr - 5
        g_avg = sum(gk_vals)  / max(len(gk_vals),  1) if gk_vals  else min_ovr - 5
        def_  = round(d_avg * 0.7 + g_avg * 0.3)
    else:
        def_ = min_ovr - 5
    ovr     = round(sum(p["rating"] for p in sample) / len(sample))
    pas_avg = round(pas_sum / max(len(sample), 1))

    return {
        "att": att, "def_": def_, "ovr": ovr, "chem": 60, "placed": len(sample),
        "scorers": ["Бот"], "all_names": ["Бот"], "gk_name": "Бот", "pas_avg": pas_avg,
    }


def _draft_slot_order(formation: str) -> list[tuple[str, str]]:
    """Returns list of (slot_name, group) in pick order: GK first, then DEF, MID, ATT."""
    slots = FORMATIONS[formation]["slots"]
    order: list[tuple[str, str]] = []
    for group in ["GK", "DEF", "MID", "ATT"]:
        for slot_name, g in slots.items():
            if g == group:
                order.append((slot_name, g))
    return order


# ══════════════════════════════════════════════════════════════════════════════
#  ДРАФТ — СОЛО ФЛОУ
# ══════════════════════════════════════════════════════════════════════════════

async def _show_draft_pick(q, data: dict) -> None:
    """Display current pick choice for a draft slot."""
    slot_order = data["slot_order"]        # list of [slot_name, group]
    slot_idx   = data["slot_idx"]
    slot_name, group = slot_order[slot_idx]
    options    = data["current_options"]
    total      = len(slot_order)

    group_name = GROUP_NAME.get(group, group)
    lines = [
        f"🎲 *Драфт — Слот {slot_idx + 1}/{total}*\n",
        f"📌 Позиция: `{slot_name}` ({group_name})\n",
        "_Выбери одного из трёх:_",
    ]
    text = "\n".join(lines)

    kb = []
    for p in options:
        emoji = _card_emoji(p["rating"])
        ver   = p.get("version", "")
        ver_s = f" ({ver})" if ver else ""
        lbl   = f"{emoji} {p['rating']} {p['position']} {p['name'][:16]}{ver_s}"
        kb.append([InlineKeyboardButton(lbl, callback_data=f"fut_draft_pick_{p['id']}")])
    kb.append([InlineKeyboardButton("❌ Отмена", callback_data="fut_menu")])

    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def _show_draft_mpick(q, data: dict) -> None:
    """Display current pick choice for a multi-draft slot."""
    slot_order = data["slot_order"]
    slot_idx   = data["slot_idx"]
    slot_name, group = slot_order[slot_idx]
    options    = data["current_options"]
    total      = len(slot_order)

    group_name = GROUP_NAME.get(group, group)
    lines = [
        f"🎲 *Мульти-Драфт — Слот {slot_idx + 1}/{total}*\n",
        f"📌 Позиция: `{slot_name}` ({group_name})\n",
        "_Выбери одного из трёх:_",
    ]
    text = "\n".join(lines)

    kb = []
    for p in options:
        emoji = _card_emoji(p["rating"])
        ver   = p.get("version", "")
        ver_s = f" ({ver})" if ver else ""
        lbl   = f"{emoji} {p['rating']} {p['position']} {p['name'][:16]}{ver_s}"
        kb.append([InlineKeyboardButton(lbl, callback_data=f"fut_draft_mpick_{p['id']}")])
    kb.append([InlineKeyboardButton("❌ Отмена", callback_data="fut_menu")])

    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_draft(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft$ — main draft menu."""
    q = update.callback_query
    await q.answer()

    await q.edit_message_text(
        "🎲 *FUT Драфт*\n\n"
        "Выбери режим:\n"
        "*Соло* — собери команду и сыграй 3 матча против бота.\n"
        "*Мульти* — пригласи соперника, оба драфтите, потом матч.\n"
        "*Турнир* — 16 игроков, один драфт, 4 раунда до победителя.\n\n"
        f"💰 Взнос соло/мульти: *{_fmt(DRAFT_ENTRY_FEE)}* монет\n"
        f"💰 Взнос турнира: *{_fmt(TOUR_ENTRY_FEE)}* монет",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Соло",   callback_data="fut_draft_solo"),
             InlineKeyboardButton("⚔️ Мульти", callback_data="fut_draft_multi")],
            [InlineKeyboardButton("🏆 Турнир (16 игроков)", callback_data="fut_tour")],
            [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")],
        ]),
    )


async def cb_fut_draft_solo_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_solo$ — check fee, show formation picker."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    coins = db.get_coins(uid)
    if coins < DRAFT_ENTRY_FEE:
        await q.edit_message_text(
            f"❌ Недостаточно монет!\n\n"
            f"Нужно: *{_fmt(DRAFT_ENTRY_FEE)}* 💰\n"
            f"Твой баланс: *{_fmt(coins)}* 💰",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_draft")]
            ]),
        )
        return

    items = [
        InlineKeyboardButton(f["label"], callback_data=f"fut_draft_form_{key}")
        for key, f in FORMATIONS.items()
    ]
    rows = [items[i:i+2] for i in range(0, len(items), 2)]
    rows.append([InlineKeyboardButton("◀ Отмена", callback_data="fut_draft")])

    await q.edit_message_text(
        f"🎯 *Соло-Драфт*\n\n"
        f"Выбери схему расстановки:\n"
        f"_Взнос: {_fmt(DRAFT_ENTRY_FEE)} 💰_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_draft_form(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_form_(\w+)$ — formation chosen, deduct fee, begin picking."""
    q        = update.callback_query
    uid      = q.from_user.id
    form_key = q.data[len("fut_draft_form_"):]

    if form_key not in FORMATIONS:
        await q.answer("Неизвестная схема.", show_alert=True)
        return

    ok, _ = db.spend_coins(uid, DRAFT_ENTRY_FEE)
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True)
        return

    await q.answer()

    slot_order = _draft_slot_order(form_key)
    first_slot, first_group = slot_order[0]
    options = _draft_get_options(first_group, set())

    data: dict = {
        "formation":        form_key,
        "slot_order":       [[s, g] for s, g in slot_order],
        "slot_idx":         0,
        "picks":            {},
        "used_ids":         [p["id"] for p in options],
        "current_options":  options,
        "phase":            "picking",
        "match_idx":        0,
        "wins":             0,
        "match_log":        [],
    }
    db.set_pending_action(uid, "fut_draft_solo", data)
    await _show_draft_pick(q, data)


async def cb_fut_draft_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_pick_(\d+)$ — player picked in solo draft."""
    q         = update.callback_query
    await q.answer()
    uid       = q.from_user.id
    player_id = int(q.data[len("fut_draft_pick_"):])

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_draft_solo":
        await q.answer("Сессия истекла. Начни заново.", show_alert=True)
        return

    data = pending["data"]
    options = data.get("current_options", [])

    # Find picked player
    picked = next((p for p in options if p["id"] == player_id), None)
    if not picked:
        await q.answer("Игрок не найден. Выбери из списка.", show_alert=True)
        return

    slot_order = data["slot_order"]
    slot_idx   = data["slot_idx"]
    slot_name  = slot_order[slot_idx][0]

    # Save pick
    data["picks"][slot_name] = picked
    data["used_ids"].append(player_id)
    data["slot_idx"] = slot_idx + 1

    if data["slot_idx"] < len(slot_order):
        # Get options for next slot
        next_slot, next_group = slot_order[data["slot_idx"]]
        next_opts = _draft_get_options(next_group, set(data["used_ids"]))
        data["current_options"] = next_opts
        data["used_ids"].extend(p["id"] for p in next_opts)
        db.set_pending_action(uid, "fut_draft_solo", data)
        await _show_draft_pick(q, data)
    else:
        # All 11 picked — show summary
        data["phase"] = "playing"
        data["current_options"] = []
        db.set_pending_action(uid, "fut_draft_solo", data)

        form_label = FORMATIONS[data["formation"]]["label"]
        sa         = _draft_build_sa(data["picks"])

        lines = [
            f"✅ *Команда собрана!* ({form_label})\n",
            f"⭐ OVR: *{sa['ovr']}*  ATT: *{sa['att']}*  DEF: *{sa['def_']}*\n",
            "Твои игроки:\n",
        ]
        for slot_name_k, p in data["picks"].items():
            emoji = _card_emoji(p["rating"])
            lines.append(f"• `{slot_name_k}` {emoji} {p['rating']} {p['name']}")

        await q.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶ Начать матчи", callback_data="fut_draft_play")],
            ]),
        )


async def cb_fut_draft_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_play$ — announce next match."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_draft_solo":
        await q.answer("Сессия истекла. Начни заново.", show_alert=True)
        return

    data      = pending["data"]
    match_idx = data["match_idx"]

    if match_idx >= DRAFT_MATCHES:
        # Should not happen, but redirect to reward
        await cb_fut_draft_reward(update, ctx)
        return

    bot_ranges = [(82, 84), (83, 85), (84, 86)]
    mn, mx = bot_ranges[min(match_idx, len(bot_ranges) - 1)]
    bot_ovr = round((mn + mx) / 2)

    await q.edit_message_text(
        f"⚔️ *Матч {match_idx + 1}/{DRAFT_MATCHES}*\n\n"
        f"🔵 Ты  vs  🤖 Бот OVR {bot_ovr}\n\n"
        "_Готов?_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Играть", callback_data="fut_draft_match")],
        ]),
    )


async def cb_fut_draft_match(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_match$ — play one draft match with full animation."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_draft_solo":
        await q.answer("Сессия истекла.", show_alert=True)
        return

    data      = pending["data"]
    match_idx = data["match_idx"]

    sa = _draft_build_sa(data["picks"])

    bot_ranges = [(82, 84), (83, 85), (84, 86)]
    mn, mx  = bot_ranges[min(match_idx, len(bot_ranges) - 1)]
    bot_sa  = _draft_bot_sa(mn, mx)
    bot_ovr = round((mn + mx) / 2)

    match_stats = _simulate_match(sa, bot_sa)
    my_score    = match_stats["score_a"]
    bot_score   = match_stats["score_b"]
    won         = my_score > bot_score

    if won:
        data["wins"] += 1

    data["match_log"].append({"my": my_score, "bot": bot_score})
    data["match_idx"] = match_idx + 1
    db.set_pending_action(uid, "fut_draft_solo", data)

    is_last = data["match_idx"] >= DRAFT_MATCHES

    # Создаём интерактивные моменты (бот сразу делает выбор)
    match_key     = f"draft_{uid}_{match_idx}"
    shared_moments = _make_shared_moments_vs_bot(uid, sa, bot_sa, match_key)

    # Финальная кнопка после анимации
    if is_last:
        after_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 Получить награду", callback_data="fut_draft_reward")],
        ])
    else:
        after_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Следующий матч", callback_data="fut_draft_play")],
        ])

    bot_name = f"🤖 Бот OVR {bot_ovr}"

    # Показываем «матч начинается» и сразу запускаем анимацию фоном
    placeholder = await q.edit_message_text(
        f"⚽ *Матч {match_idx + 1}/{DRAFT_MATCHES}* — начинается...",
        parse_mode="Markdown",
    )
    message_id = placeholder.message_id if placeholder else q.message.message_id

    async def _anim_and_cleanup():
        await _run_match_animation(
            bot=ctx.bot,
            chat_id=uid,
            message_id=message_id,
            my_name="Ты",
            opp_name=bot_name,
            my_uid=uid,
            stats=match_stats,
            r_delta=0,
            coins=0,
            shared_moments=shared_moments,
            after_kb=after_kb,
            my_sa=sa,
            opp_sa=bot_sa,
        )
        for m in shared_moments:
            _match_moments.pop(m["moment_id"], None)

    asyncio.create_task(_anim_and_cleanup())


async def cb_fut_draft_reward(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_reward$ — give final reward."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_draft_solo":
        await q.answer("Сессия не найдена.", show_alert=True)
        return

    data = pending["data"]
    # BUG-8: clear FIRST so a double-tap won't find the session anymore
    db.clear_pending_action(uid)

    wins = data.get("wins", 0)
    coins_reward, get_pack = DRAFT_REWARDS.get(wins, (0, False))

    if coins_reward > 0:
        db.add_coins(uid, coins_reward)

    pack_lines: list[str] = []
    if get_pack:
        res = (
            db.get_client().table("fut_players")
            .select("id, name, rating, position, league")
            .gte("rating", DRAFT_PACK_MIN_OVR)
            .execute()
        )
        pack_pool = [p for p in (res.data or []) if _is_male_player(p)]
        if pack_pool:
            pack_cards = random.sample(pack_pool, min(DRAFT_PACK_CARDS, len(pack_pool)))
            _add_to_club(uid, [c["id"] for c in pack_cards])
            pack_lines.append("\n🎁 *Эксклюзивный пак — получено:*")
            for c in pack_cards:
                emoji = _card_emoji(c["rating"])
                pack_lines.append(f"  {emoji} {c['rating']} {c['position']} {c['name']}")

    log_lines = []
    for i, m in enumerate(data.get("match_log", [])):
        my_s, bot_s = m["my"], m["bot"]
        ico = "✅" if my_s > bot_s else ("🤝" if my_s == bot_s else "❌")
        log_lines.append(f"• Матч {i + 1}: {my_s}:{bot_s} {ico}")

    results_block = "\n".join(log_lines) if log_lines else "—"
    pack_block    = "\n".join(pack_lines) if pack_lines else ""

    await q.edit_message_text(
        f"🏆 *Драфт завершён!*\n\n"
        f"Результаты:\n{results_block}\n\n"
        f"Побед: *{wins}/{DRAFT_MATCHES}*\n\n"
        f"💰 Награда: *{_fmt(coins_reward)} монет*"
        f"{pack_block}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")],
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ДРАФТ — МУЛЬТИ ФЛОУ
# ══════════════════════════════════════════════════════════════════════════════

async def _show_draft_multi_player_list(q, uid: int, offset: int) -> None:
    """Paginated player list for multi-draft invite."""
    eligible   = db.get_all_users(exclude_user_id=uid)  # BUG-33: already excludes uid
    PAGE       = 8
    total      = len(eligible)
    page_users = eligible[offset: offset + PAGE]

    if not page_users:
        await q.edit_message_text(
            "⚔️ *Мульти-Драфт*\n\n_Нет других игроков._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_draft")]
            ]),
        )
        return

    kb = []
    for u in page_users:
        name  = (u.get("display_name") or u.get("username") or f"User{u['user_id']}")[:20]
        label = f"👤 {name}"
        kb.append([InlineKeyboardButton(label, callback_data=f"fut_draft_multi_inv_{u['user_id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_draft_multi_invp_{offset - PAGE}"))
    if offset + PAGE < total:
        nav.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"fut_draft_multi_invp_{offset + PAGE}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Отмена", callback_data="fut_draft")])

    cur_page = offset // PAGE + 1
    pages    = (total + PAGE - 1) // PAGE
    await q.edit_message_text(
        f"⚔️ *Мульти-Драфт*\n_Выбери соперника ({cur_page}/{pages}):_\n"
        f"_Взнос: {_fmt(DRAFT_ENTRY_FEE)} 💰_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_draft_multi(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_multi$ — show player picker."""
    q = update.callback_query
    await q.answer()
    await _show_draft_multi_player_list(q, q.from_user.id, offset=0)


async def cb_fut_draft_multi_invpage(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_multi_invp_(\d+)$"""
    q      = update.callback_query
    await q.answer()
    offset = int(q.data[len("fut_draft_multi_invp_"):])
    await _show_draft_multi_player_list(q, q.from_user.id, offset=offset)


async def cb_fut_draft_multi_invite(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_multi_inv_(\d+)$ — invite chosen player."""
    q        = update.callback_query
    await q.answer()
    host_uid = q.from_user.id
    guest_uid = int(q.data[len("fut_draft_multi_inv_"):])

    if guest_uid == host_uid:
        await q.answer("Нельзя пригласить самого себя.", show_alert=True)
        return

    coins = db.get_coins(host_uid)
    if coins < DRAFT_ENTRY_FEE:
        await q.edit_message_text(
            f"❌ Недостаточно монет!\n\nНужно: *{_fmt(DRAFT_ENTRY_FEE)}* 💰",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_draft")]
            ]),
        )
        return

    ok, _ = db.spend_coins(host_uid, DRAFT_ENTRY_FEE)
    if not ok:
        await q.answer("Не удалось снять монеты.", show_alert=True)
        return

    host_user  = db.get_user(host_uid)
    guest_user = db.get_user(guest_uid)
    host_name  = (host_user or {}).get("display_name") or q.from_user.first_name or f"User{host_uid}"
    guest_name = (guest_user or {}).get("display_name") or f"User{guest_uid}"
    host_name  = host_name[:20]
    guest_name = guest_name[:20]

    room_id = f"dr_{host_uid}_{guest_uid}"
    _draft_rooms[room_id] = {
        "host_uid":   host_uid,
        "guest_uid":  guest_uid,
        "host_name":  host_name,
        "guest_name": guest_name,
        "host_sa":    None,
        "guest_sa":   None,
    }

    # Notify guest
    try:
        await ctx.bot.send_message(
            chat_id=guest_uid,
            text=(
                f"⚔️ *{host_name}* приглашает тебя в FUT Драфт!\n\n"
                f"Взнос: *{_fmt(DRAFT_ENTRY_FEE)}* 💰"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять",   callback_data=f"fut_draft_join_{host_uid}"),
                 InlineKeyboardButton("❌ Отклонить", callback_data=f"fut_draft_decline_{host_uid}")],
            ]),
        )
    except Exception as e:
        logger.warning(f"Draft invite DM failed for {guest_uid}: {e}")

    # Host starts picking immediately — show formation picker
    items = [
        InlineKeyboardButton(f["label"], callback_data=f"fut_draft_mform_{key}")
        for key, f in FORMATIONS.items()
    ]
    rows = [items[i:i+2] for i in range(0, len(items), 2)]

    # Store room_id in host pending_action
    db.set_pending_action(host_uid, "fut_draft_multi", {
        "room_id":     room_id,
        "slot_order":  [],
        "slot_idx":    0,
        "picks":       {},
        "used_ids":    [],
        "current_options": [],
        "phase":       "formation",
        "role":        "host",
    })

    await q.edit_message_text(
        f"✅ Приглашение отправлено *{guest_name}*!\n\n"
        f"Выбери схему расстановки:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_draft_multi_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_join_(\d+)$ — guest accepts multi draft invite."""
    q         = update.callback_query
    await q.answer()
    guest_uid = q.from_user.id
    host_uid  = int(q.data[len("fut_draft_join_"):])

    room_id = f"dr_{host_uid}_{guest_uid}"
    room    = _draft_rooms.get(room_id)
    if not room:
        await q.edit_message_text(
            "❌ Комната не найдена. Возможно, хост отменил приглашение.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]
            ]),
        )
        return

    ok, _ = db.spend_coins(guest_uid, DRAFT_ENTRY_FEE)
    if not ok:
        await q.edit_message_text(
            f"❌ Недостаточно монет!\n\nНужно: *{_fmt(DRAFT_ENTRY_FEE)}* 💰",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]
            ]),
        )
        return

    # Guest picks formation
    items = [
        InlineKeyboardButton(f["label"], callback_data=f"fut_draft_mform_{key}")
        for key, f in FORMATIONS.items()
    ]
    rows = [items[i:i+2] for i in range(0, len(items), 2)]

    db.set_pending_action(guest_uid, "fut_draft_multi", {
        "room_id":     room_id,
        "slot_order":  [],
        "slot_idx":    0,
        "picks":       {},
        "used_ids":    [],
        "current_options": [],
        "phase":       "formation",
        "role":        "guest",
    })

    await q.edit_message_text(
        "⚔️ *FUT Мульти-Драфт*\n\nВыбери схему расстановки:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_draft_multi_decline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_decline_(\d+)$ — guest declines invite."""
    q         = update.callback_query
    await q.answer()
    guest_uid = q.from_user.id
    host_uid  = int(q.data[len("fut_draft_decline_"):])

    room_id = f"dr_{host_uid}_{guest_uid}"
    _draft_rooms.pop(room_id, None)

    # Refund host
    db.add_coins(host_uid, DRAFT_ENTRY_FEE)
    db.clear_pending_action(host_uid)

    # BUG-22: notify host WITH a back button so they're not stuck on the dead formation picker
    try:
        await ctx.bot.send_message(
            chat_id=host_uid,
            text="❌ Соперник отклонил приглашение в драфт.\n\n💰 Взнос возвращён.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu"),
            ]]),
        )
    except Exception as e:
        logger.warning(f"Draft decline notify failed: {e}")

    await q.edit_message_text(
        "Приглашение отклонено.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]
        ]),
    )


async def cb_fut_draft_multi_form(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_mform_(\w+)$ — host or guest picks formation in multi draft."""
    q        = update.callback_query
    await q.answer()
    uid      = q.from_user.id
    form_key = q.data[len("fut_draft_mform_"):]

    if form_key not in FORMATIONS:
        await q.answer("Неизвестная схема.", show_alert=True)
        return

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_draft_multi":
        await q.answer("Сессия истекла.", show_alert=True)
        return

    data       = pending["data"]
    slot_order = _draft_slot_order(form_key)
    first_slot, first_group = slot_order[0]
    options    = _draft_get_options(first_group, set())

    data.update({
        "formation":       form_key,
        "slot_order":      [[s, g] for s, g in slot_order],
        "slot_idx":        0,
        "picks":           {},
        "used_ids":        [p["id"] for p in options],
        "current_options": options,
        "phase":           "picking",
    })
    db.set_pending_action(uid, "fut_draft_multi", data)
    await _show_draft_mpick(q, data)


async def cb_fut_draft_multi_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_draft_mpick_(\d+)$ — pick card in multi draft."""
    q         = update.callback_query
    await q.answer()
    uid       = q.from_user.id
    player_id = int(q.data[len("fut_draft_mpick_"):])

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_draft_multi":
        await q.answer("Сессия истекла.", show_alert=True)
        return

    data    = pending["data"]
    options = data.get("current_options", [])
    picked  = next((p for p in options if p["id"] == player_id), None)
    if not picked:
        await q.answer("Игрок не найден.", show_alert=True)
        return

    slot_order = data["slot_order"]
    slot_idx   = data["slot_idx"]
    slot_name  = slot_order[slot_idx][0]

    data["picks"][slot_name] = picked
    data["used_ids"].append(player_id)
    data["slot_idx"] = slot_idx + 1

    if data["slot_idx"] < len(slot_order):
        next_slot, next_group = slot_order[data["slot_idx"]]
        next_opts = _draft_get_options(next_group, set(data["used_ids"]))
        data["current_options"] = next_opts
        data["used_ids"].extend(p["id"] for p in next_opts)
        db.set_pending_action(uid, "fut_draft_multi", data)
        await _show_draft_mpick(q, data)
    else:
        # All 11 picked — compute SA and store in room
        data["phase"]           = "done"
        data["current_options"] = []
        db.set_pending_action(uid, "fut_draft_multi", data)

        sa      = _draft_build_sa(data["picks"])
        room_id = data["room_id"]
        room    = _draft_rooms.get(room_id)

        if room:
            role = data.get("role", "host")
            if role == "host":
                room["host_sa"] = sa
            else:
                room["guest_sa"] = sa

        await q.edit_message_text(
            "✅ *Драфт завершён!*\n\nЖдём соперника...",
            parse_mode="Markdown",
        )

        # Check if both ready
        if room:
            await _draft_multi_check_and_start(room_id, ctx.bot, q.from_user.id)


async def _draft_multi_check_and_start(room_id: str, bot, trigger_uid: int) -> None:
    """If both players done picking, run the match with full animation and award coins."""
    room = _draft_rooms.get(room_id)
    if not room:
        return
    if not room["host_sa"] or not room["guest_sa"]:
        return
    # BUG-1 fix: atomic guard against double-execution (asyncio is single-threaded,
    # so setting the flag here is safe before any await)
    if room.get("started"):
        return
    room["started"] = True

    host_uid   = room["host_uid"]
    guest_uid  = room["guest_uid"]
    host_name  = room["host_name"]
    guest_name = room["guest_name"]
    sa         = room["host_sa"]   # host = team A
    sb         = room["guest_sa"]  # guest = team B

    match_stats = _simulate_match(sa, sb)
    score_h     = match_stats["score_a"]
    score_g     = match_stats["score_b"]

    # Rewards
    pot   = int(DRAFT_ENTRY_FEE * 2 * 0.9)
    bonus = 200

    if score_h > score_g:
        coins_h, coins_g = pot + bonus, 0
    elif score_g > score_h:
        coins_h, coins_g = 0, pot + bonus
    else:
        coins_h = coins_g = pot // 2  # BUG-7: return from actual pot, not full fee

    if coins_h > 0:
        db.add_coins(host_uid, coins_h)
    if coins_g > 0:
        db.add_coins(guest_uid, coins_g)

    db.clear_pending_action(host_uid)
    db.clear_pending_action(guest_uid)
    _draft_rooms.pop(room_id, None)

    # Обратные статы для гостя (он видит себя как «свою» сторону)
    stats_guest = {
        **match_stats,
        "score_a":   match_stats["score_b"],
        "score_b":   match_stats["score_a"],
        "poss_a":    match_stats.get("poss_b", 50),
        "poss_b":    match_stats.get("poss_a", 50),
        "shots_a":   match_stats["shots_b"],
        "shots_b":   match_stats["shots_a"],
        "passes_a":  match_stats["passes_b"],
        "passes_b":  match_stats["passes_a"],
        "acc_a":     match_stats["acc_b"],
        "acc_b":     match_stats["acc_a"],
        "corners_a": match_stats["corners_b"],
        "corners_b": match_stats["corners_a"],
    }

    # Создаём общие интерактивные моменты для обоих игроков
    match_key      = f"dmulti_{room_id}"
    shared_moments = _make_shared_moments_pvp(host_uid, guest_uid, sa, sb, match_key)

    after_kb_h = InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]])
    after_kb_g = InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]])

    # Отправляем заглушки — анимация будет редактировать эти сообщения
    try:
        msg_h = await bot.send_message(
            chat_id=host_uid,
            text=f"⚽ *FUT Драфт* — {host_name} vs {guest_name}\n\n_Матч начинается..._",
            parse_mode="Markdown",
        )
        mid_h = msg_h.message_id
    except Exception:
        mid_h = None

    try:
        msg_g = await bot.send_message(
            chat_id=guest_uid,
            text=f"⚽ *FUT Драфт* — {host_name} vs {guest_name}\n\n_Матч начинается..._",
            parse_mode="Markdown",
        )
        mid_g = msg_g.message_id
    except Exception:
        mid_g = None

    async def _animations_and_cleanup():
        await asyncio.gather(
            _run_match_animation(
                bot=bot, chat_id=host_uid, message_id=mid_h,
                my_name=host_name, opp_name=guest_name, my_uid=host_uid,
                stats=match_stats, r_delta=0, coins=coins_h,
                shared_moments=shared_moments, after_kb=after_kb_h,
                my_sa=sa, opp_sa=sb,
            ),
            _run_match_animation(
                bot=bot, chat_id=guest_uid, message_id=mid_g,
                my_name=guest_name, opp_name=host_name, my_uid=guest_uid,
                stats=stats_guest, r_delta=0, coins=coins_g,
                shared_moments=shared_moments, after_kb=after_kb_g,
                my_sa=sb, opp_sa=sa,
            ),
            return_exceptions=True,
        )
        for m in shared_moments:
            _match_moments.pop(m["moment_id"], None)

    asyncio.create_task(_animations_and_cleanup())


# ══════════════════════════════════════════════════════════════════════════════
#  ТУРНИР-ДРАФТ — КОНСТАНТЫ
# ══════════════════════════════════════════════════════════════════════════════

TOUR_MAX_PLAYERS = 16
TOUR_ENTRY_FEE   = 500   # монет
TOUR_INVITE_PAGE = 8


# ══════════════════════════════════════════════════════════════════════════════
#  ТУРНИР-ДРАФТ — ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════════════════════════════════

def _tour_id_from_data(data: str) -> str:
    """Parse tour_id (e.g. 'DR-XXXX') from callback_data string.
    Tour IDs are always 7 chars and start with 'DR-'."""
    # BUG-13: removed dead for-loop that did nothing; just scan for the prefix
    idx = data.find("DR-")
    if idx >= 0:
        return data[idx:idx + 7]
    return ""


def _tour_bracket_text(tour: dict) -> str:
    slots   = tour.get("slots") or []
    matches = tour.get("matches") or {}
    lines   = []
    round_labels = {1: "🔵 1/8 финала", 2: "🟢 Четвертьфинал", 3: "🟡 Полуфинал", 4: "🔴 Финал"}
    for rnum in sorted(int(k) for k in matches if matches[k]):
        label = round_labels.get(rnum, f"Раунд {rnum}")
        lines.append(f"\n*{label}*")
        for m in matches[str(rnum)]:
            if m["p1"] < len(slots) and m["p2"] < len(slots):
                n1 = slots[m["p1"]]["name"][:12]
                n2 = slots[m["p2"]]["name"][:12]
            else:
                n1, n2 = "?", "?"
            if m.get("winner") is not None and m["winner"] < len(slots):
                wn = slots[m["winner"]]["name"][:12]
                lines.append(f"  {n1} {m['s1']}:{m['s2']} {n2} → {wn} ✅")
            else:
                lines.append(f"  {n1} vs {n2}")
    return "\n".join(lines) if lines else "_Матчи ещё не начались_"


def _tour_lobby_text(tour: dict) -> str:
    slots    = tour.get("slots") or []
    tour_id  = tour["id"]
    n        = len(slots)
    lines    = [f"🏆 *Турнир {tour_id}*\n", f"Игроки ({n}/{TOUR_MAX_PLAYERS}):\n"]
    for i, s in enumerate(slots, 1):
        host_tag = " \\[Хост\\]" if i == 1 else ""
        lines.append(f"{i}.{host_tag} {s['name']}")
    for i in range(n + 1, TOUR_MAX_PLAYERS + 1):
        lines.append(f"{i}. _(пусто)_")
    return "\n".join(lines)


async def _tour_run_round(tour_id: str, round_num: int, bot) -> None:
    """Simulate all matches of the given round with full animation, then advance/complete the tournament."""
    tour = db.get_fut_tournament(tour_id)
    if not tour:
        return

    slots   = tour["slots"]
    matches = tour.get("matches") or {}
    round_matches = matches.get(str(round_num), [])

    # ── Simulate all matches and prepare animations ────────────────────────────
    results      = []
    anim_tasks   = []
    all_moments  = []  # [(match_key, [moment_cfg, ...])]

    for m_idx, m in enumerate(round_matches):
        slot1 = slots[m["p1"]]
        slot2 = slots[m["p2"]]
        sa1   = slot1["sa"]
        sa2   = slot2["sa"]
        stats = _simulate_match(sa1, sa2)
        s1    = stats["score_a"]
        s2    = stats["score_b"]
        if s1 > s2:
            winner = m["p1"]
        elif s2 > s1:
            winner = m["p2"]
        else:
            winner = random.choice([m["p1"], m["p2"]])
        results.append({**m, "winner": winner, "s1": s1, "s2": s2})

        # Build animations for human players
        uid1 = slot1.get("uid")  # None if bot slot
        uid2 = slot2.get("uid")
        is_bot1 = slot1.get("is_bot", False)  # BUG-19: default False — missing key = human
        is_bot2 = slot2.get("is_bot", False)
        name1 = slot1["name"]
        name2 = slot2["name"]
        match_key = f"tour_{tour_id}_r{round_num}_m{m_idx}"

        if not is_bot1 and not is_bot2:
            # Both human — shared interactive moments
            shared = _make_shared_moments_pvp(uid1, uid2, sa1, sa2, match_key)
            all_moments.append((match_key, shared))
            stats_b = {
                **stats,
                "score_a": stats["score_b"], "score_b": stats["score_a"],
                "poss_a":  stats.get("poss_b", 50), "poss_b":  stats.get("poss_a", 50),
                "shots_a": stats["shots_b"],  "shots_b": stats["shots_a"],
                "passes_a":stats["passes_b"], "passes_b":stats["passes_a"],
                "acc_a":   stats["acc_b"],    "acc_b":   stats["acc_a"],
                "corners_a":stats["corners_b"],"corners_b":stats["corners_a"],
            }
            after_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Сетка", callback_data=f"fut_tour_bracket_{tour_id}")]])
            for uid, my_stats, my_name, opp_name, my_sa_t, opp_sa_t in [
                (uid1, stats,   name1, name2, sa1, sa2),
                (uid2, stats_b, name2, name1, sa2, sa1),
            ]:
                try:
                    msg = await bot.send_message(
                        chat_id=uid,
                        text=f"⚽ *Турнир {tour_id}* — {name1} vs {name2}\n\n_Матч начинается..._",
                        parse_mode="Markdown",
                    )
                    mid = msg.message_id
                except Exception:
                    mid = None
                anim_tasks.append(_run_match_animation(
                    bot=bot, chat_id=uid, message_id=mid,
                    my_name=my_name, opp_name=opp_name, my_uid=uid,
                    stats=my_stats, r_delta=0, coins=0,
                    shared_moments=shared, after_kb=after_kb,
                    my_sa=my_sa_t, opp_sa=opp_sa_t,
                ))

        elif not is_bot1 and is_bot2:
            # uid1 is human, uid2 is bot
            shared = _make_shared_moments_vs_bot(uid1, sa1, sa2, match_key)
            all_moments.append((match_key, shared))
            after_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Сетка", callback_data=f"fut_tour_bracket_{tour_id}")]])
            try:
                msg = await bot.send_message(
                    chat_id=uid1,
                    text=f"⚽ *Турнир {tour_id}* — {name1} vs {name2}\n\n_Матч начинается..._",
                    parse_mode="Markdown",
                )
                mid = msg.message_id
            except Exception:
                mid = None
            anim_tasks.append(_run_match_animation(
                bot=bot, chat_id=uid1, message_id=mid,
                my_name=name1, opp_name=name2, my_uid=uid1,
                stats=stats, r_delta=0, coins=0,
                shared_moments=shared, after_kb=after_kb,
                my_sa=sa1, opp_sa=sa2,
            ))

        elif is_bot1 and not is_bot2:
            # uid2 is human, uid1 is bot
            shared = _make_shared_moments_vs_bot(uid2, sa2, sa1, match_key)
            all_moments.append((match_key, shared))
            stats_b = {
                **stats,
                "score_a": stats["score_b"], "score_b": stats["score_a"],
                "poss_a":  stats.get("poss_b", 50), "poss_b":  stats.get("poss_a", 50),
                "shots_a": stats["shots_b"],  "shots_b": stats["shots_a"],
                "passes_a":stats["passes_b"], "passes_b":stats["passes_a"],
                "acc_a":   stats["acc_b"],    "acc_b":   stats["acc_a"],
                "corners_a":stats["corners_b"],"corners_b":stats["corners_a"],
            }
            after_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Сетка", callback_data=f"fut_tour_bracket_{tour_id}")]])
            try:
                msg = await bot.send_message(
                    chat_id=uid2,
                    text=f"⚽ *Турнир {tour_id}* — {name1} vs {name2}\n\n_Матч начинается..._",
                    parse_mode="Markdown",
                )
                mid = msg.message_id
            except Exception:
                mid = None
            anim_tasks.append(_run_match_animation(
                bot=bot, chat_id=uid2, message_id=mid,
                my_name=name2, opp_name=name1, my_uid=uid2,
                stats=stats_b, r_delta=0, coins=0,
                shared_moments=shared, after_kb=after_kb,
                my_sa=sa2, opp_sa=sa1,
            ))
        # else: both bots — no animation needed

    # ── Run all animations in parallel, then continue ──────────────────────────
    if anim_tasks:
        await asyncio.gather(*anim_tasks, return_exceptions=True)

    # Cleanup moments
    for _, moment_list in all_moments:
        for mc in moment_list:
            _match_moments.pop(mc["moment_id"], None)

    matches[str(round_num)] = results

    human_slots = [s for s in slots if s.get("uid") and not s.get("is_bot")]
    is_final = (len(results) == 1)

    round_labels = {1: "1/8 финала", 2: "Четвертьфинал", 3: "Полуфинал", 4: "Финал"}
    curr_label   = round_labels.get(round_num, f"Раунд {round_num}")

    if is_final:
        final_match  = results[0]
        winner_idx   = final_match["winner"]
        loser_idx    = final_match["p2"] if final_match["winner"] == final_match["p1"] else final_match["p1"]
        winner_slot  = slots[winner_idx]
        loser_slot   = slots[loser_idx]

        n_humans     = sum(1 for s in slots if not s.get("is_bot"))
        total_fee    = TOUR_ENTRY_FEE * n_humans
        prize_1st    = round(total_fee * 0.65)
        prize_2nd    = round(total_fee * 0.25)
        prize_semi   = round(total_fee * 0.05)

        if winner_slot.get("uid"):
            db.add_coins(winner_slot["uid"], prize_1st)
        if loser_slot.get("uid"):
            db.add_coins(loser_slot["uid"], prize_2nd)

        # BUG-20: prize_semi only for actual semi-final losers (round >= 3 means
        # there were 8+ players and round_num-1 is genuinely a semi-final round)
        if round_num >= 3:
            semi_matches = matches.get(str(round_num - 1), [])
            for sm in semi_matches:
                loser_semi_idx = sm["p1"] if sm["winner"] == sm["p2"] else sm["p2"]
                semi_slot = slots[loser_semi_idx]
                if semi_slot.get("uid"):
                    db.add_coins(semi_slot["uid"], prize_semi)

        db.update_fut_tournament(tour_id, status="completed", matches=matches, round=round_num)

        result_text = _tour_bracket_text({**tour, "matches": matches})
        for s in human_slots:
            try:
                await bot.send_message(
                    s["uid"],
                    f"🏆 *Турнир {tour_id} завершён!*\n\n"
                    f"🥇 Победитель: *{winner_slot['name']}* (+{_fmt(prize_1st)} 💰)\n"
                    f"🥈 Финалист: *{loser_slot['name']}* (+{_fmt(prize_2nd)} 💰)\n\n"
                    f"{result_text}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")
                    ]]),
                )
            except Exception:
                pass
    else:
        winners     = [m["winner"] for m in results]
        next_round  = round_num + 1
        next_matches = [
            {"p1": winners[i], "p2": winners[i + 1], "winner": None, "s1": 0, "s2": 0}
            for i in range(0, len(winners), 2)
        ]
        matches[str(next_round)] = next_matches
        next_label = round_labels.get(next_round, f"Раунд {next_round}")

        db.update_fut_tournament(tour_id, status=f"round_{next_round}", matches=matches, round=next_round)

        round_text = []
        for m in results:
            n1 = slots[m["p1"]]["name"]
            n2 = slots[m["p2"]]["name"]
            wn = slots[m["winner"]]["name"]
            round_text.append(f"• {n1} {m['s1']}:{m['s2']} {n2} → *{wn}* ✅")

        for s in human_slots:
            try:
                await bot.send_message(
                    s["uid"],
                    f"⚽ *{curr_label} завершён!*\n\n"
                    + "\n".join(round_text)
                    + f"\n\n*{next_label}* уже начался!",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📊 Сетка", callback_data=f"fut_tour_bracket_{tour_id}")
                    ]]),
                )
            except Exception:
                pass

        await _tour_run_round(tour_id, next_round, bot)


# ══════════════════════════════════════════════════════════════════════════════
#  ТУРНИР-ДРАФТ — ХЕНДЛЕРЫ
# ══════════════════════════════════════════════════════════════════════════════

async def cb_fut_tour(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour$ — main tournament menu."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    tour = db.get_active_tournament_for_user(uid)
    if tour:
        slots    = tour.get("slots") or []
        n        = len(slots)
        status   = tour.get("status", "")
        tour_id  = tour["id"]
        is_host  = tour.get("host_uid") == uid

        status_names = {
            "lobby":    "🟡 Ожидание игроков",
            "drafting": "🎲 Драфт",
            "round_1":  "⚽ Раунд 1/8 финала",
            "round_2":  "⚽ Четвертьфинал",
            "round_3":  "⚽ Полуфинал",
            "round_4":  "⚽ Финал",
        }
        status_str = status_names.get(status, status)

        kb_rows = []
        if status == "lobby":
            if is_host:
                kb_rows.append([
                    InlineKeyboardButton("➕ Пригласить", callback_data=f"fut_tour_invite_{tour_id}_0"),
                    InlineKeyboardButton("🚀 Начать!", callback_data=f"fut_tour_start_{tour_id}"),
                ])
            kb_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data=f"fut_tour_lobby_{tour_id}")])
        elif status == "drafting":
            # Check if this user has not yet drafted
            my_slot = next((s for s in slots if s.get("uid") == uid), None)
            if my_slot and not my_slot.get("drafted"):
                kb_rows.append([InlineKeyboardButton("🎯 Задрафтить команду", callback_data=f"fut_tour_draft_{tour_id}")])
            else:
                kb_rows.append([InlineKeyboardButton("⏳ Ждём остальных...", callback_data=f"fut_tour_lobby_{tour_id}")])
        else:
            kb_rows.append([InlineKeyboardButton("📊 Сетка", callback_data=f"fut_tour_bracket_{tour_id}")])
        kb_rows.append([InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")])

        await q.edit_message_text(
            f"🏆 *Турнир {tour_id}*\n\n"
            f"Статус: {status_str}\n"
            f"Игроки: *{n}/{TOUR_MAX_PLAYERS}*\n"
            f"Взнос: *{_fmt(tour.get('entry_fee', TOUR_ENTRY_FEE))}* 💰",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb_rows),
        )
        return

    await q.edit_message_text(
        "🏆 *Драфт-турнир*\n\n"
        "Нет активного турнира.\n"
        "_16 игроков, один драфт, четыре раунда!_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 Создать турнир", callback_data="fut_tour_create"),
             InlineKeyboardButton("◀ FUT меню",        callback_data="fut_menu")],
        ]),
    )


async def cb_fut_tour_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_create$ — create new tournament lobby."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    existing = db.get_active_tournament_for_user(uid)
    if existing:
        await q.answer("У тебя уже есть активный турнир.", show_alert=True)
        return

    host_user = db.get_user(uid)
    host_name = (host_user or {}).get("display_name") or (host_user or {}).get("username") or f"User{uid}"

    tour_id = db.create_fut_tournament(uid, TOUR_ENTRY_FEE)

    initial_slot = {"uid": uid, "name": host_name, "is_bot": False, "sa": None, "drafted": False}
    db.update_fut_tournament(tour_id, slots=[initial_slot])

    await q.edit_message_text(
        f"🏆 *Турнир {tour_id}*\n\n"
        f"Твой турнир создан!\n"
        f"Код: `{tour_id}`\n\n"
        f"Игроки (1/{TOUR_MAX_PLAYERS}):\n"
        f"1. \\[Хост\\] {host_name}\n"
        + "\n".join(f"{i}. _(пусто)_" for i in range(2, TOUR_MAX_PLAYERS + 1)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Пригласить",    callback_data=f"fut_tour_invite_{tour_id}_0"),
             InlineKeyboardButton("🚀 Начать!",       callback_data=f"fut_tour_start_{tour_id}")],
            [InlineKeyboardButton("◀ Назад",          callback_data="fut_tour")],
        ]),
    )


async def cb_fut_tour_lobby(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_lobby_(\w{7})$ — view/refresh lobby."""
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id
    tour_id = _tour_id_from_data(q.data)

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.answer("Турнир не найден.", show_alert=True)
        return

    slots   = tour.get("slots") or []
    n       = len(slots)
    is_host = tour.get("host_uid") == uid
    status  = tour.get("status", "lobby")
    in_tour = any(s.get("uid") == uid for s in slots)

    text = _tour_lobby_text(tour)

    kb_rows = []
    if status == "lobby":
        if is_host:
            kb_rows.append([
                InlineKeyboardButton("➕ Пригласить", callback_data=f"fut_tour_invite_{tour_id}_0"),
                InlineKeyboardButton("🚀 Начать!",    callback_data=f"fut_tour_start_{tour_id}"),
            ])
        elif in_tour:
            kb_rows.append([InlineKeyboardButton("🚪 Покинуть", callback_data=f"fut_tour_leave_{tour_id}")])
        kb_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data=f"fut_tour_lobby_{tour_id}")])
    else:
        my_slot = next((s for s in slots if s.get("uid") == uid), None)
        if status == "drafting" and my_slot and not my_slot.get("drafted"):
            kb_rows.append([InlineKeyboardButton("🎯 Задрафтить", callback_data=f"fut_tour_draft_{tour_id}")])
        else:
            kb_rows.append([InlineKeyboardButton("📊 Сетка", callback_data=f"fut_tour_bracket_{tour_id}")])
    kb_rows.append([InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")])

    await q.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb_rows),
    )


async def cb_fut_tour_invite(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_invite_ — paginated player list for inviting.
    callback_data format: fut_tour_invite_{tour_id}_{offset}
    tour_id is 7 chars (DR-XXXX). offset is a number.
    """
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id

    # Parse: after prefix 'fut_tour_invite_' split remainder on '_' from right to get offset
    tail    = q.data[len("fut_tour_invite_"):]
    # tail = "DR-XXXX_0" or "DR-XXXX_10"
    # Split on last '_'
    ridx    = tail.rfind("_")
    tour_id = tail[:ridx]    # "DR-XXXX"
    offset  = int(tail[ridx + 1:])

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.answer("Турнир не найден.", show_alert=True)
        return

    if tour.get("host_uid") != uid:
        await q.answer("Только хост может приглашать.", show_alert=True)
        return

    slots = tour.get("slots") or []
    if len(slots) >= TOUR_MAX_PLAYERS:
        await q.answer("Турнир уже заполнен.", show_alert=True)
        return

    existing_uids = {s["uid"] for s in slots if s.get("uid")}
    all_users     = db.get_all_users(exclude_user_id=uid)
    eligible      = [u for u in all_users if u["user_id"] not in existing_uids]

    total      = len(eligible)
    page_users = eligible[offset: offset + TOUR_INVITE_PAGE]

    if not page_users and offset == 0:
        await q.edit_message_text(
            "Нет доступных игроков для приглашения.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data=f"fut_tour_lobby_{tour_id}")]
            ]),
        )
        return

    kb = []
    for u in page_users:
        name  = (u.get("display_name") or u.get("username") or f"User{u['user_id']}")[:20]
        label = f"👤 {name}"
        kb.append([InlineKeyboardButton(label, callback_data=f"fut_tour_inv_{tour_id}_{u['user_id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_tour_invite_{tour_id}_{offset - TOUR_INVITE_PAGE}"))
    if offset + TOUR_INVITE_PAGE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_tour_invite_{tour_id}_{offset + TOUR_INVITE_PAGE}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Назад", callback_data=f"fut_tour_lobby_{tour_id}")])

    cur_page = offset // TOUR_INVITE_PAGE + 1
    pages    = max(1, (total + TOUR_INVITE_PAGE - 1) // TOUR_INVITE_PAGE)
    await q.edit_message_text(
        f"➕ *Пригласить игрока*\n_Стр. {cur_page}/{pages} • Всего: {total}_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_tour_inv(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_inv_ — send invite DM to a specific player.
    callback_data: fut_tour_inv_{tour_id}_{to_uid}
    """
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id

    tail    = q.data[len("fut_tour_inv_"):]
    ridx    = tail.rfind("_")
    tour_id = tail[:ridx]
    to_uid  = int(tail[ridx + 1:])

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.answer("Турнир не найден.", show_alert=True)
        return

    if tour.get("host_uid") != uid:
        await q.answer("Только хост может приглашать.", show_alert=True)
        return

    slots = tour.get("slots") or []
    if len(slots) >= TOUR_MAX_PLAYERS:
        await q.answer("Турнир заполнен!", show_alert=True)
        return

    if any(s.get("uid") == to_uid for s in slots):
        await q.answer("Этот игрок уже в турнире.", show_alert=True)
        return

    host_user = db.get_user(uid)
    host_name = (host_user or {}).get("display_name") or (host_user or {}).get("username") or f"User{uid}"

    try:
        await ctx.bot.send_message(
            chat_id=to_uid,
            text=(
                f"🏆 *Тебя приглашают в турнир {tour_id}!*\n\n"
                f"Организатор: *{host_name}*\n"
                f"Взнос: *{_fmt(TOUR_ENTRY_FEE)}* 💰\n"
                f"Игроков: *{len(slots)}/{TOUR_MAX_PLAYERS}*"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Вступить",   callback_data=f"fut_tour_join_{tour_id}"),
                 InlineKeyboardButton("❌ Отклонить",  callback_data=f"fut_tour_rejt_{tour_id}")],
            ]),
        )
    except Exception as e:
        logger.warning(f"Tour invite DM failed for {to_uid}: {e}")
        await q.answer("Не удалось отправить приглашение.", show_alert=True)
        return

    await q.answer(f"✅ Приглашение отправлено!")
    await q.edit_message_text(
        f"✅ Приглашение отправлено!\n\n"
        f"Турнир: *{tour_id}* ({len(slots)}/{TOUR_MAX_PLAYERS})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ещё пригласить", callback_data=f"fut_tour_invite_{tour_id}_0")],
            [InlineKeyboardButton("🔄 Лобби",          callback_data=f"fut_tour_lobby_{tour_id}")],
        ]),
    )


async def cb_fut_tour_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_join_ — accept invite."""
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id
    tour_id = _tour_id_from_data(q.data)

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.edit_message_text(
            "❌ Турнир не найден.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]),
        )
        return

    if tour.get("status") != "lobby":
        await q.edit_message_text(
            "❌ Турнир уже начался.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]),
        )
        return

    slots = list(tour.get("slots") or [])
    if any(s.get("uid") == uid for s in slots):
        await q.edit_message_text(
            "Ты уже в турнире!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Лобби", callback_data=f"fut_tour_lobby_{tour_id}")]]),
        )
        return

    if len(slots) >= TOUR_MAX_PLAYERS:
        await q.edit_message_text(
            "❌ Турнир уже заполнен.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]),
        )
        return

    entry_fee = tour.get("entry_fee", TOUR_ENTRY_FEE)
    ok, new_bal = db.spend_coins(uid, entry_fee)
    if not ok:
        await q.edit_message_text(
            f"❌ Недостаточно монет!\n\nНужно: *{_fmt(entry_fee)}* 💰\n"
            f"Твой баланс: *{_fmt(new_bal)}* 💰",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]),
        )
        return

    user = db.get_user(uid)
    name = (user or {}).get("display_name") or (user or {}).get("username") or f"User{uid}"
    slots.append({"uid": uid, "name": name, "is_bot": False, "sa": None, "drafted": False})
    db.update_fut_tournament(tour_id, slots=slots)

    # Notify host
    host_uid = tour.get("host_uid")
    try:
        await ctx.bot.send_message(
            chat_id=host_uid,
            text=f"✅ *{name}* вступил в турнир *{tour_id}*! ({len(slots)}/{TOUR_MAX_PLAYERS})",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    await q.edit_message_text(
        f"✅ *Ты вступил в турнир {tour_id}!*\n\n"
        f"Взнос: *{_fmt(entry_fee)}* 💰 списано.\n"
        f"Игроков: *{len(slots)}/{TOUR_MAX_PLAYERS}*\n\n"
        "_Жди старта от организатора._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Лобби", callback_data=f"fut_tour_lobby_{tour_id}")],
            [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")],
        ]),
    )


async def cb_fut_tour_rejt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_rejt_ — decline invite."""
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "Ты отклонил приглашение.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]),
    )


async def cb_fut_tour_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_start_ — host starts tournament."""
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id
    tour_id = _tour_id_from_data(q.data)

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.answer("Турнир не найден.", show_alert=True)
        return

    if tour.get("host_uid") != uid:
        await q.answer("Только хост может запустить турнир.", show_alert=True)
        return

    if tour.get("status") != "lobby":
        await q.answer("Турнир уже начался.", show_alert=True)
        return

    slots = list(tour.get("slots") or [])
    n_human = len(slots)

    if n_human < 2:
        await q.answer("Нужно минимум 2 игрока!", show_alert=True)
        return

    # Fill remaining slots with bots up to the nearest power of 2 (min 4)
    import math
    target = max(4, 2 ** math.ceil(math.log2(n_human)) if n_human > 1 else 4)
    target = min(target, TOUR_MAX_PLAYERS)
    bot_i  = 1
    while len(slots) < target:
        slots.append({
            "uid":     None,
            "name":    f"🤖 Бот #{bot_i}",
            "is_bot":  True,
            "sa":      _draft_bot_sa(82, 86),
            "drafted": True,
        })
        bot_i += 1

    # Shuffle draw
    random.shuffle(slots)

    # Generate Round 1 match pairs
    round_1 = [
        {"p1": i, "p2": i + 1, "winner": None, "s1": 0, "s2": 0}
        for i in range(0, len(slots), 2)
    ]
    matches = {"1": round_1}

    db.update_fut_tournament(tour_id, status="drafting", slots=slots, matches=matches, round=0)

    # Notify all human players to draft
    human_slots = [s for s in slots if s.get("uid") and not s.get("is_bot")]
    for s in human_slots:
        try:
            await ctx.bot.send_message(
                s["uid"],
                f"🎲 *Турнир {tour_id} начался!*\n\n"
                f"Задрафти команду — она будет твоей на весь турнир.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎯 Начать драфт", callback_data=f"fut_tour_draft_{tour_id}")
                ]]),
            )
        except Exception:
            pass

    await q.edit_message_text(
        f"🚀 *Турнир {tour_id} запущен!*\n\n"
        f"Участников: *{len(slots)}* ({n_human} человек + {len(slots) - n_human} ботов)\n\n"
        "_Все участники получили уведомление — начинается драфт!_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Начать драфт", callback_data=f"fut_tour_draft_{tour_id}")],
        ]),
    )


async def cb_fut_tour_draft(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_draft_ — show formation picker for tournament draft."""
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id
    tour_id = _tour_id_from_data(q.data)

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.answer("Турнир не найден.", show_alert=True)
        return

    slots    = tour.get("slots") or []
    my_slot  = next((s for s in slots if s.get("uid") == uid), None)
    if not my_slot:
        await q.answer("Ты не участник этого турнира.", show_alert=True)
        return

    if my_slot.get("drafted"):
        await q.answer("Ты уже задрафтировал команду!", show_alert=True)
        return

    if tour.get("status") != "drafting":
        await q.answer("Сейчас не фаза драфта.", show_alert=True)
        return

    items = [
        InlineKeyboardButton(f["label"], callback_data=f"fut_tour_dform_{tour_id}_{key}")
        for key, f in FORMATIONS.items()
    ]
    rows = [items[i:i + 2] for i in range(0, len(items), 2)]
    rows.append([InlineKeyboardButton("◀ Отмена", callback_data=f"fut_tour_lobby_{tour_id}")])

    await q.edit_message_text(
        f"🎲 *Турнир {tour_id} — Драфт*\n\n"
        "Выбери схему расстановки:\n"
        "_Команда будет твоей на весь турнир!_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_tour_dform(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_dform_ — formation chosen, begin tournament draft."""
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id

    # Parse: fut_tour_dform_{tour_id}_{formation}
    # tour_id is 7 chars (DR-XXXX), formation is e.g. '433', '442'
    tail     = q.data[len("fut_tour_dform_"):]
    # tour_id is always 7 chars
    tour_id  = tail[:7]
    form_key = tail[8:]   # skip the '_' separator

    if form_key not in FORMATIONS:
        await q.answer("Неизвестная схема.", show_alert=True)
        return

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.answer("Турнир не найден.", show_alert=True)
        return

    slots   = tour.get("slots") or []
    my_slot = next((s for s in slots if s.get("uid") == uid), None)
    if not my_slot or my_slot.get("drafted"):
        await q.answer("Нельзя драфтить.", show_alert=True)
        return

    slot_order = _draft_slot_order(form_key)
    first_slot, first_group = slot_order[0]
    options = _draft_get_options(first_group, set())

    data: dict = {
        "tour_id":         tour_id,
        "formation":       form_key,
        "slot_order":      [[s, g] for s, g in slot_order],
        "slot_idx":        0,
        "picks":           {},
        "used_ids":        [p["id"] for p in options],
        "current_options": options,
    }
    db.set_pending_action(uid, "fut_tour_draft", data)
    await _show_tour_draft_pick(q, data)


async def _show_tour_draft_pick(q, data: dict) -> None:
    """Display current pick choice for a tournament draft slot."""
    slot_order = data["slot_order"]
    slot_idx   = data["slot_idx"]
    slot_name, group = slot_order[slot_idx]
    options    = data["current_options"]
    total      = len(slot_order)
    tour_id    = data["tour_id"]

    group_name = GROUP_NAME.get(group, group)
    text = (
        f"🎲 *Турнир {tour_id} — Слот {slot_idx + 1}/{total}*\n\n"
        f"📌 Позиция: `{slot_name}` ({group_name})\n\n"
        "_Выбери одного из трёх:_"
    )

    kb = []
    for p in options:
        emoji = _card_emoji(p["rating"])
        ver   = p.get("version", "")
        ver_s = f" ({ver})" if ver else ""
        lbl   = f"{emoji} {p['rating']} {p['position']} {p['name'][:16]}{ver_s}"
        kb.append([InlineKeyboardButton(lbl, callback_data=f"fut_tour_pick_{p['id']}")])
    kb.append([InlineKeyboardButton("❌ Отмена", callback_data=f"fut_tour_lobby_{tour_id}")])

    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_tour_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_pick_ — pick card in tournament draft."""
    q         = update.callback_query
    await q.answer()
    uid       = q.from_user.id
    player_id = int(q.data[len("fut_tour_pick_"):])

    pending = db.get_pending_action(uid)
    if not pending or pending.get("action") != "fut_tour_draft":
        await q.answer("Сессия истекла. Начни заново.", show_alert=True)
        return

    data    = pending["data"]
    options = data.get("current_options", [])
    picked  = next((p for p in options if p["id"] == player_id), None)
    if not picked:
        await q.answer("Игрок не найден. Выбери из списка.", show_alert=True)
        return

    slot_order = data["slot_order"]
    slot_idx   = data["slot_idx"]
    slot_name  = slot_order[slot_idx][0]

    data["picks"][slot_name] = picked
    data["used_ids"].append(player_id)
    data["slot_idx"] = slot_idx + 1

    if data["slot_idx"] < len(slot_order):
        next_slot, next_group = slot_order[data["slot_idx"]]
        next_opts = _draft_get_options(next_group, set(data["used_ids"]))
        data["current_options"] = next_opts
        data["used_ids"].extend(p["id"] for p in next_opts)
        db.set_pending_action(uid, "fut_tour_draft", data)
        await _show_tour_draft_pick(q, data)
        return

    # All slots picked — build SA and save to tournament slot
    tour_id = data["tour_id"]
    sa      = _draft_build_sa(data["picks"])

    db.clear_pending_action(uid)

    # Reload tournament and update this player's slot
    tour  = db.get_fut_tournament(tour_id)
    if not tour:
        await q.edit_message_text("❌ Турнир не найден.", parse_mode="Markdown")
        return

    slots = list(tour.get("slots") or [])
    for s in slots:
        if s.get("uid") == uid:
            s["sa"]      = sa
            s["drafted"] = True
            break

    db.update_fut_tournament(tour_id, slots=slots)

    # Check if all human players have drafted
    human_slots   = [s for s in slots if s.get("uid") and not s.get("is_bot")]
    all_drafted   = all(s.get("drafted") for s in human_slots)

    form_label = FORMATIONS[data["formation"]]["label"]
    await q.edit_message_text(
        f"✅ *Команда задрафтирована!* ({form_label})\n\n"
        f"⭐ OVR: *{sa['ovr']}*  ATT: *{sa['att']}*  DEF: *{sa['def_']}*\n\n"
        + ("_Все задрафтили — начинаем турнир!_" if all_drafted else "_Ждём остальных участников..._"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Сетка", callback_data=f"fut_tour_bracket_{tour_id}")]
        ]),
    )

    if all_drafted:
        asyncio.create_task(_tour_run_round(tour_id, 1, ctx.bot))


async def cb_fut_tour_leave(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_leave_ — leave tournament lobby (only allowed before start)."""
    q       = update.callback_query
    await q.answer()
    uid     = q.from_user.id
    tour_id = _tour_id_from_data(q.data)

    tour = db.get_fut_tournament(tour_id) if tour_id else None
    if not tour or tour.get("status") != "lobby":
        await q.edit_message_text(
            "❌ Покинуть турнир можно только до старта.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]),
        )
        return

    slots = tour.get("slots") or []
    # Host cannot leave (they must cancel the tournament instead)
    if tour.get("host_uid") == uid:
        await q.answer("Хост не может покинуть — только отменить турнир.", show_alert=True)
        return

    new_slots = [s for s in slots if s.get("uid") != uid]
    if len(new_slots) == len(slots):
        await q.answer("Ты не в этом турнире.", show_alert=True)
        return

    # Refund entry fee and remove from slot list
    db.add_coins(uid, TOUR_ENTRY_FEE)
    db.update_fut_tournament(tour_id, slots=new_slots)

    await q.edit_message_text(
        f"✅ Ты покинул турнир {tour_id}.\n💰 Взнос {_fmt(TOUR_ENTRY_FEE)} монет возвращён.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]),
    )


async def cb_fut_tour_bracket(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_tour_bracket_ — show bracket."""
    q       = update.callback_query
    await q.answer()
    tour_id = _tour_id_from_data(q.data)

    tour = db.get_fut_tournament(tour_id)
    if not tour:
        await q.answer("Турнир не найден.", show_alert=True)
        return

    text = _tour_bracket_text(tour)

    await q.edit_message_text(
        f"📊 *Сетка турнира {tour_id}*\n{text}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data=f"fut_tour_bracket_{tour_id}")],
            [InlineKeyboardButton("◀ FUT меню",  callback_data="fut_menu")],
        ]),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

def fut_handlers() -> list[tuple[str, Any]]:
    return [
        # Меню и паки
        ("^fut_menu$",                    cb_fut_menu),
        ("^fut_packs$",                   cb_fut_packs),
        ("^fut_buy_",                     cb_fut_buy),
        ("^fut_no_coins$",                cb_fut_no_coins),
        # Клуб
        ("^fut_sell_confirm_",            cb_fut_sell_confirm),
        ("^fut_card_",                    cb_fut_card),
        ("^fut_sell_dupes$",              cb_fut_sell_dupes),
        ("^fut_club_",                    cb_fut_club),
        # Команда (специфичные — до общего fut_team$)
        ("^fut_team_setform_",            cb_fut_team_setform),
        ("^fut_team_remove_",             cb_fut_team_remove),
        ("^fut_team_slot_",               cb_fut_team_slot),
        ("^fut_team_pick_",               cb_fut_team_pick),
        ("^fut_team_form$",               cb_fut_team_form),
        ("^fut_team$",                    cb_fut_team),
        # Матчи (специфичные — до общего fut_match)
        ("^fut_int_",                     cb_fut_interact),      # интерактивный выбор (до fut_match)
        ("^fut_challenge_",               cb_fut_challenge),
        ("^fut_send_",                    cb_fut_send),
        ("^fut_accept_",                  cb_fut_accept),
        ("^fut_decline_",                 cb_fut_decline),
        ("^fut_match_history$",           cb_fut_match_history),
        ("^fut_match$",                   cb_fut_match),
        # ── Рынок (специфичные — до fut_market$) ──────────────────────────────
        ("^fut_market_browse_",           cb_fut_market_browse),
        ("^fut_market_buy_ok_",           cb_fut_market_buy_ok),
        ("^fut_market_buy_",              cb_fut_market_buy),
        ("^fut_market_cancel_ok_",        cb_fut_market_cancel_ok),
        ("^fut_market_cancel_",           cb_fut_market_cancel),
        ("^fut_market_view_",             cb_fut_market_view),
        ("^fut_market_sell_pick_",        cb_fut_market_sell_pick),
        ("^fut_market_sellp_",            cb_fut_market_sell_page),
        ("^fut_market_sell$",             cb_fut_market_sell),
        ("^fut_market_my$",               cb_fut_market_my),
        ("^fut_market$",                  cb_fut_market),
        # ── Торговые предложения ───────────────────────────────────────────────
        ("^fut_trade_cancel_build$",      cb_fut_trade_cancel_build),
        ("^fut_trade_cancel_",            cb_fut_trade_cancel_offer),
        ("^fut_trade_togglecard_",        cb_fut_trade_togglecard),
        ("^fut_trade_addcard_",           cb_fut_trade_addcard),
        ("^fut_trade_builder$",           cb_fut_trade_builder),
        ("^fut_trade_setcoins$",          cb_fut_trade_setcoins),
        ("^fut_trade_send$",              cb_fut_trade_send),
        ("^fut_trade_accept_",            cb_fut_trade_accept),
        ("^fut_trade_decline_",           cb_fut_trade_decline),
        ("^fut_trade_view_",              cb_fut_trade_view),
        ("^fut_trade_inbox$",             cb_fut_trade_inbox),
        ("^fut_trade_outbox$",            cb_fut_trade_outbox),
        ("^fut_trade_target_",            cb_fut_trade_target),   # выбор игрока → билдер
        ("^fut_trade_newp_",              cb_fut_trade_new_page), # пагинация списка
        ("^fut_trade_new$",               cb_fut_trade_new),
        ("^fut_trade$",                   cb_fut_trade),
        # ── Турнир-Драфт (специфичные — до fut_tour$) ─────────────────────────
        ("^fut_tour_pick_",               cb_fut_tour_pick),
        ("^fut_tour_dform_",              cb_fut_tour_dform),
        ("^fut_tour_draft_",              cb_fut_tour_draft),
        ("^fut_tour_start_",              cb_fut_tour_start),
        ("^fut_tour_rejt_",               cb_fut_tour_rejt),
        ("^fut_tour_join_",               cb_fut_tour_join),
        ("^fut_tour_inv_",                cb_fut_tour_inv),
        ("^fut_tour_invite_",             cb_fut_tour_invite),
        ("^fut_tour_leave_",              cb_fut_tour_leave),
        ("^fut_tour_bracket_",            cb_fut_tour_bracket),
        ("^fut_tour_lobby_",              cb_fut_tour_lobby),
        ("^fut_tour_create$",             cb_fut_tour_create),
        ("^fut_tour$",                    cb_fut_tour),
        # ── Драфт ─────────────────────────────────────────────────────────────
        ("^fut_draft_multi_invp_",        cb_fut_draft_multi_invpage),
        ("^fut_draft_multi_inv_",         cb_fut_draft_multi_invite),
        ("^fut_draft_mform_",             cb_fut_draft_multi_form),
        ("^fut_draft_mpick_",             cb_fut_draft_multi_pick),
        ("^fut_draft_join_",              cb_fut_draft_multi_join),
        ("^fut_draft_decline_",           cb_fut_draft_multi_decline),
        ("^fut_draft_multi$",             cb_fut_draft_multi),
        ("^fut_draft_form_",              cb_fut_draft_form),
        ("^fut_draft_pick_",              cb_fut_draft_pick),
        ("^fut_draft_play$",              cb_fut_draft_play),
        ("^fut_draft_match$",             cb_fut_draft_match),
        ("^fut_draft_reward$",            cb_fut_draft_reward),
        ("^fut_draft_solo$",              cb_fut_draft_solo_start),
        ("^fut_draft$",                   cb_fut_draft),
    ]
