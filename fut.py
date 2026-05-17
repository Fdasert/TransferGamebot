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
}

# Короткий ярлык слота (для пустых кнопок)
SLOT_LABEL: dict[str, str] = {
    "GK": "GK", "LB": "LB", "RB": "RB",
    "CB1": "CB", "CB2": "CB", "CB3": "CB",
    "LM": "LM", "RM": "RM",
    "CM1": "CM", "CM2": "CM", "CM3": "CM",
    "CDM1": "CDM", "CDM2": "CDM", "CAM": "CAM",
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
        f"`{p['position']}`  •  {p['nation']}  •  {p['club']}\n\n"
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
            [InlineKeyboardButton("🧩 Команда",     callback_data="fut_team")],
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
        # Нет команды — сразу выбор схемы
        rows = [
            [InlineKeyboardButton(f["label"], callback_data=f"fut_team_setform_{key}")]
            for key, f in FORMATIONS.items()
        ] + [[InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")]]
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

    rows = [
        [InlineKeyboardButton(f["label"], callback_data=f"fut_team_setform_{key}")]
        for key, f in FORMATIONS.items()
    ] + [[InlineKeyboardButton("◀ Назад", callback_data="fut_team")]]

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
        lbl = f"{_pos_icon(c['position'])} {c['name'][:18]}  {rar} {c['rating']}"
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

    slots        = dict(team.get("slots") or {})
    slots[slot]  = club_id
    _save_team(uid, team["formation"], slots)

    card = _get_card_by_id(club_id)
    name = card["name"] if card else "?"
    await q.answer(f"✅ {name} → {SLOT_LABEL.get(slot, slot)}")

    q.data = "fut_team"
    await cb_fut_team(update, ctx)


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
    ]
