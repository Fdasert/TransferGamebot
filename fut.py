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


# Женские лиги и версии — исключаем из всех пулов карточек
_FEMALE_LEAGUE_KEYWORDS = (
    # league-name keywords (case-insensitive substring match)
    "women", "woman", "female",
    "frauen",                        # Frauen-Bundesliga (Germany)
    "féminin", "feminin",            # Division 1 Féminin (France)
    "damen",                         # various German
    "mujer", "femenin",              # Spanish
    "damall",                        # Damallsvenskan (Sweden)
    "wsl",                           # Barclays WSL (England)
    "nwsl",                          # NWSL (USA)
    "liga f",                        # Liga F (Spain)
    "uwcl",                          # Women's Champions League
    "serie a w",                     # Serie A Women (Italy)
    "d1 fém",                        # shorthand
    "primera i",                     # Primera Iberdrola (Spain)
    "a-league w",                    # A-League Women (Australia)
    "kingsford",                     # NWSL variant
    "roshn",                         # sometimes used in women's comps
)
_FEMALE_VERSION_KEYWORDS = (
    "wfas", "wplayer", "w_player", "female", "women",
)

def _is_male_player(p: dict) -> bool:
    """Return True if the player is NOT from a female league or version."""
    league  = (p.get("league")  or "").lower()
    version = (p.get("version") or "").lower()
    if any(kw in league  for kw in _FEMALE_LEAGUE_KEYWORDS):
        return False
    if any(kw in version for kw in _FEMALE_VERSION_KEYWORDS):
        return False
    return True


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
            "fut_players(id, name, club, nation, league, position, rating, version, pac, sho, pas, dri, def, phy)"
        )
        .eq("user_id", user_id)
        .execute()
    )
    cards = []
    for row in (res.data or []):
        p = row.get("fut_players") or {}
        # Exclude female players everywhere — club view, team, strength calc, etc.
        if not _is_male_player(p):
            continue
        cards.append({
            "club_id":  row["id"],
            "acquired": row.get("acquired_at", ""),
            "name":     p.get("name", "?"),
            "club":     p.get("club", "?"),
            "nation":   p.get("nation", "?"),
            "position": p.get("position", "?"),
            "rating":   p.get("rating", 0),
            "version":  p.get("version", ""),
            "league":   p.get("league", ""),
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
            [InlineKeyboardButton("🌍 Чемпионат мира", callback_data="fut_wc")],
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

    # ── Pack achievements ─────────────────────────────────────────────────
    _pack_achs = []
    if db.award_achievement(uid, "first_pack"):
        _pack_achs.append(("📦", "Первый пак", "Открыть первый пак карточек", 0))
    if any(c.get("rating") == 97 for c in cards):
        if db.award_achievement(uid, "got_97"):
            _pack_achs.append(("👑", "Золотой грааль", "Вытащить карточку OVR 97", 15_000))

    for emoji, name, desc, reward in _pack_achs:
        if reward:
            db.add_coins(uid, reward)
        reward_line = f"\n💰 *\\+{reward:,} монет*".replace(",", " ") if reward else ""
        try:
            await ctx.bot.send_message(
                uid,
                f"🏅 *НОВОЕ ДОСТИЖЕНИЕ\\!*\n{'─' * 22}\n{emoji} *{name}*\n_{desc}_{reward_line}",
                parse_mode="MarkdownV2",
            )
        except Exception:
            pass


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
        _AUTO = {
            "penalty":  {"att": ["left", "center", "right"],              "kpr": ["left", "center", "right"]},
            "1v1":      {"att": ["shot", "dribble"],                       "kpr": ["attack", "stay"]},
            "freekick": {"att": ["top", "bottom"],                         "kpr": ["up", "down"]},
            "corner":   {"att": ["cross_center", "cross_far", "short"],    "kpr": ["rush", "center", "near_post"]},
            "var":      {"att": ["defend", "accept"],                      "kpr": ["challenge", "accept"]},
        }
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if self.is_ready():
                break
            await asyncio.sleep(0.3)
        choices = _AUTO.get(self.type, {"att": ["left", "center", "right"], "kpr": ["left", "center", "right"]})
        if not self.att_choice:
            self.att_choice = random.choice(choices["att"])
        if not self.kpr_choice:
            self.kpr_choice = random.choice(choices["kpr"])
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
    "Игра по счёту — каждый пас выверен до миллиметра.",
    "Команда уверенно держит нити игры в своих руках.",
    "Защитные редуты выстроены безупречно.",
    "Счёт устраивает — незачем рисковать.",
    "Уверенность растёт с каждой минутой владения.",
    "Соперник нервничает — ведущая команда этим пользуется.",
]

_COMM_TRAILING = [
    "Нужен гол — команда прибавляет в интенсивности!",
    "Время поджимает. Атаки следуют одна за другой!",
    "Отчаянный поиск гола — всё поставлено на карту.",
    "Тренер делает ставку на атаку — все вперёд!",
    "Каждая минута без гола — как игла в сердце болельщика.",
    "Надо забивать! Команда бросается в атаку!",
    "Риск оправдан — другого выхода нет!",
    "Давление нарастает — соперник едва сдерживает натиск.",
    "Мяч снова и снова летит в сторону чужих ворот.",
    "Вся команда в атаке — защита оголена, но выбора нет.",
    "Один точный удар — и всё изменится!",
    "Поверить в камбэк — и он случится.",
    "Ничто не решено, пока не прозвучал финальный свисток.",
]

_COMM_DRAW_LATE = [
    "Счёт равный — всё решится в эти минуты!",
    "Ни одна команда не уступает — великолепный матч!",
    "Напряжение зашкаливает при равном счёте!",
    "Любой момент может стать решающим!",
    "Обе команды хотят только победы — никаких компромиссов!",
    "Одно очко мало для обоих — ищем гол-победитель!",
    "Равенство на табло — неравенство в сердцебиении.",
    "Кто первый дрогнет — тот проиграет.",
    "Ничья устраивает никого — игра продолжается на пределе.",
    "Стадион притих в ожидании развязки.",
    "Одна ошибка — и всё решено.",
    "Борьба идёт за каждый сантиметр поля.",
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

    events: list[tuple[int, str, str, str]] = []  # (minute, text, etype, team)

    sc_a = sa.get("scorers", ["Игрок"])
    sc_b = sb.get("scorers", ["Игрок"])
    nm_a = sa.get("all_names", ["Игрок"])
    nm_b = sb.get("all_names", ["Игрок"])

    def _chance(att: float, def_: float, scorers: list, is_penalty: bool,
                minute: int, is_a: bool) -> tuple[str, str, str] | None:
        nonlocal score_a, score_b, shots_a, shots_b, corners_a, corners_b
        # Усиленная зависимость от разницы атт/деф: 90атт vs 70деф ≈ +35% к голам
        _base  = att / max(att + def_, 1)
        _steep = max(0.15, min(0.85, 0.5 + (_base - 0.5) * 2.5))
        # Пенальти в симуляции: реалистичная конверсия ~75%, не GOAL_BASE*0.7≈35%
        goal_prob = max(0.60, min(0.90, _steep * 1.5)) if is_penalty else _steep * GOAL_BASE * 2
        r = random.random()
        name = random.choice(scorers)
        team = "a" if is_a else "b"
        if r < goal_prob:
            if is_a:
                score_a += 1; shots_a += 1
            else:
                score_b += 1; shots_b += 1
            prefix = "🟡→⚽" if is_penalty else "⚽"
            return (f"{prefix} *{minute}'* — *{name}*!", "goal", team)
        elif r < goal_prob + 0.28:
            if is_a: shots_a += 1
            else:    shots_b += 1
            return (f"🧤 *{minute}'* — {name}: {random.choice(_SAVES)}", "save", team)
        elif r < goal_prob + 0.50:
            return (f"💨 *{minute}'* — {name}: {random.choice(_MISSES)}", "miss", team)
        else:
            if is_a: corners_a += 1
            else:    corners_b += 1
            return (f"🚩 *{minute}'* — Угловой", "corner", team)

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
                if ev: events.append((minute, ev[0], ev[1], ev[2]))
            if pen_minute_b and abs(minute - pen_minute_b) < 5:
                pen_minute_b = None
                ev = _chance(sb["att"], sa["def_"], sc_b, True, minute, False)
                if ev: events.append((minute, ev[0], ev[1], ev[2]))

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
                    if ev: events.append((minute, ev[0], ev[1], ev[2]))
                else:
                    if random.random() < 0.20:
                        events.append((minute, f"⚙️ *{minute}'* — {random.choice(_PRESSURE)}", "pressure", "a"))
                if random.random() < CARD_PROB and yellows_a < 3 and nm_a:
                    yellows_a += 1
                    name = random.choice(nm_a)
                    events.append((minute, f"🟨 *{minute}'* — {name} (предупреждение)", "card", "a"))
                    if yellows_a == 2 and random.random() < 0.25:
                        red_a = True
                        events.append((minute, f"🟥 *{minute}'* — {name} — УДАЛЁН!", "card", "a"))
            else:
                poss_b += 5
                p = random.randint(9, 16)
                passes_b += p
                acc = min(0.93, 0.62 + sb.get("pas_avg", 70) / 400)
                acc_b_sum += acc; acc_blk_b += 1
                if random.random() < 0.38:
                    ev = _chance(sb["att"], sa["def_"], sc_b, False, minute, False)
                    if ev: events.append((minute, ev[0], ev[1], ev[2]))
                else:
                    if random.random() < 0.20:
                        events.append((minute, f"⚙️ *{minute}'* — {random.choice(_PRESSURE)}", "pressure", "b"))
                if random.random() < CARD_PROB and yellows_b < 3 and nm_b:
                    yellows_b += 1
                    name = random.choice(nm_b)
                    events.append((minute, f"🟨 *{minute}'* — {name} (предупреждение)", "card", "b"))
                    if yellows_b == 2 and random.random() < 0.25:
                        red_b = True
                        events.append((minute, f"🟥 *{minute}'* — {name} — УДАЛЁН!", "card", "b"))

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
                if ev: events.append((inj, f"⏱ {ev[0]}", ev[1], ev[2]))

        # Фиксируем счёт первого тайма
        if half == 0:
            h1_score_a = score_a
            h1_score_b = score_b

    events.sort(key=lambda x: x[0])

    total_poss = poss_a + poss_b or 1
    acc_a = round((acc_a_sum / max(acc_blk_a, 1)) * 100)
    acc_b = round((acc_b_sum / max(acc_blk_b, 1)) * 100)

    h1_evs = [(m, t, e, tm) for m, t, e, tm in events if m <= 45]
    h2_evs = [(m, t, e, tm) for m, t, e, tm in events if m > 45]

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
    Гарантированно 1 момент на тайм (итого 2 shared). Возвращает список
    moment-cfg для _run_match_animation."""
    moment_pool = ["penalty", "1v1", "freekick", "corner", "var"]
    shared: list[dict] = []
    for half_num in (1, 2):
        mtype    = random.choice(moment_pool)
        # H1: момент показывается после тика 35'/40' → минута 36-44
        # H2: момент показывается после тика 65' и замены → минута 66-74
        minute   = random.randint(36, 44) if half_num == 1 else random.randint(66, 74)
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
    Гарантированно 1 момент на тайм. Возвращает список moment-cfg."""
    BOT_UID = _BOT_UID_SENTINEL
    moment_pool = ["penalty", "1v1", "freekick", "corner", "var"]
    shared: list[dict] = []
    _BOT_CHOICES = {
        "penalty":  {"att": ["left", "center", "right"],              "kpr": ["left", "center", "right"]},
        "1v1":      {"att": ["shot", "dribble"],                       "kpr": ["attack", "stay"]},
        "freekick": {"att": ["top", "bottom"],                         "kpr": ["up", "down"]},
        "corner":   {"att": ["cross_center", "cross_far", "short"],    "kpr": ["rush", "center", "near_post"]},
        "var":      {"att": ["defend", "accept"],                      "kpr": ["challenge", "accept"]},
    }
    for half_num in (1, 2):
        mtype    = random.choice(moment_pool)
        # H1: момент показывается после тика 35'/40' → минута 36-44
        # H2: момент показывается после тика 65' и замены → минута 66-74
        minute   = random.randint(36, 44) if half_num == 1 else random.randint(66, 74)
        attacker = random.choice([human_uid, BOT_UID])
        keeper   = BOT_UID if attacker == human_uid else human_uid
        mid      = f"{match_key}_{half_num}_{mtype}"
        moment   = _MatchMoment(mtype, attacker, keeper)
        _match_moments[mid] = moment

        att_str  = human_sa["att"] if attacker == human_uid else bot_sa["att"]
        def_str  = human_sa["def_"] if keeper == human_uid else bot_sa["def_"]

        # Бот немедленно делает выбор
        bot_role = "att" if attacker == BOT_UID else "kpr"
        bot_choice = random.choice(_BOT_CHOICES[mtype][bot_role])
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
    i_am_team_a: bool = True,
    hide_rewards: bool = False,
) -> tuple[int, int, int]:
    """Анимирует матч с живым счётом, 8+ чекпоинтами и 3-4 интерактивными моментами.
    Возвращает (live_my, live_opp, bonus_coins)."""

    sent_id = message_id

    # ── Имена игроков из SA-дикта ─────────────────────────────────────────────
    _my_scorers  = (my_sa  or {}).get("scorers",  [my_name])
    _my_gk       = (my_sa  or {}).get("gk_name",  "Вратарь")
    _opp_scorers = (opp_sa or {}).get("scorers",  [opp_name])
    _opp_gk      = (opp_sa or {}).get("gk_name",  "Вратарь")
    _real_names  = [n for n in _my_scorers if n not in (my_name, "Игрок", "Бот")]
    _is_you      = (my_name == "Ты")

    all_events = stats.get("all_events", [])  # list[tuple[int,str,str,str]]
    poss_a     = stats["poss_a"]
    poss_b     = stats["poss_b"]

    bonus_total = 0
    # Живой счёт: my goals = тим "a" если i_am_team_a=True, иначе тим "b"
    live_my  = 0
    live_opp = 0

    def _count_goals_upto(max_min: int) -> tuple[int, int]:
        """Считаем голы из событий симуляции до max_min включительно."""
        mg = og = 0
        for m, _, e, tm in all_events:
            if m <= max_min and e == "goal":
                if (i_am_team_a and tm == "a") or (not i_am_team_a and tm == "b"):
                    mg += 1
                else:
                    og += 1
        return mg, og

    def _evs_text(evs_subset: list, limit: int = 3) -> str:
        """Показывает события с маркером *(соп)* для событий соперника."""
        lines = []
        for _, t, e, tm in evs_subset[-limit:]:
            is_opp = tm and ((i_am_team_a and tm == "b") or (not i_am_team_a and tm == "a"))
            lines.append(t + (" (соп)" if is_opp else ""))
        return "\n".join(lines)

    def _score_line() -> str:
        return f"🔵 *{my_name}*  *{live_my}* : *{live_opp}*  🔴 *{opp_name}*"

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

    # ─────────────────────────────────────────────────────────────────────────
    #  Shared интерактивный момент (penalty / 1v1 / freekick / corner / var)
    # ─────────────────────────────────────────────────────────────────────────
    async def _interactive_shared(moment_cfg: dict) -> tuple[int, tuple[int, int]]:
        nonlocal live_my, live_opp
        moment: _MatchMoment = _match_moments.get(moment_cfg["moment_id"])
        if not moment:
            return 0, (0, 0)

        mtype       = moment_cfg["type"]
        minute      = moment_cfg["minute"]
        is_attacker = (my_uid == moment.attacker_uid)
        att_str     = moment_cfg.get("att_str", 80)
        def_str     = moment_cfg.get("def_str", 80)
        edge        = max(-0.15, min(0.15, (att_str - def_str) / 200))

        _att_player = random.choice(_my_scorers if is_attacker else _opp_scorers)
        _kpr_player = _opp_gk if is_attacker else _my_gk

        ATT_OPTS = {
            "penalty":  [("↖️ Влево", "left"), ("⬆️ Центр", "center"), ("↗️ Вправо", "right")],
            "1v1":      [("⚽ Бить!", "shot"), ("🎯 Обводка!", "dribble")],
            "freekick": [("⬆️ Верхний угол", "top"), ("⬇️ Нижний угол", "bottom")],
            "corner":   [("⬆️ Навес в центр", "cross_center"), ("↗️ Навес дальняя", "cross_far"), ("↙️ Короткий", "short")],
            "var":      [("✅ Это чистый момент!", "defend"), ("🤫 Не буду рисковать", "accept")],
        }
        KPR_OPTS = {
            "penalty":  [("↖️ Влево", "left"), ("⬆️ Центр", "center"), ("↗️ Вправо", "right")],
            "1v1":      [("⚡ Выйти навстречу", "attack"), ("🧤 Держать ворота", "stay")],
            "freekick": [("⬆️ Прыгнуть вверх", "up"), ("⬇️ Прыгнуть вниз", "down")],
            "corner":   [("🧤 На выход", "rush"), ("📍 Держать центр", "center"), ("📌 Ближняя штанга", "near_post")],
            "var":      [("📹 Оспорить! Нарушение!", "challenge"), ("✋ Принять решение", "accept")],
        }
        ATT_BASE = {
            "penalty":  (f"🟡 *{minute}'* — *ПЕНАЛЬТИ!*\n\n"
                         f"💥 *{_att_player}* {'выходишь' if _is_you else 'выходит'} к точке!\n"
                         f"*{_kpr_player}* в воротах... Куда бьёшь?"),
            "1v1":      (f"🔥 *{minute}'* — *ОДИН НА ОДИН!*\n\n"
                         f"⚡ *{_att_player}* {'врываешься' if _is_you else 'врывается'} в штрафную!\n"
                         f"*{_kpr_player}* выходит навстречу. Что делаешь?"),
            "freekick": (f"⚡ *{minute}'* — *ШТРАФНОЙ!*\n\n"
                         f"🎯 *{_att_player}* {'разбегаешься' if _is_you else 'разбегается'}!\n"
                         f"*{_kpr_player}* строит стенку. Куда бьёшь?"),
            "corner":   (f"🚩 *{minute}'* — *УГЛОВОЙ!*\n\n"
                         f"📐 *{_att_player}* {'подаёшь' if _is_you else 'подаёт'} из угла!\n"
                         f"*{_kpr_player}* командует обороной. Куда подаёшь?"),
            "var":      (f"📹 *{minute}'* — *VAR ПРОВЕРКА!*\n\n"
                         f"🔍 Спорный момент в штрафной! Судьи смотрят повтор...\n"
                         f"*{_att_player}* ждёт решения. Как {'действуешь' if _is_you else 'действует'}?"),
        }
        KPR_BASE = {
            "penalty":  (f"🟡 *{minute}'* — *Пенальти против {'тебя' if _is_you else 'вас'}!*\n\n"
                         f"😰 Нападающий соперника идёт к точке!\n"
                         f"*{_kpr_player}* готовится... Куда {'прыгаешь' if _is_you else 'прыгает'}?"),
            "1v1":      (f"🔥 *{minute}'* — *Один на один!*\n\n"
                         f"😤 Нападающий соперника выходит на *{_kpr_player}*!\n"
                         f"Что {'делаешь' if _is_you else 'делает'} вратарь?"),
            "freekick": (f"⚡ *{minute}'* — *Штрафной против {'тебя' if _is_you else 'вас'}!*\n\n"
                         f"😬 Соперник готовится к удару!\n"
                         f"*{_kpr_player}* строит стенку. Куда {'прыгаешь' if _is_you else 'прыгает'}?"),
            "corner":   (f"🚩 *{minute}'* — *Угловой у соперника!*\n\n"
                         f"😰 Соперник готовится к подаче!\n"
                         f"*{_kpr_player}* командует обороной. Что {'делаешь' if _is_you else 'делает'}?"),
            "var":      (f"📹 *{minute}'* — *VAR ПРОВЕРКА!*\n\n"
                         f"🔍 Спорный момент! Судьи смотрят повтор...\n"
                         f"*{_kpr_player}* в центре внимания. Что {'делаешь' if _is_you else 'делает'}?"),
        }

        opts      = ATT_OPTS[mtype] if is_attacker else KPR_OPTS[mtype]
        base_text = ATT_BASE[mtype] if is_attacker else KPR_BASE[mtype]

        # Для типов с 3 кнопками (penalty, corner) — 2+1 чтобы не сплющивались
        if len(opts) == 3:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(lbl, callback_data=f"fut_int_{val}") for lbl, val in opts[:2]],
                [InlineKeyboardButton(lbl, callback_data=f"fut_int_{val}") for lbl, val in opts[2:]],
            ])
        else:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(lbl, callback_data=f"fut_int_{val}") for lbl, val in opts
            ]])
        choice, auto = await _wait_interaction_with_countdown(
            user_id=my_uid, base_prompt=base_text, kb=kb, show_fn=_show, timeout=30.0,
        )
        if auto:
            choice = random.choice([v for _, v in opts])
        moment.submit(my_uid, choice)

        await _show("✅ *Выбор сделан!* Ждём соперника...")
        result = await moment.wait_result(timeout=35.0)  # ≥ countdown (30s) + буфер
        att_c = result["att"]
        kpr_c = result["kpr"]

        # ── Вычисляем исход ────────────────────────────────────────────────────
        match_dir = False
        if mtype == "penalty":
            prob = max(0.55, min(0.97, 0.82 + edge)) if att_c != kpr_c else max(0.05, min(0.35, 0.15 + edge))
            goal = random.random() < prob
        elif mtype == "1v1":
            # shot: стабильнее, dribble рискованнее но контрит agressive вратаря
            # shot vs attack=0.55, shot vs stay=0.42
            # dribble vs attack=0.75 (вратарь выбежал и промахнулся), dribble vs stay=0.28
            base_p = (0.55 if kpr_c == "attack" else 0.42) if att_c == "shot" else (0.75 if kpr_c == "attack" else 0.28)
            goal = random.random() < max(0.05, min(0.95, base_p + edge))
        elif mtype == "freekick":
            match_dir = (att_c == "top" and kpr_c == "up") or (att_c == "bottom" and kpr_c == "down")
            base_p = 0.18 if match_dir else 0.52
            goal = random.random() < max(0.05, min(0.90, base_p + edge))
        elif mtype == "corner":
            if att_c == "short":
                base_p = 0.20 if kpr_c == "rush" else 0.32
            elif att_c == "cross_center":
                base_p = 0.55 if kpr_c == "rush" else (0.20 if kpr_c == "center" else 0.35)
            else:  # cross_far
                base_p = 0.45 if kpr_c == "near_post" else (0.28 if kpr_c == "center" else 0.22)
            goal = random.random() < max(0.05, min(0.88, base_p + edge))
        else:  # var — настоящий mind-game: defend рискованно, accept безопасно
            # defend vs challenge: VAR нашёл нарушение — гол отменён (плохо для атт)
            # defend vs accept:    соперник принял → гол засчитан (хорошо для атт)
            # accept vs challenge: атт умно принял → keeper зря оспорил (+ATT)
            # accept vs accept:    оба согласились → чистый шанс
            if att_c == "defend" and kpr_c == "challenge":
                base_p = max(0.20, min(0.45, 0.30 + edge))   # высокий риск, VAR на стороне def
            elif att_c == "defend" and kpr_c == "accept":
                base_p = max(0.60, min(0.85, 0.72 + edge))   # keeper сдался → хорошо для атт
            elif att_c == "accept" and kpr_c == "challenge":
                base_p = max(0.45, min(0.70, 0.58 + edge))   # атт принял, keeper зря рискнул
            else:  # accept vs accept
                base_p = max(0.35, min(0.60, 0.48 + edge))   # оба согласились → чистый шанс
            goal = random.random() < base_p

        # ── Кинематограф ───────────────────────────────────────────────────────
        if mtype == "penalty":
            _cine1 = f"📍 *{_att_player}* устанавливает мяч на точку...\n_Стадион замер в ожидании_"
            _kpr_dir = {"left": "влево", "right": "вправо", "center": "в центр"}.get(kpr_c, "")
            _cine2 = f"💨 Разбег! *{_att_player}* бьёт!\n🧤 *{_kpr_player}* прыгает {_kpr_dir}..."
        elif mtype == "1v1":
            _action  = "бьёт по воротам" if att_c == "shot" else "идёт в обводку"
            _kpr_act = "выходит навстречу" if kpr_c == "attack" else "держит позицию"
            _cine1   = f"⚡ *{_att_player}* врывается в штрафную!\n_Один шанс — всё или ничего!_"
            _cine2   = f"🏃 *{_att_player}* {_action}!\n🧤 *{_kpr_player}* {_kpr_act}..."
        elif mtype == "freekick":
            _kpr_jump = "вверх" if kpr_c == "up" else "вниз"
            _cine1    = f"🎯 *{_att_player}* разбегается к мячу...\n_Тишина на стадионе. Стенка выстроена._"
            _cine2    = f"💥 Удар! *{_kpr_player}* прыгает {_kpr_jump}..."
        elif mtype == "corner":
            _dir = {"cross_center": "в центр", "cross_far": "на дальнюю штангу", "short": "коротко"}.get(att_c, "")
            _kpr_act = {"rush": "идёт на перехват", "center": "держит центр", "near_post": "занял ближнюю штангу"}.get(kpr_c, "")
            _cine1   = f"🚩 *{_att_player}* устанавливает мяч у флажка...\n_Вся команда врывается в штрафную!_"
            _cine2   = f"⚡ Подача {_dir}! *{_kpr_player}* {_kpr_act}..."
        else:  # var
            _cine1 = f"📹 Повтор... Повтор...\n_Главный арбитр идёт к монитору_"
            _cine2 = f"😤 Игроки в нервном ожидании...\n_Решение принимается!_"

        await _show(_cine1)
        await asyncio.sleep(0.8)
        await _show(_cine2)
        await asyncio.sleep(0.7)

        # ── Человекочитаемые описания ─────────────────────────────────────────
        ATT_3 = {
            "left": "бьёт *влево* ↖️",      "center": "бьёт *в центр* ⬆️",
            "right": "бьёт *вправо* ↗️",
            "shot": "наносит *удар* ⚽",     "dribble": "идёт *в обводку* 🎯",
            "top": "целит *верхний угол* ⬆️","bottom": "целит *нижний угол* ⬇️",
            "cross_center": "подаёт *в центр* ⬆️", "cross_far": "подаёт *на дальнюю* ↗️",
            "short": "разыгрывает *коротко* ↙️",
            "defend": "настаивает на *чистом голе* ✅", "accept": "не оспаривает 🤫",
        }
        ATT_2 = {
            "left": "бьёшь *влево* ↖️",     "center": "бьёшь *в центр* ⬆️",
            "right": "бьёшь *вправо* ↗️",
            "shot": "наносишь *удар* ⚽",    "dribble": "идёшь *в обводку* 🎯",
            "top": "целишь *верхний угол* ⬆️","bottom": "целишь *нижний угол* ⬇️",
            "cross_center": "подаёшь *в центр* ⬆️", "cross_far": "подаёшь *на дальнюю* ↗️",
            "short": "разыгрываешь *коротко* ↙️",
            "defend": "настаиваешь на *чистом голе* ✅", "accept": "не оспариваешь 🤫",
        }
        KPR_3 = {
            "left": "прыгает *влево* ↖️",   "center": "держит *центр* ⬆️",
            "right": "прыгает *вправо* ↗️",
            "attack": "выходит *навстречу* ⚡", "stay": "держит *позицию* 🧤",
            "up": "прыгает *вверх* ⬆️",     "down": "прыгает *вниз* ⬇️",
            "rush": "идёт *на перехват* 🧤", "center": "держит *центр* 📍", "near_post": "занял *ближнюю штангу* 📌",
            "challenge": "оспаривает решение 📹", "accept": "принимает решение ✋",
        }
        KPR_2 = {
            "left": "прыгаешь *влево* ↖️",  "center": "держишь *центр* ⬆️",
            "right": "прыгаешь *вправо* ↗️",
            "attack": "выходишь *навстречу* ⚡", "stay": "держишь *позицию* 🧤",
            "up": "прыгаешь *вверх* ⬆️",    "down": "прыгаешь *вниз* ⬇️",
            "rush": "идёшь *на перехват* 🧤", "center": "держишь *центр* 📍", "near_post": "занял *ближнюю штангу* 📌",
            "challenge": "оспариваешь решение 📹", "accept": "принимаешь решение ✋",
        }

        auto_tag = " _(авто)_" if auto else ""
        if is_attacker:
            att_lbl = (ATT_2 if _is_you else ATT_3).get(att_c, att_c)
            kpr_lbl = KPR_3.get(kpr_c, kpr_c)
        else:
            att_lbl = ATT_3.get(att_c, att_c)
            kpr_lbl = (KPR_2 if _is_you else KPR_3).get(kpr_c, kpr_c)

        setup = f"⚽ *{_att_player}* {att_lbl}\n🧤 *{_kpr_player}* {kpr_lbl}"

        # ── Текст результата ──────────────────────────────────────────────────
        if goal:
            if mtype == "penalty":
                bonus = 150
            elif mtype == "var":
                bonus = 80
            else:
                bonus = 100
            if is_attacker:
                if mtype == "var":
                    excl = random.choice(["📹 VAR подтвердил: *ГОЛ ЗАСЧИТАН!*", "🟢 Чистый момент! VAR на стороне атаки!", f"✅ *{_att_player}* был в игре — *ГОЛ*!"])
                else:
                    excl = random.choice([f"*{_att_player}* — в девятку! 💥", "Чистый гол! 🚀", f"*{_kpr_player}* не угадал! 🎉", f"*{_att_player}* — мастер класс! 🔥", "ГОООЛ! Стадион взрывается! 🏟"])
                result_txt = f"⚽ *ГОЛ!*{auto_tag}\n\n{setup}\n\n🔥 {excl}\n💰 Бонус: *+{bonus}* монет!"
            else:
                if mtype == "var":
                    excl = random.choice(["📹 VAR засчитал гол — момент чистый 😞", "🔴 Нарушения нет — гол подтверждён!", f"❌ VAR не нашёл нарушения — гол засчитан!"])
                else:
                    excl = random.choice(["Не угадал... 😔", f"*{_att_player}* оказался хитрее 😤", "Обидный гол 😞"])
                result_txt = f"😤 *Гол в твои ворота!*{auto_tag}\n\n{setup}\n\n{excl}"
                bonus = 0
        else:
            bonus = 0
            if is_attacker:
                if mtype == "penalty":
                    fail = f"*{_kpr_player}* угадал угол! 🧤" if att_c == kpr_c else random.choice([f"*{_att_player}* — рядом со штангой! 😬", "Мяч над перекладиной! 💨", f"*{_kpr_player}* вытянул руку! 🧤"])
                elif mtype == "1v1":
                    fail = (f"*{_kpr_player}* угадал и взял! 🧤" if (att_c == "shot" and kpr_c == "attack") else random.choice(["В штангу! 💥", "Мимо! 💨", f"*{_kpr_player}* перекрыл угол! 🧤"]))
                elif mtype == "freekick":
                    fail = f"*{_kpr_player}* угадал направление! 🧤" if match_dir else random.choice(["В стенку! 💨", "Над перекладиной! 💨", f"*{_kpr_player}* легко взял! 🧤"])
                elif mtype == "corner":
                    fail = random.choice([f"*{_kpr_player}* выбил в безопасное место! 🧤", "Прошло выше ворот! 💨", "Оборона справилась! 🛡", f"*{_kpr_player}* поймал мяч! 🧤"])
                else:  # var
                    fail = random.choice(["📹 VAR отменил: *нарушение при подаче!*", "🔴 VAR нашёл офсайд!", "❌ Момент не засчитан!"])
                result_txt = f"❌ *Не получилось!*{auto_tag}\n\n{setup}\n\n{fail}"
            else:
                bonus = 100
                if mtype == "penalty":
                    excl = f"*{_kpr_player}* угадал угол! 🎯" if att_c == kpr_c else random.choice([f"*{_kpr_player}* — невероятный рефлекс! 🏆", f"*{_kpr_player}* — потрясающий сейв! 🔥"])
                elif mtype == "1v1":
                    excl = f"*{_kpr_player}* выходит и накрывает! ⚡" if kpr_c == "attack" else random.choice([f"*{_kpr_player}* — правильная позиция! 🧤", f"*{_kpr_player}* сужает угол! 🏆"])
                elif mtype == "freekick":
                    excl = f"*{_kpr_player}* угадал направление! 🎯" if match_dir else random.choice([f"*{_kpr_player}* — рефлекс на высшем уровне! 🏆", f"*{_kpr_player}* — великолепный сейв! 🔥"])
                elif mtype == "corner":
                    excl = random.choice([f"*{_kpr_player}* выбил кулаком! 💪", "Оборона успела! 🛡", f"*{_kpr_player}* поймал подачу! 🧤"])
                else:  # var
                    excl = random.choice(["📹 VAR отменил гол соперника! 🎯", "🟢 VAR на твоей стороне — нарушение!", f"*{_kpr_player}* добился справедливости! ✅"])
                result_txt = f"🧤 *СЕЙВ!*{auto_tag}\n\n{setup}\n\n🔵 {excl}\n💰 Бонус: *+{bonus}* монет!"

        await _show(result_txt)
        await asyncio.sleep(2.0)
        if goal:
            if is_attacker:
                live_my += 1
                return bonus, (1, 0)
            else:
                live_opp += 1
                return bonus, (0, 1)
        return bonus, (0, 0)

    # ─────────────────────────────────────────────────────────────────────────
    #  Solo: Аут (throw-in) — solo choice, лёгкий бонус
    # ─────────────────────────────────────────────────────────────────────────
    async def _interactive_throwin(minute: int) -> int:
        """Возвращает bonus_coins."""
        _pl = random.choice(_my_scorers)
        prompt = (
            f"🎾 *{minute}'* — *АУТ!*\n\n"
            f"*{_pl}* {'берёшь' if _is_you else 'берёт'} мяч у флажка.\n"
            f"Куда разыгрываешь вброс?"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("↖️ Длинный вброс", callback_data="fut_int_long"),
            InlineKeyboardButton("🔄 Короткий", callback_data="fut_int_short"),
        ], [
            InlineKeyboardButton("⚡ Быстро вперёд", callback_data="fut_int_forward"),
        ]])
        choice, auto = await _wait_interaction_with_countdown(
            user_id=my_uid, base_prompt=prompt, kb=kb, show_fn=_show, timeout=20.0,
        )
        if auto:
            choice = random.choice(["long", "short", "forward"])
        auto_tag = " _(авто)_" if auto else ""
        _outcomes = {
            # EV ≈ равен (~19-20): нет доминирующей стратегии
            "long":    (0.22, f"⚡ Длинный вброс — опасный момент у штрафной!{auto_tag}", 90),  # EV≈19.8
            "short":   (0.55, f"🔄 Короткий пас — сохраняем владение!{auto_tag}", 35),           # EV≈19.3
            "forward": (0.36, f"⚡ Быстрый вброс — прорыв в атаку!{auto_tag}", 55),              # EV≈19.8
        }
        prob, ok_txt, bonus = _outcomes.get(choice, (0.25, "...", 40))
        if random.random() < prob:
            await _show(f"✅{ok_txt}\n💰 Бонус: *+{bonus}* монет!")
            await asyncio.sleep(1.5)
            return bonus
        else:
            await _show(f"❌ Перехвачено соперником!{auto_tag}")
            await asyncio.sleep(1.2)
            return 0

    # ─────────────────────────────────────────────────────────────────────────
    #  Solo: Тактика на перерыве (halftime tactics)
    # ─────────────────────────────────────────────────────────────────────────
    async def _interactive_tactics(ht_my: int, ht_opp: int) -> int:
        deficit = ht_opp - ht_my
        if deficit > 0:
            situation = f"⚠️ Проигрываешь — нужен гол во втором тайме!"
            correct   = "press"
        elif deficit < 0:
            situation = f"✅ Ведёшь — удержи результат!"
            correct   = "defensive"
        else:
            situation = f"🤝 Ничья — нужна победа во втором тайме!"
            correct   = "press"
        prompt = (
            f"🕐 *Перерыв — тактика на 2-й тайм*\n\n"
            f"{_score_line()}\n\n"
            f"{situation}"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔥 Прессинг", callback_data="fut_int_press"),
            InlineKeyboardButton("⚡ Контратаки", callback_data="fut_int_counter"),
        ], [
            InlineKeyboardButton("🛡 Оборона", callback_data="fut_int_defensive"),
        ]])
        choice, auto = await _wait_interaction_with_countdown(
            user_id=my_uid, base_prompt=prompt, kb=kb, show_fn=_show, timeout=25.0,
        )
        if auto:
            choice = correct
        auto_tag = " _(авто)_" if auto else ""
        _names = {"press": "Прессинг 🔥", "counter": "Контратаки ⚡", "defensive": "Оборона 🛡"}
        cname = _names.get(choice, choice)
        if choice == correct:
            bonus = 100
            txt = f"🧠 *Тактика: {cname}*{auto_tag}\n\n✅ Верное решение! Команда заряжена!\n💰 Тактический бонус: *+{bonus}* монет!"
        elif choice == "counter":
            bonus = 55
            txt = f"🧠 *Тактика: {cname}*{auto_tag}\n\n✅ Разумный план!\n💰 Тактический бонус: *+{bonus}* монет!"
        else:
            bonus = 0
            txt = f"🧠 *Тактика: {cname}*{auto_tag}\n\n_Посмотрим, как сыграет команда..._"
        await _show(txt)
        await asyncio.sleep(2.0)
        return bonus

    # ─────────────────────────────────────────────────────────────────────────
    #  Solo: Тактическая замена (~60')
    # ─────────────────────────────────────────────────────────────────────────
    async def _interactive_substitution(minute: int) -> int:
        nonlocal live_my
        deficit = live_opp - live_my
        _pl = random.choice(_my_scorers)
        situation = '⚠️ Проигрываешь' if deficit > 0 else ('✅ Ведёшь' if deficit < 0 else '🤝 Ничья')
        prompt = (
            f"🔄 *{minute}'* — *ТАКТИЧЕСКАЯ ЗАМЕНА!*\n\n"
            f"{_score_line()}\n\n"
            f"{situation} — кого {'выпускаешь' if _is_you else 'выпускает тренер'}?"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚡ Нападающий", callback_data="fut_int_striker"),
            InlineKeyboardButton("🛡 Защитник",   callback_data="fut_int_defender"),
        ], [
            InlineKeyboardButton("🔄 Полузащитник", callback_data="fut_int_midfielder"),
        ]])
        choice, auto = await _wait_interaction_with_countdown(
            user_id=my_uid, base_prompt=prompt, kb=kb, show_fn=_show, timeout=20.0,
        )
        if auto:
            choice = "striker" if deficit > 0 else ("defender" if deficit < 0 else "midfielder")
        auto_tag = " _(авто)_" if auto else ""
        correct = "striker" if deficit > 0 else ("defender" if deficit < 0 else "midfielder")
        _names  = {"striker": "Нападающий ⚡", "defender": "Защитник 🛡", "midfielder": "Полузащитник 🔄"}
        cname   = _names.get(choice, choice)
        is_correct = (choice == correct)
        goal_scored = False
        if choice == "striker":
            bonus = 80 if is_correct else 20
            if is_correct and random.random() < 0.32:
                goal_scored = True
                bonus += 100
                txt = f"⚡ *{cname} на поле!*{auto_tag}\n\n🔥 Свежие ноги — сразу создаёт момент!\n⚽ *{_pl} — ГОЛ! Замена сыграла!*\n💰 Бонус: *+{bonus}* монет!"
            elif is_correct:
                txt = f"⚡ *{cname} на поле!*{auto_tag}\n\n💪 Свежие ноги давят на оборону!\n💰 Бонус: *+{bonus}* монет!"
            else:
                txt = f"🔄 *{cname} выходит*{auto_tag}\n\n_Рискованный выбор при таком счёте..._\n💰 Бонус: *+{bonus}* монет!"
        elif choice == "defender":
            bonus = 70 if is_correct else 20
            txt = f"🛡 *{cname} на поле!*{auto_tag}\n\n{'✅ Оборона укрепилась!' if is_correct else '_Атака ослаблена..._'}\n💰 Бонус: *+{bonus}* монет!"
        else:  # midfielder
            bonus = 50
            txt = f"🔄 *{cname} на поле!*{auto_tag}\n\n📊 Контроль мяча вырос!\n💰 Бонус: *+{bonus}* монет!"
        await _show(txt)
        await asyncio.sleep(2.0)
        if goal_scored:
            live_my += 1
        return bonus

    # ═════════════════════════════════════════════════════════════════════════
    #  АНИМАЦИЯ МАТЧА — каждые 5 минут (0→5→10→...→90)
    #  Живой счёт: sim_goals_upto(minute) + int_my + int_opp (interactive)
    # ═════════════════════════════════════════════════════════════════════════
    moments    = shared_moments or []
    h1_moments = [m for m in moments if m.get("half") == 1]
    h2_moments = [m for m in moments if m.get("half") == 2]
    do_throwin = random.random() < 0.35
    do_sub     = random.random() < 0.65

    int_my  = 0   # интерактивные голы моей команды
    int_opp = 0   # интерактивные голы соперника

    def _refresh_live(up_to_minute: int) -> None:
        """Обновляет live_my / live_opp = sim_goals + interactive."""
        nonlocal live_my, live_opp
        sm, so = _count_goals_upto(up_to_minute)
        live_my  = sm + int_my
        live_opp = so + int_opp

    # Обёртка над _interactive_shared для учёта int_my / int_opp
    async def _run_shared(m_cfg: dict) -> int:
        nonlocal int_my, int_opp, bonus_total
        b, (da, db) = await _interactive_shared(m_cfg)
        # _interactive_shared уже обновил live_my / live_opp напрямую,
        # синхронизируем int_* чтобы _refresh_live не затёр их
        int_my  += da
        int_opp += db
        bonus_total += b
        return b

    def _atm(minute: int) -> str:
        """Атмосферный комментарий в зависимости от счёта и стадии матча."""
        if minute <= 30:
            pool = _COMM_EARLY
        elif minute <= 45:
            pool = _COMM_EARLY if live_my == live_opp else (_COMM_LEADING if live_my > live_opp else _COMM_TRAILING)
        elif minute <= 60:
            pool = _COMM_SECOND_HALF
        elif live_my > live_opp:
            pool = _COMM_LEADING
        elif live_opp > live_my:
            pool = _COMM_TRAILING
        else:
            pool = _COMM_DRAW_LATE
        return random.choice(pool)

    async def _tick(minute: int, prev_minute: int) -> None:
        """Стандартный 5-минутный чекпоинт."""
        evs = [(m, t, e, tm) for m, t, e, tm in all_events if prev_minute < m <= minute]
        _refresh_live(minute)
        if evs:
            await _show(f"⏱ *{minute}'*\n\n{_score_line()}\n\n{_evs_text(evs)}")
            await asyncio.sleep(1.4)
        else:
            await _show(f"⏱ *{minute}'*\n\n{_score_line()}\n\n_{_atm(minute)}_")
            await asyncio.sleep(0.8)

    # ── Стартовый свисток ─────────────────────────────────────────────────────
    _star   = random.choice(_real_names) if _real_names else None
    ko_line = f"_Все взоры на *{_star}* — главная звезда атаки!_" if _star else f"_{random.choice(_COMM_KICKOFF)}_"
    await _show(
        f"⚽ *Матч начинается!*\n\n"
        f"🔵 *{my_name}*\n"
        f"🔴 *{opp_name}*\n\n"
        f"{ko_line}"
    )
    await asyncio.sleep(1.5)

    # ── 1-й тайм: тики каждые 5' ─────────────────────────────────────────────
    #  5' → 10' → 15' → [аут?] → 20' → 25' → 30'★ → 35' → [shared H1] → 40'
    await _tick(5,  0)
    await _tick(10, 5)
    await _tick(15, 10)

    # Аут — соло (~35% шанс, 18–24')
    if do_throwin:
        bonus_total += await _interactive_throwin(random.randint(18, 24))

    await _tick(20, 15)
    await _tick(25, 20)

    # 30' — особый тик со shoutout звезды
    evs30 = [(m, t, e, tm) for m, t, e, tm in all_events if 25 < m <= 30]
    _refresh_live(30)
    _shown30 = _evs_text(evs30) if evs30 else f"_{random.choice(_COMM_EARLY)}_"
    _shout30 = ""
    if _real_names:
        _pl30 = random.choice(_real_names)
        _shout30 = "\n" + random.choice([
            f"⚡ *{_pl30}* активно ищет голевой момент!",
            f"🎯 *{_pl30}* создаёт давление на оборону!",
            f"🔥 *{_pl30}* опасен в каждой атаке!",
        ])
    await _show(f"⏱ *30'*\n\n{_score_line()}\n\n{_shown30}{_shout30}")
    await asyncio.sleep(1.8 if evs30 else 1.2)

    await _tick(35, 30)

    # Shared интерактив 1-го тайма (всегда)
    for m_cfg in h1_moments:
        await _run_shared(m_cfg)

    await _tick(40, 35)

    # ── Перерыв — 45' + тактика (всегда) ─────────────────────────────────────
    evs_ht = [(m, t, e, tm) for m, t, e, tm in all_events if 40 < m <= 45]
    _refresh_live(45)
    ht_my, ht_opp = live_my, live_opp
    if ht_my > ht_opp:
        ht_lead = f"\n🔵 *{my_name}* ведёт! " + random.choice(_COMM_LEADING)
    elif ht_opp > ht_my:
        ht_lead = f"\n🔴 *{opp_name}* ведёт! " + random.choice(_COMM_TRAILING)
    else:
        ht_lead = f"\n_{random.choice(_COMM_DRAW_LATE)}_"
    ht_evs_txt = ("\n\n" + _evs_text(evs_ht)) if evs_ht else ""
    await _show(
        f"🕐 *Перерыв — 45'*{ht_evs_txt}\n\n"
        f"🔵 *{my_name}*  *{ht_my}* : *{ht_opp}*  🔴 *{opp_name}*{ht_lead}\n\n"
        f"📊 Владение 1-го тайма: *{poss_a}%* — *{poss_b}%*\n"
        f"_{random.choice(_COMM_HT)}_"
    )
    await asyncio.sleep(1.5)
    bonus_total += await _interactive_tactics(ht_my, ht_opp)

    # ── 2-й тайм: старт ──────────────────────────────────────────────────────
    sh_comm = random.choice(_COMM_SECOND_HALF)
    tension = f"_{my_name if ht_my > ht_opp else opp_name} ведёт! {sh_comm}_" if ht_my != ht_opp else f"_{sh_comm}_"
    # _refresh_live(45) уже вызван выше при перерыве — повторно не нужен
    await _show(f"⏱ *45' — 2-й тайм*\n\n{_score_line()}\n\n{tension}")
    await asyncio.sleep(1.8)

    # ── 2-й тайм: тики каждые 5' ─────────────────────────────────────────────
    #  50' → 55' → 60' → [замена?] → 65' → [shared H2] → 70' → 75' → 80' → 85'★
    await _tick(50, 45)
    await _tick(55, 50)
    await _tick(60, 55)
    await _tick(65, 60)

    # Тактическая замена — соло (~65% шанс, 61–67')
    # ВАЖНО: тик 65' должен быть ДО замены, чтобы счёт 65' не включал гол на 66'
    if do_sub:
        _lm_before = live_my
        bonus_total += await _interactive_substitution(random.randint(61, 67))
        int_my += live_my - _lm_before  # sync int_my если замена забила

    # Shared интерактив 2-го тайма (всегда)
    for m_cfg in h2_moments:
        await _run_shared(m_cfg)

    await _tick(70, 65)
    await _tick(75, 70)
    await _tick(80, 75)

    # 85' — горячая концовка
    evs85 = [(m, t, e, tm) for m, t, e, tm in all_events if 80 < m <= 85]
    _refresh_live(85)
    _climax   = random.choice(_COMM_CLIMAX)
    _end_shout = ""
    if live_my > live_opp and _real_names:
        _end_shout = f"\n💪 *{random.choice(_real_names)}* закрывает игру!"
    elif live_my < live_opp and _real_names:
        _end_shout = f"\n🔥 *{random.choice(_real_names)}* ищет спасительный гол!"
    _shown85 = _evs_text(evs85) if evs85 else f"_{_climax}_"
    await _show(
        f"🔥 *85' — Горячая концовка!*\n\n"
        f"{_score_line()}\n\n"
        f"{_shown85}"
        + (f"\n\n{_climax}" if evs85 else "")
        + _end_shout
    )
    await asyncio.sleep(1.8)

    # 90' — добавленное время (показываем только если были события)
    evs90 = [(m, t, e, tm) for m, t, e, tm in all_events if m > 85]
    _refresh_live(99)  # все оставшиеся голы симуляции
    if evs90:
        await _show(
            f"⏰ *90' — Добавленное время!*\n\n"
            f"{_score_line()}\n\n"
            f"{_evs_text(evs90)}"
        )
        await asyncio.sleep(1.5)

    # ── Финальный свисток ─────────────────────────────────────────────────────
    if live_my > live_opp:
        result_hdr = "🏆 *ПОБЕДА!*";  emoji_row = "🥇🎉🏆"
    elif live_my == live_opp:
        result_hdr = "🤝 *Ничья*";    emoji_row = "🤝"
    else:
        result_hdr = "💀 *Поражение*"; emoji_row = "😤"

    acc_a_str = f"{stats['acc_a']}%"
    acc_b_str = f"{stats['acc_b']}%"

    extra_lines = ""
    if not hide_rewards:
        total_c   = coins + bonus_total
        bonus_str = f"  _(+{bonus_total} бонус)_" if bonus_total else ""
        if r_delta != 0:
            r_str = f"+{r_delta}" if r_delta >= 0 else str(r_delta)
            extra_lines += f"📈 Рейтинг:   *{r_str}* ⭐\n"
        if total_c != 0:
            extra_lines += f"💰 Монеты:    *+{total_c}* 💰{bonus_str}\n"
    elif bonus_total:
        extra_lines = f"💰 Бонус матча: *+{bonus_total}* монет\n"

    kb = after_kb or InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Ещё матч", callback_data="fut_match"),
         InlineKeyboardButton("🏟 Команда",  callback_data="fut_team")],
        [InlineKeyboardButton("◀ FUT меню",  callback_data="fut_menu")],
    ])

    await _show(
        f"{result_hdr}  {emoji_row}\n\n"
        f"🔵 *{my_name}*   *{live_my}* : *{live_opp}*   🔴 *{opp_name}*\n\n"
        f"📊 *Статистика матча*\n"
        f"```\n"
        f"{'':>14}{'🔵':^7}{'🔴':^7}\n"
        f"{'Владение':>14}{str(poss_a)+'%':^7}{str(poss_b)+'%':^7}\n"
        f"{'Удары':>14}{stats['shots_a']:^7}{stats['shots_b']:^7}\n"
        f"{'Передачи':>14}{stats['passes_a']:^7}{stats['passes_b']:^7}\n"
        f"{'Точность':>14}{acc_a_str:^7}{acc_b_str:^7}\n"
        f"{'Угловые':>14}{stats['corners_a']:^7}{stats['corners_b']:^7}\n"
        f"```\n"
        + extra_lines,
        kb=kb,
    )
    return live_my, live_opp, bonus_total


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

    # ELO-данные (нужны до анимации для передачи в неё, корректируются после)
    games_ch = _get_fut_games(challenger_id)
    games_ac = _get_fut_games(accepter_id)

    # Статистика для accepter (A = accepter, B = challenger)
    # Счёт, владение и угловые меняются местами; события общие (neutral commentar)
    stats_ac = {
        "score_a":   match_stats["score_b"],
        "score_b":   match_stats["score_a"],
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
        "h1_events": match_stats["h1_events"],
        "h2_events": match_stats["h2_events"],
        "all_events": match_stats["all_events"],
    }

    # Shared интерактивные моменты (1 на каждый тайм)
    match_key     = f"{challenger_id}_{accepter_id}"
    shared_moments = _make_shared_moments_pvp(challenger_id, accepter_id, sa, sb, match_key)

    # ──────────────────────────────────────────────────────────────────────────
    # Анимации запускаем как фоновые задачи через create_task —
    # это критически важно: если awaiting gather, бот НЕ обрабатывает
    # другие апдейты (нажатия кнопок) пока идёт анимация.
    # create_task возвращает управление боту сразу, анимации идут параллельно.
    async def _animations_and_cleanup():
      try:
        results = await asyncio.gather(
            _run_match_animation(
                bot=ctx.bot,
                chat_id=accepter_id,
                message_id=q.message.message_id,
                my_name=my_name,
                opp_name=ch_name,
                my_uid=accepter_id,
                stats=stats_ac,
                r_delta=0, coins=0,
                shared_moments=shared_moments,
                my_sa=sb,
                opp_sa=sa,
                i_am_team_a=False,    # accepter is team "b" in events
                hide_rewards=True,
            ),
            _run_match_animation(
                bot=ctx.bot,
                chat_id=challenger_id,
                message_id=None,
                my_name=ch_name,
                opp_name=my_name,
                my_uid=challenger_id,
                stats=match_stats,
                r_delta=0, coins=0,
                shared_moments=shared_moments,
                my_sa=sa,
                opp_sa=sb,
                i_am_team_a=True,     # challenger is team "a" in events
                hide_rewards=True,
            ),
            return_exceptions=True,
        )

        # Получаем фактический счёт из анимации challenger (a=challenger)
        if isinstance(results[1], tuple):
            actual_ch, actual_ac, bonus_ch = results[1]
        else:
            actual_ch = match_stats["score_a"]; actual_ac = match_stats["score_b"]; bonus_ch = 0
        if isinstance(results[0], tuple):
            _ac_my, _ac_opp, bonus_ac = results[0]
        else:
            bonus_ac = 0

        # Определяем итог по фактическому счёту
        if actual_ch > actual_ac:
            r_ch, r_ac = 1.0, 0.0
        elif actual_ch == actual_ac:
            r_ch = r_ac = 0.5
        else:
            r_ch, r_ac = 0.0, 1.0

        # ELO и монеты по фактическому результату
        delta_ch = _elo_delta(ra, rb, r_ch, games_ch)
        delta_ac = _elo_delta(rb, ra, r_ac, games_ac)
        coins_ch = _match_coins(actual_ch, actual_ac) + bonus_ch
        coins_ac = _match_coins(actual_ac, actual_ch) + bonus_ac

        # Записываем в БД
        _set_fut_rating(challenger_id, ra + delta_ch)
        _set_fut_rating(accepter_id,   rb + delta_ac)
        _increment_fut_games(challenger_id)
        _increment_fut_games(accepter_id)
        db.add_coins(challenger_id, coins_ch)
        db.add_coins(accepter_id,   coins_ac)
        _save_fut_match(challenger_id, accepter_id, actual_ch, actual_ac,
                        ra, rb, delta_ch, delta_ac)

        # Отправляем итог наград каждому
        def _reward_msg(my_d: int, my_c: int) -> str:
            r_str = f"+{my_d}" if my_d >= 0 else str(my_d)
            return (
                f"📊 *Итог матча записан*\n\n"
                f"🔵 *{ch_name}*  {actual_ch} : {actual_ac}  🔴 *{my_name}*\n\n"
                f"📈 Рейтинг: *{r_str}* ⭐\n"
                f"💰 Монеты: *+{my_c}* 💰"
            )
        try:
            await ctx.bot.send_message(
                chat_id=challenger_id,
                text=_reward_msg(delta_ch, coins_ch),
                parse_mode="Markdown",
            )
        except Exception:
            pass
        try:
            await ctx.bot.send_message(
                chat_id=accepter_id,
                text=(
                    f"📊 *Итог матча записан*\n\n"
                    f"🔵 *{my_name}*  {actual_ac} : {actual_ch}  🔴 *{ch_name}*\n\n"
                    f"📈 Рейтинг: *{'+' + str(delta_ac) if delta_ac >= 0 else str(delta_ac)}* ⭐\n"
                    f"💰 Монеты: *+{coins_ac}* 💰"
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass

      finally:
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

    # ── ЧМ: ввод результата матча (суперадмин) ───────────────────────────────
    if action == "wc_result_input":
        data     = pending.get("data", {})
        wc_id    = data.get("wc_id")
        match_id = data.get("match_id")

        # Парсим "2:1" или "2 1" или "2-1"
        import re
        m_score = re.match(r"^(\d+)\s*[:\-\s]\s*(\d+)$", text.strip())
        if not m_score:
            await update.message.reply_text(
                "❌ Неверный формат. Введи счёт как `2:1` или `0:0`",
                parse_mode="Markdown",
            )
            return True

        h_goals = int(m_score.group(1))
        a_goals = int(m_score.group(2))

        db.clear_pending_action(uid)
        summary = db.wc_set_match_result(wc_id, match_id, h_goals, a_goals)

        if not summary.get("ok"):
            await update.message.reply_text(f"❌ Ошибка: {summary.get('err')}")
            return True

        # Найдём матч для отображения
        wc    = db.get_wc(wc_id)
        match = next((mm for mm in (wc.get("schedule") or []) if mm["id"] == match_id), {}) if wc else {}
        hf    = match.get("home_flag", "")
        af    = match.get("away_flag", "")
        home  = match.get("home", "?")
        away  = match.get("away", "?")

        # Определяем победителя
        if h_goals > a_goals:
            winner_text = f"{hf} {home}"
        elif a_goals > h_goals:
            winner_text = f"{af} {away}"
        else:
            winner_text = "🤝 Ничья"

        await update.message.reply_text(
            f"✅ *Результат записан!*\n\n"
            f"*{hf} {home}* {h_goals}:{a_goals} *{af} {away}*\n"
            f"Победитель: *{winner_text}*\n\n"
            f"📊 Прогнозов обработано: *{summary['total']}*\n"
            f"✅ Угадали исход: *{summary['correct_winner']}*\n"
            f"➕ Бонус за разницу: *{summary.get('correct_diff', 0)}*\n"
            f"🎯 Точный счёт: *{summary['exact_scores']}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 К матчам", callback_data="fut_wc_admin_list_0"),
            ]]),
        )

        # Уведомить всех участников
        if wc:
            parts = db.wc_get_participants(wc_id)
            my_preds_by_uid = {}
            res_p = db.get_client().table("wc_predictions").select("*").eq("wc_id", wc_id).eq("match_id", match_id).execute()
            for pred in (res_p.data or []):
                my_preds_by_uid[pred["user_id"]] = pred
            for p in parts:
                pred = my_preds_by_uid.get(p["user_id"])
                if not pred:
                    continue
                pts       = pred.get("points_earned", 0)
                pred_w    = pred.get("pred_winner", "")
                pw_label  = {"home": f"{hf}{home}", "away": f"{af}{away}", "draw": "🤝"}.get(pred_w, "?")
                ph = pred.get("pred_home")
                pa = pred.get("pred_away")
                sc_str = f" ({ph}:{pa})" if ph is not None else ""
                if pts == 5:
                    result_icon, res_line = "🎯", "Точный счёт! *+5 очков*"
                elif pts == 4:
                    result_icon, res_line = "✅", "Исход и разница! *+4 очка*"
                elif pts == 3:
                    result_icon, res_line = "✅", "Исход угадан! *+3 очка*"
                else:
                    result_icon, res_line = "❌", "Не угадал — *0 очков*"
                try:
                    await ctx.bot.send_message(
                        chat_id=p["user_id"],
                        text=(
                            f"{result_icon} *Матч сыгран!*\n\n"
                            f"*{hf} {home}* {h_goals}:{a_goals} *{af} {away}*\n\n"
                            f"Твой прогноз: *{pw_label}*{sc_str}\n"
                            f"{res_line}"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
        return True

    # ── ЧМ: свой счёт прогноза текстом ────────────────────────────────────────
    if action == "wc_score_input":
        data   = pending.get("data", {})
        wc_id  = data.get("wc_id")
        mid    = data.get("match_id")
        winner = data.get("winner")

        import re
        m_score = re.match(r"^(\d{1,2})\s*[:\-\s]\s*(\d{1,2})$", text)
        if not m_score:
            await update.message.reply_text(
                "❌ Формат: `4:2`", parse_mode="Markdown",
            )
            return True
        h_g, a_g = int(m_score.group(1)), int(m_score.group(2))

        derived = "home" if h_g > a_g else ("away" if a_g > h_g else "draw")
        if winner and derived != winner:
            w_labels = {"home": "победа хозяев", "draw": "ничья", "away": "победа гостей"}
            await update.message.reply_text(
                f"❌ Счёт {h_g}:{a_g} не соответствует выбранному исходу "
                f"(*{w_labels.get(winner, '?')}*). Введи другой счёт.",
                parse_mode="Markdown",
            )
            return True

        ok, err = db.wc_submit_prediction(wc_id, uid, mid, winner or derived, h_g, a_g)
        if not ok:
            await update.message.reply_text(f"❌ {err}\nПопробуй другой счёт.")
            return True

        db.clear_pending_action(uid)
        wc_d  = db.get_wc(wc_id)
        match = next((mm for mm in ((wc_d or {}).get("schedule") or []) if mm["id"] == mid), {})
        hf = match.get("home_flag", "")
        af = match.get("away_flag", "")
        await update.message.reply_text(
            f"✅ *Прогноз сохранён!*\n\n"
            f"*{hf} {match.get('home', '?')}* — *{af} {match.get('away', '?')}*\n"
            f"Твой счёт: *{h_g}:{a_g}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Расписание", callback_data="fut_wc_schedule_0"),
                InlineKeyboardButton("◀ ЧМ",          callback_data="fut_wc"),
            ]]),
        )
        return True

    # ── ЧМ: ввод команд для нового матча (суперадмин) ────────────────────────
    # ── ЧМ: задать команды существующему матчу (плей-офф) ─────────────────────
    if action == "wc_teams_input":
        data     = pending.get("data", {})
        wc_id    = data.get("wc_id")
        match_id = data.get("match_id")

        import re
        m_teams = re.split(r"\s+(?:vs\.?|-|—|–)\s+", text.strip(), maxsplit=1, flags=re.IGNORECASE)
        if len(m_teams) != 2 or not m_teams[0].strip() or not m_teams[1].strip():
            await update.message.reply_text(
                "❌ Формат: `Бразилия - Франция`", parse_mode="Markdown",
            )
            return True

        home_team = m_teams[0].strip()
        away_team = m_teams[1].strip()
        hf = _team_flag(home_team)
        af = _team_flag(away_team)

        db.clear_pending_action(uid)
        ok = db.wc_set_match_teams(wc_id, match_id, home_team, hf, away_team, af)
        if not ok:
            await update.message.reply_text("❌ Не удалось сохранить (матч не найден).")
            return True

        await update.message.reply_text(
            f"✅ *Команды заданы!*\n\n"
            f"`{match_id}`: *{hf} {home_team}* — *{af} {away_team}*\n\n"
            f"Прогнозы откроются автоматически до начала матча.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⚙️ К матчу", callback_data=f"fut_wc_admin_match_{match_id}"),
            ]]),
        )
        return True

    # ── FUT→CUB обменник ──────────────────────────────────────────────────────
    if action == "fut_exchange_amount":
        try:
            amount = int(text.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("❌ Введи целое число (например: 300)")
            return True
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше нуля.")
            return True
        coins = db.get_coins(uid)
        if coins < amount:
            await update.message.reply_text(
                f"❌ Недостаточно монет. Баланс: *{_fmt(coins)} FUT*",
                parse_mode="Markdown",
            )
            return True
        out, comm = db._cross_calc_fut(amount, "fut_to_cube")
        db.clear_pending_action(uid)
        await update.message.reply_text(
            f"💰 *ПОДТВЕРЖДЕНИЕ КОНВЕРТАЦИИ*\n\n"
            f"Потратишь: *{_fmt(amount)} FUT*\n"
            f"Получишь: *{_fmt(out)} CUB* (в Cubeasses-боте)\n"
            f"Комиссия (сжигается): *{_fmt(comm)} CUB*\n\n"
            f"Твой баланс сейчас: *{_fmt(coins)} FUT*\n"
            f"После: *{_fmt(coins - amount)} FUT*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"fut_exchange_confirm_{amount}"),
                InlineKeyboardButton("❌ Отмена",      callback_data="fut_exchange_menu"),
            ]]),
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
        .select("position, pac, sho, pas, dri, def, phy, rating, league, version")
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
            .select("id, name, rating, position, league, version")
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
        "yellows_a": match_stats["yellows_b"],
        "yellows_b": match_stats["yellows_a"],
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
                i_am_team_a=True,
            ),
            _run_match_animation(
                bot=bot, chat_id=guest_uid, message_id=mid_g,
                my_name=guest_name, opp_name=host_name, my_uid=guest_uid,
                stats=stats_guest, r_delta=0, coins=coins_g,
                shared_moments=shared_moments, after_kb=after_kb_g,
                my_sa=sb, opp_sa=sa,
                i_am_team_a=False,
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
            for uid, my_stats, my_name, opp_name, my_sa_t, opp_sa_t, team_a in [
                (uid1, stats,   name1, name2, sa1, sa2, True),
                (uid2, stats_b, name2, name1, sa2, sa1, False),
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
                    i_am_team_a=team_a,
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
                i_am_team_a=False,  # uid2 is team "b" in events (uid1=bot is "a")
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
#  КРОСС-БОТ ОБМЕННИК (FUT-монеты ↔ Кубики)
# ══════════════════════════════════════════════════════════════════════════════


async def cb_fut_exchange_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_exchange_menu — главный экран обменника в FUT-боте."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    coins       = db.get_coins(uid)
    pending_c2f = db.get_cube_to_fut_pending(uid)   # куб→FUT, забрать здесь
    pending_f2c = db.get_fut_to_cube_pending(uid)   # fut→куб, ожидают в Cubeasses

    rate_out = int(300 / db.CROSS_RATE * (1 - db.CROSS_FEE))
    lines = [
        "🔄 *ОБМЕННИК*\n\n",
        f"💰 Твои FUT: *{_fmt(coins)}*\n",
        f"📈 Курс: {db.CROSS_RATE} FUT = 1 CUB (комиссия {int(db.CROSS_FEE * 100)}%)\n",
        f"💱 Пример: 300 FUT → *{rate_out} CUB*\n",
    ]
    if pending_c2f:
        total = sum(t["amount_out"] for t in pending_c2f)
        lines.append(f"\n✅ Готово к получению: *{_fmt(total)} FUT*")
    if pending_f2c:
        total = sum(t["amount_out"] for t in pending_f2c)
        lines.append(f"\n⏳ Ожидает в Cubeasses: *{_fmt(total)} CUB* ({len(pending_f2c)} перев.)")

    rows = [
        [InlineKeyboardButton("💰 FUT → CUB", callback_data="fut_exchange_start_fut")],
    ]
    if pending_c2f:
        total = sum(t["amount_out"] for t in pending_c2f)
        rows.append([InlineKeyboardButton(
            f"📥 Забрать CUB→FUT ({_fmt(total)} FUT)",
            callback_data="fut_exchange_claim_c2f",
        )])
    if pending_f2c:
        rows.append([InlineKeyboardButton(
            "📋 Мои ожидающие переводы",
            callback_data="fut_exchange_pending",
        )])
    rows.append([InlineKeyboardButton("◀ Меню", callback_data="menu_back")])

    await q.edit_message_text(
        "".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_exchange_start_fut(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_exchange_start_fut — начать FUT→CUB конвертацию."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    coins = db.get_coins(uid)
    if coins <= 0:
        await q.answer("Недостаточно монет!", show_alert=True)
        return

    db.set_pending_action(uid, "fut_exchange_amount", {})
    await q.edit_message_text(
        f"💰 *FUT → CUB*\n\n"
        f"💰 Твой баланс: *{_fmt(coins)} FUT*\n"
        f"📈 Курс: {db.CROSS_RATE} FUT = 1 CUB (комиссия {int(db.CROSS_FEE * 100)}%)\n\n"
        f"Введи количество FUT для конвертации:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data="fut_exchange_menu"),
        ]]),
    )


async def cb_fut_exchange_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_exchange_confirm_<amount> — подтвердить FUT→CUB."""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    amount = int(q.data.split("_")[-1])

    ok, tid, err = db.create_fut_to_cube_transfer(uid, amount)
    if not ok:
        await q.edit_message_text(
            f"❌ {err}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ Обменник", callback_data="fut_exchange_menu"),
            ]]),
        )
        return

    out, comm = db._cross_calc_fut(amount, "fut_to_cube")
    await q.edit_message_text(
        f"✅ *ПЕРЕВОД СОЗДАН!*\n\n"
        f"Потрачено: *{_fmt(amount)} FUT*\n"
        f"К получению: *{_fmt(out)} CUB*\n"
        f"Комиссия сожжена: *{_fmt(comm)} CUB*\n\n"
        f"Перейди в Cubeasses-бот и нажми *🔄 Обменник → Забрать*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ Обменник", callback_data="fut_exchange_menu"),
        ]]),
    )


async def cb_fut_exchange_claim_c2f(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_exchange_claim_c2f — забрать CUB→FUT переводы."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    ok, total, err = db.claim_cube_to_fut(uid)
    if not ok:
        await q.answer(err, show_alert=True)
        return

    coins = db.get_coins(uid)
    await q.edit_message_text(
        f"✅ *МОНЕТЫ ПОЛУЧЕНЫ!*\n\n"
        f"Зачислено: *{_fmt(total)} FUT*\n"
        f"Твой баланс: *{_fmt(coins)} FUT*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ Обменник", callback_data="fut_exchange_menu"),
        ]]),
    )


async def cb_fut_exchange_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_exchange_pending — список ожидающих FUT→CUB переводов с отменой."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    transfers = db.get_fut_to_cube_pending(uid)
    if not transfers:
        await q.answer("Нет ожидающих переводов.", show_alert=True)
        return

    lines = ["📋 *ОЖИДАЮЩИЕ ПЕРЕВОДЫ (FUT→CUB)*\n\n"]
    rows  = []
    for t in transfers:
        lines.append(f"• {_fmt(t['amount_in'])} FUT → {_fmt(t['amount_out'])} CUB\n")
        rows.append([InlineKeyboardButton(
            f"🚫 Отменить ({_fmt(t['amount_in'])} FUT)",
            callback_data=f"fut_exchange_cancel_{t['id']}",
        )])
    rows.append([InlineKeyboardButton("◀ Обменник", callback_data="fut_exchange_menu")])

    await q.edit_message_text(
        "".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_fut_exchange_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """fut_exchange_cancel_<id> — отменить FUT→CUB перевод."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    tid = int(q.data.split("_")[-1])

    ok, err = db.cancel_fut_to_cube_transfer(tid, uid)
    if not ok:
        await q.answer(err, show_alert=True)
        return

    await q.answer("✅ Перевод отменён, монеты возвращены!", show_alert=True)
    await cb_fut_exchange_pending(update, ctx)


# ══════════════════════════════════════════════════════════════════════════════
#  ЧЕМПИОНАТ МИРА — ПРОГНОЗЫ
# ══════════════════════════════════════════════════════════════════════════════

WC_ROUND_LABELS: dict[str, str] = {
    "group": "Групповой этап",
    "r32":   "1/16 финала",
    "r16":   "1/8 финала",
    "qf":    "Четвертьфинал",
    "sf":    "Полуфинал",
    "3rd":   "Матч за 3-е место",
    "final": "Финал",
}
WC_ROUND_EMOJI: dict[str, str] = {
    "group": "🏟", "r32": "🔥", "r16": "⚔️", "qf": "⚡",
    "sf": "🌟", "3rd": "🥉", "final": "🏆",
}
WC_STATUS_EMOJI: dict[str, str] = {
    "upcoming": "⏳", "open": "🟢", "closed": "🔴", "done": "✅",
}
WC_PRIZES_DEFAULT: dict[str, int] = {"1": 50_000, "2": 25_000, "3": 10_000}

# Реальные сборные ЧМ-2026: англ. имя → (рус. имя, флаг)
_WC_TEAMS: dict[str, tuple[str, str]] = {
    "Mexico": ("Мексика", "🇲🇽"), "South Africa": ("ЮАР", "🇿🇦"),
    "South Korea": ("Южная Корея", "🇰🇷"), "Czechia": ("Чехия", "🇨🇿"),
    "Canada": ("Канада", "🇨🇦"), "Switzerland": ("Швейцария", "🇨🇭"),
    "Qatar": ("Катар", "🇶🇦"), "Bosnia and Herzegovina": ("Босния", "🇧🇦"),
    "Brazil": ("Бразилия", "🇧🇷"), "Morocco": ("Марокко", "🇲🇦"),
    "Scotland": ("Шотландия", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"), "Haiti": ("Гаити", "🇭🇹"),
    "United States": ("США", "🇺🇸"), "Australia": ("Австралия", "🇦🇺"),
    "Paraguay": ("Парагвай", "🇵🇾"), "Türkiye": ("Турция", "🇹🇷"),
    "Germany": ("Германия", "🇩🇪"), "Ecuador": ("Эквадор", "🇪🇨"),
    "Ivory Coast": ("Кот-д'Ивуар", "🇨🇮"), "Curaçao": ("Кюрасао", "🇨🇼"),
    "Netherlands": ("Нидерланды", "🇳🇱"), "Japan": ("Япония", "🇯🇵"),
    "Tunisia": ("Тунис", "🇹🇳"), "Sweden": ("Швеция", "🇸🇪"),
    "Belgium": ("Бельгия", "🇧🇪"), "Iran": ("Иран", "🇮🇷"),
    "Egypt": ("Египет", "🇪🇬"), "New Zealand": ("Новая Зеландия", "🇳🇿"),
    "Spain": ("Испания", "🇪🇸"), "Uruguay": ("Уругвай", "🇺🇾"),
    "Saudi Arabia": ("Саудовская Аравия", "🇸🇦"), "Cape Verde": ("Кабо-Верде", "🇨🇻"),
    "France": ("Франция", "🇫🇷"), "Senegal": ("Сенегал", "🇸🇳"),
    "Norway": ("Норвегия", "🇳🇴"), "Iraq": ("Ирак", "🇮🇶"),
    "Argentina": ("Аргентина", "🇦🇷"), "Austria": ("Австрия", "🇦🇹"),
    "Algeria": ("Алжир", "🇩🇿"), "Jordan": ("Иордания", "🇯🇴"),
    "Portugal": ("Португалия", "🇵🇹"), "Colombia": ("Колумбия", "🇨🇴"),
    "Uzbekistan": ("Узбекистан", "🇺🇿"), "DR Congo": ("ДР Конго", "🇨🇩"),
    "England": ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"), "Croatia": ("Хорватия", "🇭🇷"),
    "Panama": ("Панама", "🇵🇦"), "Ghana": ("Гана", "🇬🇭"),
}

# Рус. имя → флаг (для ручного ввода команд админом в плей-офф)
_TEAM_FLAGS: dict[str, str] = {ru.lower(): flag for ru, flag in _WC_TEAMS.values()}
_TEAM_FLAGS.update({
    "босния и герцеговина": "🇧🇦", "кот д'ивуар": "🇨🇮", "кот-д’ивуар": "🇨🇮",
    "корея": "🇰🇷", "сша": "🇺🇸",
})

WC_SCHED_PAGE = 6   # матчей на страницу расписания
WC_LB_PAGE    = 10  # участников на страницу таблицы


def _team_flag(name: str) -> str:
    return _TEAM_FLAGS.get(name.lower().strip(), "🏳")


def _wc_et_to_utc_iso(date_str: str, et_time: str) -> str:
    """ET (EDT=UTC-4) → UTC ISO."""
    from datetime import datetime, timedelta, timezone
    dt = datetime.fromisoformat(f"{date_str}T{et_time}:00") + timedelta(hours=4)
    return dt.replace(tzinfo=timezone.utc).isoformat()


# Реальный календарь группового этапа ЧМ-2026 (по данным ESPN; время ET).
# (дата, время ET, группа, хозяева, гости, результат|None)
_WC_GROUP_FIXTURES: list[tuple] = [
    ("2026-06-11","20:00","A","Mexico","South Africa",(2,0)),
    ("2026-06-11","23:00","A","South Korea","Czechia",(2,1)),
    ("2026-06-12","18:00","B","Canada","Bosnia and Herzegovina",(1,1)),
    ("2026-06-12","21:00","D","United States","Paraguay",(4,1)),
    ("2026-06-13","15:00","B","Qatar","Switzerland",(1,1)),
    ("2026-06-13","18:00","C","Brazil","Morocco",(1,1)),
    ("2026-06-13","15:00","C","Haiti","Scotland",(0,1)),
    ("2026-06-14","00:00","D","Australia","Türkiye",(2,0)),
    ("2026-06-14","17:00","E","Germany","Curaçao",(7,1)),
    ("2026-06-14","18:00","F","Netherlands","Japan",(2,2)),
    ("2026-06-14","19:00","E","Ivory Coast","Ecuador",(1,0)),
    ("2026-06-14","22:00","F","Sweden","Tunisia",(5,1)),
    ("2026-06-15","15:00","H","Spain","Cape Verde",(0,0)),
    ("2026-06-15","18:00","G","Belgium","Egypt",(1,1)),
    ("2026-06-15","18:00","H","Saudi Arabia","Uruguay",(1,1)),
    ("2026-06-16","00:00","G","Iran","New Zealand",(2,2)),
    ("2026-06-16","15:00","I","France","Senegal",None),
    ("2026-06-16","18:00","I","Iraq","Norway",None),
    ("2026-06-16","21:00","J","Argentina","Algeria",None),
    ("2026-06-17","00:00","J","Austria","Jordan",None),
    ("2026-06-17","13:00","K","Portugal","DR Congo",None),
    ("2026-06-17","16:00","L","England","Croatia",None),
    ("2026-06-17","19:00","L","Ghana","Panama",None),
    ("2026-06-17","22:00","K","Uzbekistan","Colombia",None),
    ("2026-06-18","12:00","A","Czechia","South Africa",None),
    ("2026-06-18","15:00","B","Switzerland","Bosnia and Herzegovina",None),
    ("2026-06-18","18:00","B","Canada","Qatar",None),
    ("2026-06-18","23:00","A","Mexico","South Korea",None),
    ("2026-06-19","15:00","D","United States","Australia",None),
    ("2026-06-19","18:00","C","Scotland","Morocco",None),
    ("2026-06-19","21:00","C","Brazil","Haiti",None),
    ("2026-06-20","00:00","D","Türkiye","Paraguay",None),
    ("2026-06-20","13:00","F","Netherlands","Sweden",None),
    ("2026-06-20","16:00","E","Germany","Ivory Coast",None),
    ("2026-06-20","20:00","E","Ecuador","Curaçao",None),
    ("2026-06-21","00:00","F","Tunisia","Japan",None),
    ("2026-06-21","12:00","H","Spain","Saudi Arabia",None),
    ("2026-06-21","15:00","G","Belgium","Iran",None),
    ("2026-06-21","18:00","H","Uruguay","Cape Verde",None),
    ("2026-06-21","21:00","G","New Zealand","Egypt",None),
    ("2026-06-22","13:00","J","Argentina","Austria",None),
    ("2026-06-22","17:00","I","France","Iraq",None),
    ("2026-06-22","20:00","I","Norway","Senegal",None),
    ("2026-06-22","23:00","J","Jordan","Algeria",None),
    ("2026-06-23","13:00","K","Portugal","Uzbekistan",None),
    ("2026-06-23","16:00","L","England","Ghana",None),
    ("2026-06-23","19:00","L","Panama","Croatia",None),
    ("2026-06-23","22:00","K","Colombia","DR Congo",None),
    ("2026-06-24","15:00","B","Switzerland","Canada",None),
    ("2026-06-24","15:00","B","Bosnia and Herzegovina","Qatar",None),
    ("2026-06-24","18:00","C","Scotland","Brazil",None),
    ("2026-06-24","18:00","C","Morocco","Haiti",None),
    ("2026-06-24","21:00","A","Czechia","Mexico",None),
    ("2026-06-24","21:00","A","South Africa","South Korea",None),
    ("2026-06-25","16:00","E","Ecuador","Germany",None),
    ("2026-06-25","16:00","E","Curaçao","Ivory Coast",None),
    ("2026-06-25","19:00","F","Japan","Sweden",None),
    ("2026-06-25","19:00","F","Tunisia","Netherlands",None),
    ("2026-06-25","22:00","D","Türkiye","United States",None),
    ("2026-06-25","22:00","D","Paraguay","Australia",None),
    ("2026-06-26","15:00","I","Norway","France",None),
    ("2026-06-26","15:00","I","Senegal","Iraq",None),
    ("2026-06-26","20:00","H","Cape Verde","Saudi Arabia",None),
    ("2026-06-26","20:00","H","Uruguay","Spain",None),
    ("2026-06-26","23:00","G","Egypt","Iran",None),
    ("2026-06-26","23:00","G","New Zealand","Belgium",None),
    ("2026-06-27","17:00","L","Panama","England",None),
    ("2026-06-27","17:00","L","Croatia","Ghana",None),
    ("2026-06-27","19:30","K","Colombia","Portugal",None),
    ("2026-06-27","19:30","K","DR Congo","Uzbekistan",None),
    ("2026-06-27","22:00","J","Algeria","Austria",None),
    ("2026-06-27","22:00","J","Jordan","Argentina",None),
]

# Скелет плей-офф (команды определяются по ходу турнира): (раунд, [даты ET])
_WC_KO_SPEC: list[tuple] = [
    ("r32", ["2026-06-28","2026-06-28","2026-06-28",
             "2026-06-29","2026-06-29","2026-06-29",
             "2026-06-30","2026-06-30","2026-06-30",
             "2026-07-01","2026-07-01","2026-07-01",
             "2026-07-02","2026-07-02",
             "2026-07-03","2026-07-03"]),
    ("r16", ["2026-07-04","2026-07-04","2026-07-05","2026-07-05",
             "2026-07-06","2026-07-06","2026-07-07","2026-07-07"]),
    ("qf",  ["2026-07-09","2026-07-10","2026-07-10","2026-07-11"]),
    ("sf",  ["2026-07-14","2026-07-15"]),
    ("3rd", ["2026-07-18"]),
    ("final", ["2026-07-19"]),
]


def _wc_schedule_2026() -> list[dict]:
    """Полное реальное расписание ЧМ-2026: 72 матча групп + 32 матча плей-офф."""
    schedule: list[dict] = []
    seq = 0

    for date_s, et, grp, home_en, away_en, result in _WC_GROUP_FIXTURES:
        seq += 1
        h_ru, h_fl = _WC_TEAMS.get(home_en, (home_en, "🏳"))
        a_ru, a_fl = _WC_TEAMS.get(away_en, (away_en, "🏳"))
        hg, ag = (result if result else (None, None))
        schedule.append({
            "id": f"M{seq:03d}", "round": "group", "group": grp,
            "home": h_ru, "home_flag": h_fl,
            "away": a_ru, "away_flag": a_fl,
            "kickoff": _wc_et_to_utc_iso(date_s, et),
            "home_goals": hg, "away_goals": ag,
        })

    for rnd, dates in _WC_KO_SPEC:
        for date_s in dates:
            seq += 1
            schedule.append({
                "id": f"M{seq:03d}", "round": rnd, "group": "",
                "home": "TBD", "home_flag": "🏆",
                "away": "TBD", "away_flag": "🏆",
                "kickoff": _wc_et_to_utc_iso(date_s, "19:00"),
                "home_goals": None, "away_goals": None,
            })

    return schedule


def _wc_fmt_dt(iso: str | None) -> str:
    """UTC ISO → 'DD.MM HH:MM' по местному времени матча (ET, вост. США, UTC-4)."""
    if not iso:
        return ""
    from datetime import datetime, timezone, timedelta
    try:
        kt = datetime.fromisoformat(iso)
        if kt.tzinfo is None:
            kt = kt.replace(tzinfo=timezone.utc)
        loc = kt.astimezone(timezone(timedelta(hours=-4)))
        return loc.strftime("%d.%m %H:%M")
    except Exception:
        return ""


def _wc_rank_emoji(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")


def _wc_live_offset(schedule: list) -> int:
    """Смещение страницы расписания на первый ещё не сыгранный матч."""
    for i, m in enumerate(schedule):
        if m.get("status") != "done":
            return (i // WC_SCHED_PAGE) * WC_SCHED_PAGE
    return 0


def _wc_match_line(m: dict, pred: dict | None = None, show_date: bool = True) -> str:
    st   = WC_STATUS_EMOJI.get(m.get("status", "upcoming"), "⏳")
    hf   = m.get("home_flag", "")
    af   = m.get("away_flag", "")
    home = m.get("home", "?")
    away = m.get("away", "?")
    rnd_e = WC_ROUND_EMOJI.get(m.get("round", "group"), "")
    grp  = f"Гр.{m['group']} " if m.get("group") else ""

    dt_str = ""
    if show_date:
        d = _wc_fmt_dt(m.get("kickoff"))
        if d:
            dt_str = f"_{d}_ "

    score_str = ""
    if m.get("status") == "done" and m.get("home_goals") is not None:
        score_str = f" *{m['home_goals']}:{m['away_goals']}*"

    pred_str = ""
    if pred:
        w = pred.get("pred_winner", "")
        ph = pred.get("pred_home")
        pa = pred.get("pred_away")
        pts = pred.get("points_earned", 0)
        resolved = pred.get("resolved", False)
        pred_icon = {"home": hf or "🏠", "away": af or "✈️", "draw": "🤝"}.get(w, "❓")
        exact = f" {ph}:{pa}" if ph is not None and pa is not None else ""
        if resolved:
            pts_str = f"+{pts}🏅" if pts > 0 else "✗"
            pred_str = f" _[{pred_icon}{exact} {pts_str}]_"
        else:
            pred_str = f" _[{pred_icon}{exact}]_"

    return f"{st}{rnd_e} {dt_str}{grp}{hf}{home} — {af}{away}{score_str}{pred_str}"


# ── Справочные данные (стадионы / история) ────────────────────────────────────

# Города-организаторы ЧМ-2026 (16 арен в США, Канаде и Мексике)
_WC_STADIUMS: list[tuple] = [
    ("🇲🇽", "Мехико",            "Эстадио Ацтека",        "Матч открытия"),
    ("🇲🇽", "Гвадалахара",       "Эстадио Акрон",         ""),
    ("🇲🇽", "Монтеррей",         "Эстадио BBVA",          ""),
    ("🇨🇦", "Торонто",           "BMO Field",             ""),
    ("🇨🇦", "Ванкувер",          "BC Place",              ""),
    ("🇺🇸", "Нью-Йорк / Н.-Дж.", "MetLife Stadium",       "ФИНАЛ"),
    ("🇺🇸", "Лос-Анджелес",      "SoFi Stadium",          ""),
    ("🇺🇸", "Даллас",            "AT&T Stadium",          ""),
    ("🇺🇸", "Сан-Франциско",     "Levi's Stadium",        ""),
    ("🇺🇸", "Майами",            "Hard Rock Stadium",     ""),
    ("🇺🇸", "Атланта",           "Mercedes-Benz Stadium", ""),
    ("🇺🇸", "Сиэтл",             "Lumen Field",           ""),
    ("🇺🇸", "Хьюстон",           "NRG Stadium",           ""),
    ("🇺🇸", "Филадельфия",       "Lincoln Financial",     ""),
    ("🇺🇸", "Канзас-Сити",       "Arrowhead Stadium",     ""),
    ("🇺🇸", "Бостон",            "Gillette Stadium",      ""),
]

# Чемпионы прошлых ЧМ (последние турниры + рекордсмены)
_WC_HISTORY: list[tuple] = [
    ("2022", "🇶🇦 Катар",        "🇦🇷 Аргентина", "🇫🇷 Франция"),
    ("2018", "🇷🇺 Россия",       "🇫🇷 Франция",   "🇭🇷 Хорватия"),
    ("2014", "🇧🇷 Бразилия",     "🇩🇪 Германия",  "🇦🇷 Аргентина"),
    ("2010", "🇿🇦 ЮАР",          "🇪🇸 Испания",   "🇳🇱 Нидерланды"),
    ("2006", "🇮🇹 Италия",       "🇮🇹 Италия",    "🇫🇷 Франция"),
    ("2002", "🇰🇷🇯🇵 Корея/Яп.",  "🇧🇷 Бразилия",  "🇩🇪 Германия"),
]
_WC_TITLES: list[str] = [
    "🇧🇷 Бразилия — 5",
    "🇩🇪 Германия — 4",
    "🇮🇹 Италия — 4",
    "🇦🇷 Аргентина — 3",
    "🇫🇷 Франция · 🇺🇾 Уругвай — 2",
]


def _wc_group_badge(g: str) -> str:
    """Буква группы как «плитка» (одиночный regional-indicator: A→🇦 … L→🇱)."""
    g = (g or "").strip().upper()
    if len(g) == 1 and "A" <= g <= "Z":
        return chr(0x1F1E6 + ord(g) - ord("A"))
    return f"Гр.{g}"


def _wc_teams_by_group(schedule: list) -> dict[str, list[tuple]]:
    """Сборные по группам: {буква: [(имя, флаг), ...]} (уникальные, в порядке появления)."""
    groups: dict[str, list[tuple]] = {}
    for m in schedule:
        g = m.get("group")
        if not g or m.get("round") != "group":
            continue
        bucket = groups.setdefault(g, [])
        for name, flag in ((m.get("home"), m.get("home_flag", "")),
                           (m.get("away"), m.get("away_flag", ""))):
            if name and name not in ("TBD", "?") and (name, flag) not in bucket:
                bucket.append((name, flag))
    return dict(sorted(groups.items()))


def _wc_group_standings(schedule: list) -> dict[str, list[dict]]:
    """Турнирная таблица групп из сыгранных матчей. Сортировка: очки → разница → забито."""
    table: dict[str, dict[str, dict]] = {}

    # Заводим все команды (даже без игр), чтобы группа всегда была полной
    for g, teams in _wc_teams_by_group(schedule).items():
        table[g] = {
            name: {"team": name, "flag": flag, "P": 0, "W": 0, "D": 0,
                   "L": 0, "GF": 0, "GA": 0, "Pts": 0}
            for name, flag in teams
        }

    for m in schedule:
        g = m.get("group")
        if (not g or m.get("round") != "group"
                or m.get("home_goals") is None or m.get("away_goals") is None):
            continue
        hg, ag = m["home_goals"], m["away_goals"]
        h, a   = m.get("home"), m.get("away")
        if h not in table.get(g, {}) or a not in table.get(g, {}):
            continue
        rh, ra = table[g][h], table[g][a]
        rh["P"] += 1; ra["P"] += 1
        rh["GF"] += hg; rh["GA"] += ag
        ra["GF"] += ag; ra["GA"] += hg
        if hg > ag:
            rh["W"] += 1; rh["Pts"] += 3; ra["L"] += 1
        elif hg < ag:
            ra["W"] += 1; ra["Pts"] += 3; rh["L"] += 1
        else:
            rh["D"] += 1; ra["D"] += 1; rh["Pts"] += 1; ra["Pts"] += 1

    out: dict[str, list[dict]] = {}
    for g, rows in table.items():
        ranked = sorted(
            rows.values(),
            key=lambda r: (r["Pts"], r["GF"] - r["GA"], r["GF"]),
            reverse=True,
        )
        out[g] = ranked
    return out


# ── Пользовательские хендлеры ─────────────────────────────────────────────────

async def cb_fut_wc(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc$ — главный экран ЧМ."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    # Режим существует всегда — ЧМ-2026 создаётся лениво при первом открытии.
    wc = db.get_active_wc()
    if not wc:
        wc = db.ensure_wc(
            uid, _wc_schedule_2026(),
            {"entry_fee": 0, "prizes": WC_PRIZES_DEFAULT, "preset": "wc2026"},
        )
    if not wc:
        await q.edit_message_text(
            "🌍 *ЧЕМПИОНАТ МИРА 2026*\n\n"
            "Режим временно недоступен. Попробуй позже.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")],
            ]),
        )
        return

    wc_id    = wc["id"]
    schedule = wc.get("schedule") or []
    settings = wc.get("settings") or {}

    parts        = db.wc_get_participants(wc_id)
    open_matches = [m for m in schedule if m.get("status") == "open"]
    done_matches = [m for m in schedule if m.get("status") == "done"]

    my_part = db.wc_get_participant(wc_id, uid)
    my_rank = None
    if my_part:
        my_rank = next((i + 1 for i, p in enumerate(parts) if p["user_id"] == uid), None)

    top3 = "\n".join(
        f"{_wc_rank_emoji(i+1)} *{p['name']}* — {p['total_points']} очк."
        for i, p in enumerate(parts[:3])
    ) or "_Пока нет участников_"

    my_line = ""
    if my_part:
        my_line = f"\n\n👤 Ты: *{my_part['total_points']}* очк. (#{my_rank})"
    else:
        my_line = "\n\n_Ты ещё не записан — нажми «Участвовать»!_"

    # «Следующий матч» — ближайший открытый по времени
    next_line = ""
    if open_matches:
        nm = open_matches[0]
        next_line = (
            f"\n⏭ _Ближайший:_ {nm.get('home_flag','')}{nm.get('home','?')} — "
            f"{nm.get('away_flag','')}{nm.get('away','?')}  ·  {_wc_fmt_dt(nm.get('kickoff'))}"
        )

    text = (
        "🏆 *FIFA WORLD CUP 2026* 🌍\n"
        "🇺🇸 🇨🇦 🇲🇽  _США · Канада · Мексика_\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Сыграно: *{len(done_matches)}/{len(schedule)}*   "
        f"🟢 Открыто: *{len(open_matches)}*\n"
        f"👥 Прогнозистов: *{len(parts)}*"
        f"{next_line}\n\n"
        f"🏆 *Лидеры прогнозов:*\n{top3}"
        f"{my_line}\n\n"
        "📜 _Очки: точный счёт 5 · исход 3 · разница +1_\n"
        "🚫 _Счёт не должен повторяться у разных игроков_"
    )

    live_off = _wc_live_offset(schedule)
    kb = []
    # Действие-прогноз (или вступление)
    if not my_part:
        fee     = settings.get("entry_fee", 0)
        fee_str = f" ({_fmt(fee)} 💰)" if fee else " (free)"
        kb.append([InlineKeyboardButton(f"✅ Участвовать в прогнозах{fee_str}",
                                        callback_data="fut_wc_join")])
    elif open_matches:
        kb.append([InlineKeyboardButton(
            f"🎯 Сделать прогноз ({len(open_matches)})",
            callback_data=f"fut_wc_schedule_{live_off}",
        )])
    # Вкладки в стиле soccer365
    kb.append([
        InlineKeyboardButton("📊 Таблица",    callback_data="fut_wc_tbl"),
        InlineKeyboardButton("📅 Расписание", callback_data=f"fut_wc_schedule_{live_off}"),
    ])
    kb.append([
        InlineKeyboardButton("✅ Результаты", callback_data="fut_wc_res_0"),
        InlineKeyboardButton("🏳 Команды",    callback_data="fut_wc_teams"),
    ])
    kb.append([
        InlineKeyboardButton("🎯 Прогнозы",  callback_data=f"fut_wc_schedule_{live_off}"),
        InlineKeyboardButton("👑 Рейтинг",   callback_data="fut_wc_lb_0"),
    ])
    kb.append([
        InlineKeyboardButton("🏟 Стадионы",  callback_data="fut_wc_stad"),
        InlineKeyboardButton("📜 История",   callback_data="fut_wc_hist"),
    ])
    if my_part:
        kb.append([InlineKeyboardButton("📝 Мои прогнозы", callback_data="fut_wc_mypreds_0")])
    from config import SUPERADMIN_IDS
    if uid in SUPERADMIN_IDS:
        kb.append([InlineKeyboardButton("🛠 Управление", callback_data="fut_wc_admin")])
    kb.append([InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")])

    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_wc_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_join$ — записаться в ЧМ."""
    q   = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    user = db.get_user(uid)
    if not user:
        await q.answer("Сначала зарегистрируйся в боте.", show_alert=True)
        return

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id    = wc["id"]
    settings = wc.get("settings") or {}
    fee      = settings.get("entry_fee", 0)

    if db.wc_get_participant(wc_id, uid):
        await q.answer("Ты уже участвуешь!", show_alert=True)
        return

    if fee > 0:
        ok, bal = db.spend_coins(uid, fee)
        if not ok:
            await q.answer(f"Недостаточно монет! Нужно {_fmt(fee)} 💰", show_alert=True)
            return

    name    = user.get("display_name") or user.get("username") or f"User{uid}"
    ok, err = db.wc_join(wc_id, uid, name)
    if not ok:
        if fee > 0:
            db.add_coins(uid, fee)  # вернуть взнос при неудаче
        if err == "already_joined":
            await q.answer("Ты уже участвуешь!", show_alert=True)
        else:
            await q.answer(f"Ошибка: {err}", show_alert=True)
        return

    await q.answer("✅ Ты теперь участник ЧМ!")
    await cb_fut_wc(update, ctx)


async def cb_fut_wc_table(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_tbl$ — турнирная таблица групп (вкладка «Таблица»)."""
    q  = update.callback_query
    await q.answer()

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return
    schedule  = wc.get("schedule") or []
    standings = _wc_group_standings(schedule)

    blocks = ["📊 *ТАБЛИЦА ГРУПП — ЧМ-2026*\n_И · О · мячи · ±_\n"]
    for g, rows in standings.items():
        lines = [f"{_wc_group_badge(g)} *Группа {g}*"]
        for i, r in enumerate(rows, 1):
            gd  = r["GF"] - r["GA"]
            gds = f"+{gd}" if gd > 0 else str(gd)
            mark = "🟢" if i <= 2 else ("🟡" if i == 3 else "⚪")
            nm  = (r["team"][:11])
            lines.append(
                f"{mark}{i} {r['flag']}{nm}  "
                f"`{r['P']:>1} {r['Pts']:>2}о {r['GF']}:{r['GA']} {gds}`"
            )
        blocks.append("\n".join(lines))

    text = "\n\n".join(blocks) + "\n\n🟢 плей-офф · 🟡 стыки/лучшие 3-и · ⚪ вылет"
    await q.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ ЧМ", callback_data="fut_wc"),
        ]]),
    )


async def cb_fut_wc_results(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_res_ — сыгранные матчи с результатами (вкладка «Результаты»)."""
    q      = update.callback_query
    await q.answer()
    offset = int(q.data.split("_")[-1])

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return
    schedule = wc.get("schedule") or []
    done = [m for m in schedule if m.get("status") == "done"]
    done.sort(key=lambda m: m.get("kickoff") or "")

    if not done:
        await q.edit_message_text(
            "✅ *РЕЗУЛЬТАТЫ — ЧМ-2026*\n\n_Сыгранных матчей пока нет._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ ЧМ", callback_data="fut_wc"),
            ]]),
        )
        return

    page  = done[offset: offset + WC_SCHED_PAGE]
    lines = [_wc_match_line(m, show_date=True) for m in page]
    text  = (
        f"✅ *РЕЗУЛЬТАТЫ — ЧМ-2026* ({offset + 1}–{min(offset + WC_SCHED_PAGE, len(done))} из {len(done)})\n"
        "_местное время матча (ET)_\n\n"
        + "\n".join(lines)
    )

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_wc_res_{offset - WC_SCHED_PAGE}"))
    if offset + WC_SCHED_PAGE < len(done):
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_wc_res_{offset + WC_SCHED_PAGE}"))
    kb = [nav] if nav else []
    kb.append([InlineKeyboardButton("◀ ЧМ", callback_data="fut_wc")])

    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_wc_teams(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_teams$ — сборные по группам (вкладка «Команды»)."""
    q  = update.callback_query
    await q.answer()

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return
    schedule = wc.get("schedule") or []
    groups   = _wc_teams_by_group(schedule)

    total = sum(len(v) for v in groups.values())
    blocks = [f"🏳 *СБОРНЫЕ — ЧМ-2026*\n_{total} команд · {len(groups)} групп_\n"]
    for g, teams in groups.items():
        names = "  ".join(f"{fl}{nm}" for nm, fl in teams)
        blocks.append(f"{_wc_group_badge(g)} *Группа {g}*\n{names}")

    await q.edit_message_text(
        "\n\n".join(blocks),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ ЧМ", callback_data="fut_wc"),
        ]]),
    )


async def cb_fut_wc_stadiums(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_stad$ — города и арены (вкладка «Стадионы»)."""
    q = update.callback_query
    await q.answer()

    lines = ["🏟 *СТАДИОНЫ ЧМ-2026*\n_16 арен · 3 страны_\n"]
    for flag, city, arena, note in _WC_STADIUMS:
        tag = f"  ⭐ _{note}_" if note else ""
        lines.append(f"{flag} *{city}* — {arena}{tag}")

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ ЧМ", callback_data="fut_wc"),
        ]]),
    )


async def cb_fut_wc_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_hist$ — чемпионы прошлых турниров (вкладка «История»)."""
    q = update.callback_query
    await q.answer()

    champ = "\n".join(
        f"*{yr}* {host} → 🥇 {win}  _(финал vs {ru})_"
        for yr, host, win, ru in _WC_HISTORY
    )
    titles = "\n".join(f"• {t}" for t in _WC_TITLES)
    text = (
        "📜 *ИСТОРИЯ ЧЕМПИОНАТА МИРА*\n\n"
        "🏆 *Последние чемпионы:*\n"
        f"{champ}\n\n"
        "👑 *Больше всего титулов:*\n"
        f"{titles}"
    )
    await q.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ ЧМ", callback_data="fut_wc"),
        ]]),
    )


async def cb_fut_wc_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_schedule_ — расписание с пагинацией."""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    offset = int(q.data.split("_")[-1])

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id    = wc["id"]
    schedule = wc.get("schedule") or []
    my_preds = db.wc_get_user_predictions(wc_id, uid)
    my_part  = db.wc_get_participant(wc_id, uid)

    page_matches = schedule[offset: offset + WC_SCHED_PAGE]
    lines = []
    for m in page_matches:
        pred = my_preds.get(m["id"]) if my_part else None
        lines.append(_wc_match_line(m, pred))

    text = (
        f"📋 *РАСПИСАНИЕ ЧМ-2026* ({offset + 1}–{min(offset + WC_SCHED_PAGE, len(schedule))} из {len(schedule)})\n"
        f"_местное время матча (ET)_\n\n"
        + "\n".join(lines)
        + "\n\n🟢 открыт · 🔴 закрыт · ⏳ предстоит · ✅ сыгран"
    )

    # Кнопки: прогноз для открытых, просмотр прогнозов для закрытых/сыгранных
    kb = []
    for m in page_matches:
        hf = m.get("home_flag", "")
        af = m.get("away_flag", "")
        if m.get("status") == "open":
            pred = my_preds.get(m["id"])
            mark = " ✔" if pred and not pred.get("resolved") else ""
            kb.append([InlineKeyboardButton(
                f"🎯 {hf}{m['home']} — {af}{m['away']}{mark}",
                callback_data=f"fut_wc_predict_{m['id']}",
            )])
        elif m.get("status") in ("closed", "done"):
            kb.append([InlineKeyboardButton(
                f"👁 {hf}{m['home']} — {af}{m['away']}",
                callback_data=f"fut_wc_preds_{m['id']}",
            )])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_wc_schedule_{offset - WC_SCHED_PAGE}"))
    if offset + WC_SCHED_PAGE < len(schedule):
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_wc_schedule_{offset + WC_SCHED_PAGE}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Назад", callback_data="fut_wc")])

    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_wc_predict(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_predict_ — экран прогноза для одного матча."""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    mid    = q.data[len("fut_wc_predict_"):]

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id = wc["id"]
    match = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), None)
    if not match or match.get("status") != "open":
        await q.answer("Прогнозы на этот матч недоступны.", show_alert=True)
        return

    my_part = db.wc_get_participant(wc_id, uid)
    if not my_part:
        await q.answer("Сначала вступи в ЧМ!", show_alert=True)
        return

    hf   = match.get("home_flag", "")
    af   = match.get("away_flag", "")
    home = match["home"]
    away = match["away"]
    rnd  = WC_ROUND_LABELS.get(match.get("round", "group"), "")
    grp  = f" • Группа {match['group']}" if match.get("group") else ""

    my_preds = db.wc_get_user_predictions(wc_id, uid)
    existing = my_preds.get(mid)
    existing_str = ""
    if existing:
        w  = existing.get("pred_winner", "")
        ph = existing.get("pred_home")
        pa = existing.get("pred_away")
        wi = {"home": f"{hf}{home}", "away": f"{af}{away}", "draw": "🤝 Ничья"}.get(w, "?")
        sc = f" ({ph}:{pa})" if ph is not None and pa is not None else ""
        existing_str = f"\n\n_Твой текущий прогноз: *{wi}*{sc}_"

    text = (
        f"🎯 *ПРОГНОЗ НА МАТЧ*\n\n"
        f"*{hf} {home}*  vs  *{af} {away}*\n"
        f"_{rnd}{grp}_"
        f"{existing_str}\n\n"
        "_📜 точный счёт — 5 очков • исход — 3 • +1 за разницу_\n\n"
        "Выбери исход:"
    )

    kb = [
        [InlineKeyboardButton(f"🏠 {hf} {home}", callback_data=f"fut_wc_pw_{mid}_home")],
        [InlineKeyboardButton("🤝 Ничья",          callback_data=f"fut_wc_pw_{mid}_draw")],
        [InlineKeyboardButton(f"✈️ {af} {away}",   callback_data=f"fut_wc_pw_{mid}_away")],
        [InlineKeyboardButton("◀ Расписание",       callback_data="fut_wc_schedule_0")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_wc_pred_winner(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_pw_ — выбран победитель, теперь выбор точного счёта."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    # fut_wc_pw_{mid}_{winner}
    tail   = q.data[len("fut_wc_pw_"):]
    ridx   = tail.rfind("_")
    mid    = tail[:ridx]
    winner = tail[ridx + 1:]  # home / draw / away

    wc = db.get_active_wc()
    if not wc:
        await q.answer("ЧМ не найден.", show_alert=True)
        return
    wc_id = wc["id"]
    match = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), None)
    if not match:
        await q.answer("Матч не найден.", show_alert=True)
        return

    hf   = match.get("home_flag", "")
    af   = match.get("away_flag", "")
    home = match["home"]
    away = match["away"]
    w_label = {"home": f"{hf} {home}", "draw": "🤝 Ничья", "away": f"{af} {away}"}.get(winner, "?")

    # Регламент: счета не повторяются — помечаем занятые другими участниками
    all_preds = db.wc_get_match_predictions(wc_id, mid)
    taken = {(p["pred_home"], p["pred_away"]) for p in all_preds
             if p["user_id"] != uid and p.get("pred_home") is not None}

    text = (
        f"🎯 *{hf} {home} — {af} {away}*\n\n"
        f"Выбрано: *{w_label}*\n\n"
        "Теперь выбери точный счёт:\n"
        "_📜 точный счёт — 5 • исход — 3 • +1 за разницу_\n"
        "_🚫 — счёт занят другим участником_"
    )

    def _score_btn(h_g: int, a_g: int) -> InlineKeyboardButton:
        if (h_g, a_g) in taken:
            return InlineKeyboardButton(f"🚫 {h_g}:{a_g}", callback_data="fut_wc_taken")
        return InlineKeyboardButton(
            f"{h_g}:{a_g}",
            callback_data=f"fut_wc_psave_{mid}_{winner}_{h_g}_{a_g}",
        )

    kb = []
    if winner == "draw":
        kb.append([_score_btn(g, g) for g in range(4)])
    else:
        win_goals_opts = [1, 2, 3, 4]
        rows_scores = []
        for wg in win_goals_opts:
            for lg in range(min(wg, 3)):
                h_g = wg if winner == "home" else lg
                a_g = wg if winner == "away" else lg
                rows_scores.append(_score_btn(h_g, a_g))
        for i in range(0, len(rows_scores), 3):
            kb.append(rows_scores[i:i + 3])

    kb.append([InlineKeyboardButton("✏️ Свой счёт", callback_data=f"fut_wc_custom_{mid}_{winner}")])
    kb.append([InlineKeyboardButton("◀ Назад",      callback_data=f"fut_wc_predict_{mid}")])

    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_wc_pred_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_psave_ — сохранить прогноз."""
    q   = update.callback_query
    uid = q.from_user.id

    # fut_wc_psave_{mid}_{winner}_{h}_{a}
    parts  = q.data[len("fut_wc_psave_"):].rsplit("_", 3)
    mid, winner, h_str, a_str = parts[0], parts[1], parts[2], parts[3]
    pred_h = int(h_str) if h_str != "-1" else None
    pred_a = int(a_str) if a_str != "-1" else None

    if pred_h is None or pred_a is None:
        await q.answer("По регламенту нужно выбрать точный счёт!", show_alert=True)
        return

    wc = db.get_active_wc()
    if not wc:
        await q.answer("ЧМ не найден.", show_alert=True)
        return

    ok, err = db.wc_submit_prediction(wc["id"], uid, mid, winner, pred_h, pred_a)
    if not ok:
        await q.answer(err, show_alert=True)
        return

    match   = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), {})
    hf      = match.get("home_flag", "")
    af      = match.get("away_flag", "")
    home    = match.get("home", "?")
    away    = match.get("away", "?")
    w_label = {"home": f"{hf} {home}", "draw": "🤝 Ничья", "away": f"{af} {away}"}.get(winner, "?")
    sc_str  = f" · *{pred_h}:{pred_a}*" if pred_h is not None else ""

    await q.answer(f"✅ Прогноз сохранён: {w_label}{sc_str}", show_alert=True)

    # Показываем подтверждение с кнопками навигации
    schedule = wc.get("schedule") or []
    open_remaining = [m for m in schedule if m.get("status") == "open" and m["id"] != mid]
    kb = []
    if open_remaining:
        m2 = open_remaining[0]
        kb.append([InlineKeyboardButton(
            f"🎯 Следующий: {m2.get('home_flag','')}{m2['home']} — {m2.get('away_flag','')}{m2['away']}",
            callback_data=f"fut_wc_predict_{m2['id']}",
        )])
    kb.append([
        InlineKeyboardButton("📋 Расписание", callback_data="fut_wc_schedule_0"),
        InlineKeyboardButton("◀ ЧМ",          callback_data="fut_wc"),
    ])
    await q.edit_message_text(
        f"✅ *Прогноз сохранён!*\n\n"
        f"*{hf} {home}* — *{af} {away}*\n"
        f"Твой выбор: *{w_label}*{sc_str}\n\n"
        + (f"Осталось открытых матчей: *{len(open_remaining)}*" if open_remaining else "_Больше открытых матчей нет_"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_wc_taken(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_taken$ — нажатие на занятый счёт."""
    await update.callback_query.answer(
        "🚫 Этот счёт уже занят другим участником!\n"
        "По регламенту счета не повторяются.",
        show_alert=True,
    )


async def cb_fut_wc_custom(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_custom_ — ввести свой счёт текстом."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    # fut_wc_custom_{mid}_{winner}
    tail   = q.data[len("fut_wc_custom_"):]
    ridx   = tail.rfind("_")
    mid    = tail[:ridx]
    winner = tail[ridx + 1:]

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return
    match = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), None)
    if not match or match.get("status") != "open":
        await q.answer("Прогнозы на этот матч недоступны.", show_alert=True)
        return

    all_preds = db.wc_get_match_predictions(wc["id"], mid)
    taken = sorted(
        {(p["pred_home"], p["pred_away"]) for p in all_preds
         if p["user_id"] != uid and p.get("pred_home") is not None}
    )
    taken_str = ", ".join(f"{h}:{a}" for h, a in taken) if taken else "пока нет"

    w_labels = {"home": "победа хозяев", "draw": "ничья", "away": "победа гостей"}
    db.set_pending_action(uid, "wc_score_input", {
        "wc_id": wc["id"], "match_id": mid, "winner": winner,
    })

    hf = match.get("home_flag", "")
    af = match.get("away_flag", "")
    await q.edit_message_text(
        f"✏️ *СВОЙ СЧЁТ*\n\n"
        f"*{hf} {match['home']}* — *{af} {match['away']}*\n"
        f"Исход: *{w_labels.get(winner, '?')}*\n\n"
        f"🚫 Заняты: {taken_str}\n\n"
        f"Отправь счёт текстом, например `4:2`\n"
        f"_(счёт должен соответствовать выбранному исходу)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data=f"fut_wc_inpcancel_{mid}"),
        ]]),
    )


async def cb_fut_wc_inpcancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_inpcancel_ — отмена текстового ввода счёта."""
    q   = update.callback_query
    await q.answer("Отменено")
    uid = q.from_user.id
    mid = q.data[len("fut_wc_inpcancel_"):]

    pending = db.get_pending_action(uid)
    if pending and pending.get("action") == "wc_score_input":
        db.clear_pending_action(uid)

    await q.edit_message_text(
        "Ввод счёта отменён.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 К прогнозу",  callback_data=f"fut_wc_predict_{mid}")],
            [InlineKeyboardButton("📋 Расписание",  callback_data="fut_wc_schedule_0")],
        ]),
    )


async def cb_fut_wc_preds(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_preds_ — прогнозы всех участников (для закрытых/сыгранных матчей)."""
    q   = update.callback_query
    await q.answer()
    mid = q.data[len("fut_wc_preds_"):]

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return
    wc_id = wc["id"]
    match = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), None)
    if not match:
        await q.answer("Матч не найден.", show_alert=True)
        return
    if match.get("status") == "open":
        await q.answer("Прогнозы участников скрыты, пока матч открыт!", show_alert=True)
        return

    preds = db.wc_get_match_predictions(wc_id, mid)
    parts = db.wc_get_participants(wc_id)
    names = {p["user_id"]: p["name"] for p in parts}

    hf, af  = match.get("home_flag", ""), match.get("away_flag", "")
    is_done = match.get("status") == "done"
    score_str = (
        f" — *{match['home_goals']}:{match['away_goals']}*"
        if is_done and match.get("home_goals") is not None else ""
    )

    if is_done:
        preds.sort(key=lambda p: -p.get("points_earned", 0))
    else:
        preds.sort(key=lambda p: names.get(p["user_id"], ""))

    lines = []
    for p in preds:
        name   = names.get(p["user_id"], f"User{p['user_id']}")
        ph, pa = p.get("pred_home"), p.get("pred_away")
        sc = f"{ph}:{pa}" if ph is not None else \
             {"home": "П1", "away": "П2", "draw": "Х"}.get(p.get("pred_winner"), "?")
        if is_done:
            pts  = p.get("points_earned", 0)
            icon = "🎯" if pts == 5 else ("✅" if pts > 0 else "❌")
            lines.append(f"{icon} {name}: {sc} → *+{pts}*")
        else:
            lines.append(f"• {name}: {sc}")

    await q.edit_message_text(
        f"👁 *ПРОГНОЗЫ — {mid}*\n\n"
        f"{hf}{match['home']} — {af}{match['away']}{score_str}\n\n"
        + ("\n".join(lines) or "_Никто не сделал прогноз_"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ Расписание", callback_data="fut_wc_schedule_0"),
        ]]),
    )


async def cb_fut_wc_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_lb_ — таблица лидеров."""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    offset = int(q.data.split("_")[-1])

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id = wc["id"]
    parts = db.wc_get_participants(wc_id)
    total = len(parts)
    page  = parts[offset: offset + WC_LB_PAGE]

    lines = []
    for i, p in enumerate(page):
        rank  = offset + i + 1
        mark  = " ←" if p["user_id"] == uid else ""
        exact = f" ({p['exact_scores']}🎯)" if p.get("exact_scores") else ""
        lines.append(
            f"{_wc_rank_emoji(rank)} *{p['name']}*{mark} — "
            f"*{p['total_points']}* очк.{exact}"
        )

    text = (
        f"🏆 *ТАБЛИЦА — {wc_id}*\n\n"
        + ("\n".join(lines) or "_Нет участников_")
        + f"\n\n_Всего участников: {total}_"
        + "\n_Цифра 🎯 = угаданных точных счётов_"
    )

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_wc_lb_{offset - WC_LB_PAGE}"))
    if offset + WC_LB_PAGE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_wc_lb_{offset + WC_LB_PAGE}"))
    kb = [nav] if nav else []
    kb.append([InlineKeyboardButton("◀ Назад", callback_data="fut_wc")])

    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_wc_mypreds(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_mypreds_ — мои прогнозы с пагинацией."""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    offset = int(q.data.split("_")[-1])

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id    = wc["id"]
    schedule = wc.get("schedule") or []
    my_preds = db.wc_get_user_predictions(wc_id, uid)
    my_part  = db.wc_get_participant(wc_id, uid)

    if not my_part:
        await q.answer("Ты не участвуешь в ЧМ.", show_alert=True)
        return

    # Матчи с прогнозами
    pred_matches = [m for m in schedule if m["id"] in my_preds]
    total_pts    = my_part["total_points"]
    exact_cnt    = my_part.get("exact_scores", 0)

    page_m = pred_matches[offset: offset + WC_SCHED_PAGE]
    lines  = []
    for m in page_m:
        pred = my_preds.get(m["id"])
        lines.append(_wc_match_line(m, pred))

    text = (
        f"📝 *МОИ ПРОГНОЗЫ*\n\n"
        f"Всего прогнозов: *{len(pred_matches)}*\n"
        f"Очков набрано: *{total_pts}* (из них точных счётов: *{exact_cnt}*)\n\n"
        + ("\n".join(lines) or "_Нет прогнозов_")
    )

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_wc_mypreds_{offset - WC_SCHED_PAGE}"))
    if offset + WC_SCHED_PAGE < len(pred_matches):
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_wc_mypreds_{offset + WC_SCHED_PAGE}"))
    kb = [nav] if nav else []
    kb.append([InlineKeyboardButton("◀ Назад", callback_data="fut_wc")])

    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


# ── Административные хендлеры ─────────────────────────────────────────────────

async def cb_fut_wc_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin$ — панель управления ЧМ (суперадмин)."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    wc = db.get_active_wc()
    if not wc:
        await q.edit_message_text(
            "🛠 *УПРАВЛЕНИЕ ЧМ*\n\n"
            "Активного ЧМ нет — открой экран «🌍 Чемпионат мира», "
            "режим создастся автоматически.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Назад", callback_data="fut_wc")],
            ]),
        )
        return

    wc_id    = wc["id"]
    schedule = wc.get("schedule") or []
    parts    = db.wc_get_participants(wc_id)
    open_m   = [m for m in schedule if m.get("status") == "open"]
    done_m   = [m for m in schedule if m.get("status") == "done"]
    settings = wc.get("settings") or {}
    prizes   = settings.get("prizes", WC_PRIZES_DEFAULT)

    await q.edit_message_text(
        f"🛠 *УПРАВЛЕНИЕ — {wc_id}*\n\n"
        f"Участников: *{len(parts)}*\n"
        f"Матчей: *{len(done_m)} сыграно / {len(schedule)} всего*\n"
        f"🟢 Открыто: *{len(open_m)}*\n\n"
        f"Призы: 🥇 {_fmt(prizes.get('1', 0))} | "
        f"🥈 {_fmt(prizes.get('2', 0))} | "
        f"🥉 {_fmt(prizes.get('3', 0))}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Матчи",         callback_data="fut_wc_admin_list_0")],
            [InlineKeyboardButton("🏁 Завершить ЧМ",  callback_data="fut_wc_admin_finish")],
            [InlineKeyboardButton("◀ Назад",           callback_data="fut_wc")],
        ]),
    )


async def cb_fut_wc_admin_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin_list_ — список матчей для управления."""
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    offset = int(q.data.split("_")[-1])
    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id    = wc["id"]
    schedule = wc.get("schedule") or []
    page_m   = schedule[offset: offset + WC_SCHED_PAGE]

    kb = []
    for m in page_m:
        st   = WC_STATUS_EMOJI.get(m.get("status", "upcoming"), "⏳")
        hf   = m.get("home_flag", "")
        af   = m.get("away_flag", "")
        label = f"{st} {m['id']}: {hf}{m['home'][:8]} — {af}{m['away'][:8]}"
        if m.get("status") == "done" and m.get("home_goals") is not None:
            label += f" {m['home_goals']}:{m['away_goals']}"
        kb.append([InlineKeyboardButton(label, callback_data=f"fut_wc_admin_match_{m['id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀", callback_data=f"fut_wc_admin_list_{offset - WC_SCHED_PAGE}"))
    if offset + WC_SCHED_PAGE < len(schedule):
        nav.append(InlineKeyboardButton("▶", callback_data=f"fut_wc_admin_list_{offset + WC_SCHED_PAGE}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Назад", callback_data="fut_wc_admin")])

    await q.edit_message_text(
        f"📋 *МАТЧИ — {wc_id}* ({offset + 1}–{min(offset + WC_SCHED_PAGE, len(schedule))} из {len(schedule)})\n\nВыбери матч для управления:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_wc_admin_match(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin_match_ — детали матча + кнопки управления."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    mid = q.data[len("fut_wc_admin_match_"):]
    wc  = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id = wc["id"]
    match = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), None)
    if not match:
        await q.answer("Матч не найден.", show_alert=True)
        return

    hf     = match.get("home_flag", "")
    af     = match.get("away_flag", "")
    status = match.get("status", "upcoming")
    st_lbl = {"upcoming": "⏳ Предстоит/нет команд", "open": "🟢 Открыт", "closed": "🔴 Закрыт (ждёт результат)", "done": "✅ Завершён"}.get(status, status)
    rnd    = WC_ROUND_LABELS.get(match.get("round", "group"), "")
    grp    = f" • Группа {match['group']}" if match.get("group") else ""
    dt_str = _wc_fmt_dt(match.get("kickoff"))
    is_tbd = match.get("home") in ("TBD", "?", "", None)

    res_str = ""
    if status == "done":
        res_str = f"\nРезультат: *{match.get('home_goals')}:{match.get('away_goals')}*"

    # Статистика прогнозов
    res_preds = db.get_client().table("wc_predictions").select("pred_winner, resolved, points_earned").eq("wc_id", wc_id).eq("match_id", mid).execute()
    pred_rows = res_preds.data or []
    n_preds   = len(pred_rows)
    n_res     = sum(1 for p in pred_rows if p.get("resolved"))

    text = (
        f"⚙️ *{mid}: {hf}{match['home']} — {af}{match['away']}*\n"
        f"_{rnd}{grp}_\n"
        f"🕐 {dt_str} (ET, местное)\n"
        f"Статус: {st_lbl}{res_str}\n"
        f"Прогнозов: *{n_preds}* (подведено: {n_res})"
    )

    kb = []
    kb.append([InlineKeyboardButton("✏️ Задать команды", callback_data=f"fut_wc_admin_teams_{mid}")])
    if not is_tbd:
        kb.append([InlineKeyboardButton("📝 Ввести/исправить результат", callback_data=f"fut_wc_admin_result_{mid}")])
        if status == "open":
            kb.append([InlineKeyboardButton("🔴 Закрыть досрочно", callback_data=f"fut_wc_admin_close_{mid}")])
        elif status == "closed" and match.get("locked"):
            kb.append([InlineKeyboardButton("🟢 Снять закрытие", callback_data=f"fut_wc_admin_open_{mid}")])
    kb.append([InlineKeyboardButton("◀ К списку", callback_data="fut_wc_admin_list_0")])

    await q.edit_message_text(text, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(kb))


async def cb_fut_wc_admin_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin_open_ — снять ручное закрытие (unlock)."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    mid = q.data[len("fut_wc_admin_open_"):]
    wc  = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    db.wc_set_lock(wc["id"], mid, False)
    await q.answer("🟢 Закрытие снято (статус — по времени матча)", show_alert=True)
    await cb_fut_wc_admin_match(update, ctx)


async def cb_fut_wc_admin_close(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin_close_ — закрыть приём прогнозов досрочно (lock)."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    mid = q.data[len("fut_wc_admin_close_"):]
    wc  = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    db.wc_set_lock(wc["id"], mid, True)
    await q.answer("🔴 Приём прогнозов закрыт", show_alert=True)
    await cb_fut_wc_admin_match(update, ctx)


async def cb_fut_wc_admin_teams(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin_teams_ — задать команды для матча (плей-офф)."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    mid = q.data[len("fut_wc_admin_teams_"):]
    wc  = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return
    match = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), None)
    if not match:
        await q.answer("Матч не найден.", show_alert=True)
        return

    db.set_pending_action(uid, "wc_teams_input", {"wc_id": wc["id"], "match_id": mid})
    rnd = WC_ROUND_LABELS.get(match.get("round", "group"), "")
    await q.edit_message_text(
        f"✏️ *Задать команды — {mid}*\n"
        f"_{rnd}, {_wc_fmt_dt(match.get('kickoff'))} ET_\n\n"
        f"Текущие: {match.get('home_flag','')}{match.get('home','?')} — "
        f"{match.get('away_flag','')}{match.get('away','?')}\n\n"
        f"Введи команды в формате:\n`Бразилия - Франция`\n\n"
        f"_(флаги подставятся автоматически по русскому названию)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data=f"fut_wc_admin_match_{mid}"),
        ]]),
    )


async def cb_fut_wc_admin_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin_result_ — начать ввод результата матча."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    mid = q.data[len("fut_wc_admin_result_"):]
    wc  = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    match = next((m for m in (wc.get("schedule") or []) if m["id"] == mid), None)
    if not match:
        await q.answer("Матч не найден.", show_alert=True)
        return

    hf = match.get("home_flag", "")
    af = match.get("away_flag", "")

    db.set_pending_action(uid, "wc_result_input", {"wc_id": wc["id"], "match_id": mid})

    await q.edit_message_text(
        f"📝 *Введи результат матча*\n\n"
        f"*{hf} {match['home']}* — *{af} {match['away']}*\n\n"
        f"Формат: `2:1` или `1:1`\n"
        f"_(отправь счёт текстом)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data=f"fut_wc_admin_match_{mid}"),
        ]]),
    )


async def cb_fut_wc_admin_finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """^fut_wc_admin_finish$ — завершить ЧМ и раздать призы."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    from config import SUPERADMIN_IDS
    if uid not in SUPERADMIN_IDS:
        await q.answer("Нет прав.", show_alert=True)
        return

    wc = db.get_active_wc()
    if not wc:
        await q.answer("Нет активного ЧМ.", show_alert=True)
        return

    wc_id    = wc["id"]
    settings = wc.get("settings") or {}
    prizes   = settings.get("prizes", WC_PRIZES_DEFAULT)
    parts    = db.wc_get_participants(wc_id)

    # Раздать призы топ-3
    for i, p in enumerate(parts[:3]):
        rank = i + 1
        prize = prizes.get(str(rank), 0)
        if prize > 0:
            db.add_coins(p["user_id"], prize)
            try:
                await ctx.bot.send_message(
                    chat_id=p["user_id"],
                    text=(
                        f"{_wc_rank_emoji(rank)} *ЧМ ЗАВЕРШЁН!*\n\n"
                        f"Ты занял *{rank}-е место* в {wc_id}!\n"
                        f"Приз: *+{_fmt(prize)} 💰*\n\n"
                        f"Твои очки: *{p['total_points']}*  Точных счётов: *{p.get('exact_scores', 0)}*"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    # Уведомить остальных
    for p in parts[3:]:
        try:
            my_rank = next((i + 1 for i, x in enumerate(parts) if x["user_id"] == p["user_id"]), "?")
            await ctx.bot.send_message(
                chat_id=p["user_id"],
                text=(
                    f"🏁 *{wc_id} завершён!*\n\n"
                    f"Твоё место: *#{my_rank}* | Очков: *{p['total_points']}*\n\n"
                    f"🥇 {parts[0]['name']} — {parts[0]['total_points']} очк.\n"
                    + (f"🥈 {parts[1]['name']} — {parts[1]['total_points']} очк.\n" if len(parts) > 1 else "")
                    + (f"🥉 {parts[2]['name']} — {parts[2]['total_points']} очк." if len(parts) > 2 else "")
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass

    db.update_wc(wc_id, status="finished")

    podium = "\n".join(
        f"{_wc_rank_emoji(i+1)} {p['name']} — {p['total_points']} очк. (+{_fmt(prizes.get(str(i+1), 0))} 💰)"
        for i, p in enumerate(parts[:3])
    ) or "_Нет участников_"

    await q.edit_message_text(
        f"🏆 *{wc_id} ЗАВЕРШЁН!*\n\n"
        f"*Пьедестал:*\n{podium}\n\n"
        f"Призы розданы. ЧМ закрыт.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu"),
        ]]),
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
        # ── Кросс-бот обменник ────────────────────────────────────────────────
        ("^fut_exchange_menu$",           cb_fut_exchange_menu),
        ("^fut_exchange_start_fut$",      cb_fut_exchange_start_fut),
        ("^fut_exchange_confirm_",        cb_fut_exchange_confirm),
        ("^fut_exchange_claim_c2f$",      cb_fut_exchange_claim_c2f),
        ("^fut_exchange_pending$",        cb_fut_exchange_pending),
        ("^fut_exchange_cancel_",         cb_fut_exchange_cancel),
        # ── Чемпионат мира ────────────────────────────────────────────────────
        ("^fut_wc_admin_open_",           cb_fut_wc_admin_open),
        ("^fut_wc_admin_close_",          cb_fut_wc_admin_close),
        ("^fut_wc_admin_result_",         cb_fut_wc_admin_result),
        ("^fut_wc_admin_teams_",          cb_fut_wc_admin_teams),
        ("^fut_wc_admin_match_",          cb_fut_wc_admin_match),
        ("^fut_wc_admin_list_",           cb_fut_wc_admin_list),
        ("^fut_wc_admin_finish$",         cb_fut_wc_admin_finish),
        ("^fut_wc_admin$",                cb_fut_wc_admin),
        ("^fut_wc_taken$",                cb_fut_wc_taken),
        ("^fut_wc_custom_",               cb_fut_wc_custom),
        ("^fut_wc_inpcancel_",            cb_fut_wc_inpcancel),
        ("^fut_wc_preds_",                cb_fut_wc_preds),            # просмотр прогнозов
        ("^fut_wc_psave_",                cb_fut_wc_pred_save),        # до fut_wc_pw_
        ("^fut_wc_pw_",                   cb_fut_wc_pred_winner),
        ("^fut_wc_predict_",              cb_fut_wc_predict),
        # ── Вкладки-разделы (soccer365-style) ──
        ("^fut_wc_tbl$",                  cb_fut_wc_table),
        ("^fut_wc_res_",                  cb_fut_wc_results),
        ("^fut_wc_teams$",                cb_fut_wc_teams),
        ("^fut_wc_stad$",                 cb_fut_wc_stadiums),
        ("^fut_wc_hist$",                 cb_fut_wc_history),
        ("^fut_wc_schedule_",             cb_fut_wc_schedule),
        ("^fut_wc_lb_",                   cb_fut_wc_leaderboard),
        ("^fut_wc_mypreds_",              cb_fut_wc_mypreds),
        ("^fut_wc_join$",                 cb_fut_wc_join),
        ("^fut_wc$",                      cb_fut_wc),
    ]
