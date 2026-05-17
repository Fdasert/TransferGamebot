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


def _draw_players(min_r: int, max_r: int, n: int) -> list[dict]:
    res = (
        db.get_client()
        .table("fut_players")
        .select("id, name, club, nation, position, rating, version, pac, sho, pas, dri, def, phy")
        .gte("rating", min_r).lte("rating", max_r)
        .execute()
    )
    return _weighted_sample(res.data or [], n)


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
    for cid in to_delete:
        db.get_client().table("user_club").delete().eq("id", cid).execute()
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
    _interaction_choices[user_id] = None          # сбрасываем предыдущий выбор
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        v = _interaction_choices.get(user_id)
        if v is not None:
            _interaction_choices.pop(user_id, None)
            return v
        await asyncio.sleep(0.3)
    _interaction_choices.pop(user_id, None)
    return None


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

async def _run_match_animation(
    bot, chat_id: int, message_id: int | None,
    my_name: str, opp_name: str,
    my_uid: int,
    stats: dict,
    r_delta: int, coins: int,
    shared_moments: list[dict] | None = None,
) -> None:
    """Анимирует матч с синхронизированными интерактивными моментами."""

    sent_id = message_id

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

    # ── Интерактивный момент (синхронизированный с соперником) ────────────────
    async def _interactive_shared(moment_cfg: dict) -> int:
        moment: _MatchMoment = _match_moments.get(moment_cfg["moment_id"])
        if not moment:
            return 0

        mtype        = moment_cfg["type"]
        minute       = moment_cfg["minute"]
        is_attacker  = (my_uid == moment.attacker_uid)

        ATT_OPTS = {
            "penalty":  [("↖️ Лево", "left"), ("⬆️ Центр", "center"), ("↗️ Право", "right")],
            "1v1":      [("⚡ Удар", "shot"), ("🎯 Обводка", "dribble")],
            "freekick": [("⬆️ Верхний угол", "top"), ("⬇️ Нижний угол", "bottom")],
        }
        KPR_OPTS = {
            "penalty":  [("↖️ Лево", "left"), ("⬆️ Центр", "center"), ("↗️ Право", "right")],
            "1v1":      [("⚡ Атаковать", "attack"), ("🧤 В ворота", "stay")],
            "freekick": [("⬆️ Прыгаю вверх", "up"), ("⬇️ Прыгаю вниз", "down")],
        }
        ATT_PROMPT = {
            "penalty":  f"🟡 *{minute}'* — *ПЕНАЛЬТИ!*\n\nВыбирай угол удара!\n⏱ _30 секунд_",
            "1v1":      f"🔥 *{minute}'* — *ВЫХОД ОДИН НА ОДИН!*\n\nЧто делаешь?\n⏱ _30 секунд_",
            "freekick": f"⚡ *{minute}'* — *ШТРАФНОЙ!*\n\nКуда бьёшь?\n⏱ _30 секунд_",
        }
        KPR_PROMPT = {
            "penalty":  f"🟡 *{minute}'* — *Соперник бьёт пенальти!*\n\nКуда прыгает твой вратарь?\n⏱ _30 секунд_",
            "1v1":      f"🔥 *{minute}'* — *Соперник выходит один на один!*\n\nДействия вратаря?\n⏱ _30 секунд_",
            "freekick": f"⚡ *{minute}'* — *Соперник бьёт штрафной!*\n\nКуда прыгаешь?\n⏱ _30 секунд_",
        }

        opts = ATT_OPTS[mtype] if is_attacker else KPR_OPTS[mtype]
        prompt = ATT_PROMPT[mtype] if is_attacker else KPR_PROMPT[mtype]

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(lbl, callback_data=f"fut_int_{val}") for lbl, val in opts
        ]])
        await _show(prompt, kb=kb)

        # Ждём свой выбор (30с)
        choice = await _wait_interaction(my_uid, timeout=30.0)
        auto   = choice is None
        if auto:
            choice = random.choice([v for _, v in opts])
        moment.submit(my_uid, choice)

        # Ждём пока соперник тоже выберет (максимум 5с, потом авто)
        result = await moment.wait_result(timeout=5.0)
        att_c = result["att"]
        kpr_c = result["kpr"]

        # Вычисляем исход
        if mtype == "penalty":
            goal = random.random() < (0.85 if att_c != kpr_c else 0.18)
        elif mtype == "1v1":
            if att_c == "shot":
                goal = random.random() < (0.70 if kpr_c == "attack" else 0.45)
            else:  # dribble
                goal = random.random() < (0.65 if kpr_c == "stay" else 0.30)
        else:  # freekick
            match_dir = (att_c == "top" and kpr_c == "up") or (att_c == "bottom" and kpr_c == "down")
            goal = random.random() < (0.20 if match_dir else 0.55)

        auto_tag = " _(авто)_" if auto else ""

        if goal:
            bonus = 150 if mtype == "penalty" else 100
            if is_attacker:
                result_txt = f"⚽ *ГОЛ!*{auto_tag}\n\n🔵 *{my_name}* реализует момент!\n💰 Бонус: *+{bonus}* монет!"
            else:
                result_txt = f"😤 *Вратарь пропустил*{auto_tag}\n\nСоперник забил..."
                bonus = 0
        else:
            if is_attacker:
                if mtype == "penalty":
                    fail = "Вратарь угадал угол!" if att_c == kpr_c else "Мимо ворот!"
                else:
                    fail = random.choice(["💨 Мимо!", "🧤 Сейв вратаря!", "🏹 В штангу!"])
                result_txt = f"❌ *Не получилось!*{auto_tag}\n\n{fail}"
                bonus = 0
            else:
                bonus = 100
                result_txt = f"🧤 *Сейв вратаря!*{auto_tag}\n\n🔵 *{my_name}* отбивает удар!\n💰 Бонус: *+{bonus}* монет!"

        await _show(result_txt)
        await asyncio.sleep(2.5)
        return bonus

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

    # ── Старт ─────────────────────────────────────────────────────────────────
    await _show(
        f"⚽ *Матч начинается!*\n\n"
        f"🔵 *{my_name}*\n"
        f"🔴 *{opp_name}*\n\n"
        f"_Команды выходят на поле..._"
    )
    await asyncio.sleep(1.5)

    # ── 1-й тайм — 0' ─────────────────────────────────────────────────────────
    await _show(
        f"⏱ *1-й тайм — 0:00*\n\n"
        f"🔵 *{my_name}*  *0* : *0*  🔴 *{opp_name}*\n\n"
        f"_Игра началась!_"
    )
    await asyncio.sleep(2.0)

    # ── 1-й тайм — 25' ─────────────────────────────────────────────────────────
    early_evs = [(m, t) for m, t in h1_events if m <= 25]
    shown = "\n".join(t for _, t in early_evs[-2:]) if early_evs else "_Осторожный старт..._"
    await _show(
        f"⏱ *1-й тайм — 25:00*\n\n"
        f"🔵 *{my_name}*  *0* : *0*  🔴 *{opp_name}*\n\n"
        f"{shown}"
    )
    await asyncio.sleep(2.0)

    # ── Интерактив 1-го тайма ─────────────────────────────────────────────────
    for m_cfg in h1_moments:
        bonus_total += await _interactive_shared(m_cfg)

    # ── 1-й тайм — 40' ─────────────────────────────────────────────────────────
    late_h1 = [(m, t) for m, t in h1_events if 25 < m <= 45]
    if late_h1:
        shown2 = "\n".join(t for _, t in late_h1[-2:])
        await _show(
            f"⏱ *1-й тайм — 40:00*\n\n"
            f"🔵 *{my_name}*  *{h1_a}* : *{h1_b}*  🔴 *{opp_name}*\n\n"
            f"{shown2}"
        )
        await asyncio.sleep(1.8)

    # ── Перерыв — 45' ─────────────────────────────────────────────────────────
    await _show(
        f"🕐 *Перерыв — 45'*\n\n"
        f"🔵 *{my_name}*  *{h1_a}* : *{h1_b}*  🔴 *{opp_name}*\n\n"
        f"📊 Владение 1-го тайма: *{poss_a}%* — *{poss_b}%*\n"
        f"_Команды уходят в раздевалку..._"
    )
    await asyncio.sleep(2.2)

    # ── 2-й тайм — 45' ─────────────────────────────────────────────────────────
    if score_a != score_b:
        leading = my_name if score_a > score_b else opp_name
        tension = f"_{leading} ведёт! Нужно отыгрываться..._"
    else:
        tension = "_Равная борьба — всё решится сейчас!_"
    await _show(
        f"⏱ *2-й тайм — 45:00*\n\n"
        f"🔵 *{my_name}*  *{h1_a}* : *{h1_b}*  🔴 *{opp_name}*\n\n"
        f"{tension}"
    )
    await asyncio.sleep(2.0)

    # ── 2-й тайм — 65' ─────────────────────────────────────────────────────────
    mid2_evs = [(m, t) for m, t in h2_events if m <= 65]
    if mid2_evs:
        shown3 = "\n".join(t for _, t in mid2_evs[-2:])
        await _show(
            f"⏱ *2-й тайм — 65:00*\n\n"
            f"🔵 *{my_name}*  *{h1_a}* : *{h1_b}*  🔴 *{opp_name}*\n\n"
            f"{shown3}"
        )
        await asyncio.sleep(2.0)

    # ── Интерактив 2-го тайма ─────────────────────────────────────────────────
    for m_cfg in h2_moments:
        bonus_total += await _interactive_shared(m_cfg)

    # ── Концовка — 80'+ ───────────────────────────────────────────────────────
    late2_evs = [(m, t) for m, t in h2_events if m > 65]
    if late2_evs:
        shown4 = "\n".join(t for _, t in late2_evs[-2:])
        await _show(
            f"🔥 *Горячая концовка!*\n\n"
            f"🔵 *{my_name}*  *{score_a}* : *{score_b}*  🔴 *{opp_name}*\n\n"
            f"{shown4}"
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

    r_str     = f"+{r_delta}" if r_delta >= 0 else str(r_delta)
    total_c   = coins + bonus_total
    c_str     = f"+{total_c}"
    bonus_str = f"  _(+{bonus_total} бонус)_" if bonus_total else ""

    acc_a_str = f"{stats['acc_a']}%"
    acc_b_str = f"{stats['acc_b']}%"
    pos_a_str = f"{poss_a}%"
    pos_b_str = f"{poss_b}%"

    kb = InlineKeyboardMarkup([
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
        f"📈 Рейтинг:   *{r_str}* ⭐\n"
        f"💰 Монеты:    *{c_str}* 💰{bonus_str}\n",
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
            shared_moments.append({
                "half": half_num, "minute": minute, "type": mtype,
                "attacker_uid": attacker, "keeper_uid": keeper, "moment_id": mid,
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
#  REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

def fut_handlers() -> list[tuple[str, Any]]:
    return [
        # Меню и паки
        ("^fut_menu$",            cb_fut_menu),
        ("^fut_packs$",           cb_fut_packs),
        ("^fut_buy_",             cb_fut_buy),
        ("^fut_no_coins$",        cb_fut_no_coins),
        # Клуб
        ("^fut_sell_confirm_",    cb_fut_sell_confirm),
        ("^fut_card_",            cb_fut_card),
        ("^fut_sell_dupes$",      cb_fut_sell_dupes),
        ("^fut_club_",            cb_fut_club),
        # Команда (специфичные — до общего fut_team$)
        ("^fut_team_setform_",    cb_fut_team_setform),
        ("^fut_team_remove_",     cb_fut_team_remove),
        ("^fut_team_slot_",       cb_fut_team_slot),
        ("^fut_team_pick_",       cb_fut_team_pick),
        ("^fut_team_form$",       cb_fut_team_form),
        ("^fut_team$",            cb_fut_team),
        # Матчи (специфичные — до общего fut_match)
        ("^fut_int_",             cb_fut_interact),      # интерактивный выбор (до fut_match)
        ("^fut_challenge_",       cb_fut_challenge),
        ("^fut_send_",            cb_fut_send),
        ("^fut_accept_",          cb_fut_accept),
        ("^fut_decline_",         cb_fut_decline),
        ("^fut_match_history$",   cb_fut_match_history),
        ("^fut_match$",           cb_fut_match),
    ]
