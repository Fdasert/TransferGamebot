"""FUT-режим: пакеты карточек и Мой клуб.

Пакеты:
  Bronze  — 1 500 монет  — 3 карты, OVR 82–84
  Silver  — 4 000 монет  — 3 карты, OVR 85–87
  Gold    — 12 000 монет — 3 карты, OVR 88–91
  Elite   — 30 000 монет — 3 карты, OVR 92–97
  Mega    — 60 000 монет — 5 карт,  OVR 88–97, гарант. 1× OVR 93+

Шансы выпадения:
  — Рейтинг: взвешенный (высокий OVR = редкость)
  — Спец-версии (TOTY/TOTS/Hero/…): в 10× реже обычной карты того же рейтинга

Мой клуб:
  — Список карточек в виде кнопок, сортировка OVR↓ / OVR↑ / Позиция
  — Тап → полная карточка (стат-бары, название, позиция, нация, клуб)
  — Продажа любой карточки за монеты, цена зависит от OVR + спец-версия ×2
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


# ─── Пакеты ───────────────────────────────────────────────────────────────────

PACKS: dict[str, dict] = {
    "bronze": {
        "name": "🥉 Бронзовый пак",
        "cost": 1_500,
        "cards": 3,
        "min_rating": 82,
        "max_rating": 84,
        "guaranteed": None,
        "desc": "3 карты • OVR 82–84",
    },
    "silver": {
        "name": "🥈 Серебряный пак",
        "cost": 4_000,
        "cards": 3,
        "min_rating": 85,
        "max_rating": 87,
        "guaranteed": None,
        "desc": "3 карты • OVR 85–87",
    },
    "gold": {
        "name": "🥇 Золотой пак",
        "cost": 12_000,
        "cards": 3,
        "min_rating": 88,
        "max_rating": 91,
        "guaranteed": None,
        "desc": "3 карты • OVR 88–91",
    },
    "elite": {
        "name": "💎 Элитный пак",
        "cost": 30_000,
        "cards": 3,
        "min_rating": 92,
        "max_rating": 97,
        "guaranteed": None,
        "desc": "3 карты • OVR 92–97",
    },
    "mega": {
        "name": "⚡ Мега пак",
        "cost": 60_000,
        "cards": 5,
        "min_rating": 88,
        "max_rating": 97,
        "guaranteed": 93,
        "desc": "5 карт • OVR 88–97 • Гарант OVR 93+",
    },
}

CLUB_PAGE_SIZE = 5

# ─── Веса рейтингов ────────────────────────────────────────────────────────────

RATING_WEIGHTS: dict[int, float] = {
    82: 65.0, 83: 25.0, 84: 10.0,
    85: 60.0, 86: 28.0, 87: 12.0,
    88: 50.0, 89: 28.0, 90: 15.0, 91: 7.0,
    92: 38.0, 93: 28.0, 94: 18.0, 95: 9.0, 96: 5.0, 97: 2.0,
}

SPECIAL_VERSIONS = {
    "TOTY", "TOTS", "FUT BIRTHDAY", "FUTTIES",
    "HEROES", "RTTK", "OTW", "FLASHBACK", "ICON",
}
SPECIAL_MULT = 0.10

# Уровни анимации
_LVL_LEGENDARY = "legendary"
_LVL_EPIC      = "epic"
_LVL_RARE      = "rare"
_LVL_NORMAL    = "normal"

# Порядок позиций для сортировки
_POS_ORDER: dict[str, int] = {
    "GK": 1,
    "CB": 2, "LB": 2, "RB": 2, "LWB": 2, "RWB": 2,
    "CDM": 3, "CM": 3, "CAM": 3, "LM": 3, "RM": 3,
    "LW": 4, "RW": 4, "LF": 4, "RF": 4, "CF": 4, "ST": 4, "SS": 4,
}


# ─── Утилиты ──────────────────────────────────────────────────────────────────

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
    if p in ("GK",):                                     return "🧤"
    if p in ("CB", "LB", "RB", "LWB", "RWB"):           return "🛡"
    if p in ("CDM", "CM", "CAM", "LM", "RM"):           return "⚙️"
    if p in ("LW", "RW", "LF", "RF", "CF", "ST", "SS"): return "⚽"
    return "🎽"


def _stat_bar(value: int) -> str:
    """Прогресс-бар из 8 блоков для значения 0–100."""
    filled = max(0, min(8, round(value / 100 * 8)))
    return "▓" * filled + "░" * (8 - filled)


def _sell_price(rating: int, version: str) -> int:
    """Цена продажи карточки зависит от OVR и версии."""
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


def _excitement(cards: list[dict]) -> str:
    max_r = max(c["rating"] for c in cards)
    vers  = {c.get("version", "").upper() for c in cards}
    if bool(vers & {"TOTY", "TOTS"}) or max_r >= 96: return _LVL_LEGENDARY
    if bool(vers & SPECIAL_VERSIONS)  or max_r >= 94: return _LVL_EPIC
    if max_r >= 92:                                    return _LVL_RARE
    return _LVL_NORMAL


# ─── Взвешенная выборка ───────────────────────────────────────────────────────

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
        .gte("rating", min_r)
        .lte("rating", max_r)
        .execute()
    )
    return _weighted_sample(res.data or [], n)


# ─── DB helpers — клуб ────────────────────────────────────────────────────────

def _get_club_all(user_id: int) -> list[dict]:
    """Все карточки пользователя со статами (для сортировки в Python)."""
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
    return sorted(cards, key=lambda c: -c["rating"])  # "od" default


def _get_card_by_id(club_id: int) -> dict | None:
    """Одна карточка по user_club.id."""
    res = (
        db.get_client()
        .table("user_club")
        .select(
            "id, fut_players(id, name, club, nation, position, rating, version, pac, sho, pas, dri, def, phy)"
        )
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
    """Продать дубликаты (оставить 1 экземпляр каждого игрока)."""
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


# ─── Форматирование карточки ───────────────────────────────────────────────────

def _card_detail_text(p: dict) -> str:
    """Полная карточка со стат-барами."""
    rar      = _rarity(p["rating"], p.get("version", ""))
    pos_icon = _pos_icon(p["position"])
    name     = p["name"].upper()

    # Версия (если спец — показать)
    v = p.get("version", "").upper()
    ver_line = f"  _✦ {p['version']}_\n" if v in SPECIAL_VERSIONS else ""

    return (
        f"{rar}   OVR *{p['rating']}*\n"
        f"{ver_line}\n"
        f"{pos_icon}  *{name}*\n"
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


# ─── Анимация открытия ────────────────────────────────────────────────────────

async def _animate_open(query, pack_name: str, cards: list[dict], cost: int, new_bal: int) -> None:
    level = _excitement(cards)
    slots = "🎴 " * len(cards)

    await query.edit_message_text(
        f"📦 *{pack_name}*\n\n{slots}\n_Перемешиваем колоду..._",
        parse_mode="Markdown",
    )
    await asyncio.sleep(1.2)

    await query.edit_message_text(
        f"📦 *{pack_name}*\n\n✨ ✨ ✨\n_Тянем карточки..._",
        parse_mode="Markdown",
    )
    await asyncio.sleep(1.2)

    if level == _LVL_LEGENDARY:
        await query.edit_message_text(
            "🌟 *ЧТО-ТО НЕВЕРОЯТНОЕ!* 🌟\n\n⚡ ⚡ ⚡ ⚡ ⚡\n_Это должно быть..._",
            parse_mode="Markdown",
        )
        await asyncio.sleep(1.4)
        await query.edit_message_text(
            "🏆 *Л Е Г Е Н Д А* 🏆\n\n🔱 🔱 🔱 🔱 🔱\n_Открываем..._",
            parse_mode="Markdown",
        )
        await asyncio.sleep(1.4)
    elif level == _LVL_EPIC:
        await query.edit_message_text(
            "🔥 *РЕДЧАЙШАЯ КАРТА ЗАМЕЧЕНА!* 🔥\n\n💎 💎 💎 💎\n_Открываем..._",
            parse_mode="Markdown",
        )
        await asyncio.sleep(1.4)
    elif level == _LVL_RARE:
        await query.edit_message_text(
            "💎 *ОЙ, ЧТО ЭТО?* 💎\n\n✨ ✨ ✨ ✨\n_Почти..._",
            parse_mode="Markdown",
        )
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


# ─── Handlers: меню и паки ───────────────────────────────────────────────────

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
        await q.answer("Неизвестный пак.", show_alert=True)
        return

    ok, _ = db.spend_coins(uid, pack["cost"])
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True)
        return

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
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ Паки", callback_data="fut_packs"),
            ]]),
        )
        return

    _add_to_club(uid, [c["id"] for c in cards])
    new_bal = db.get_coins(uid)
    await _animate_open(q, pack["name"], cards, pack["cost"], new_bal)


# ─── Handlers: Мой клуб ───────────────────────────────────────────────────────

async def cb_fut_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Список карточек с сортировкой и пагинацией.
    callback_data: fut_club_{offset}_{sort}  (sort: od | oa | pos)
    """
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    # Парсим offset и sort из callback_data
    tail  = q.data[len("fut_club_"):]
    parts = tail.split("_")
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

    # Корректируем offset, если вышли за границу
    offset = max(0, min(offset, ((total - 1) // CLUB_PAGE_SIZE) * CLUB_PAGE_SIZE))

    page_cards = all_cards[offset: offset + CLUB_PAGE_SIZE]
    pages      = (total + CLUB_PAGE_SIZE - 1) // CLUB_PAGE_SIZE
    cur_page   = offset // CLUB_PAGE_SIZE + 1

    # Кнопки-карточки (каждая открывает детальный вид)
    card_buttons = []
    for c in page_cards:
        icon  = _pos_icon(c["position"])
        rstar = _rarity_short(c["rating"], c["version"])
        label = f"{icon} {c['name'][:18]}  {rstar} {c['rating']}"
        card_buttons.append([
            InlineKeyboardButton(label, callback_data=f"fut_card_{c['club_id']}_{offset}_{sort}")
        ])

    # Сортировка
    sort_row = [
        InlineKeyboardButton(
            f"{'▶ ' if sort == 'od' else ''}OVR↓",
            callback_data=f"fut_club_{offset}_od",
        ),
        InlineKeyboardButton(
            f"{'▶ ' if sort == 'oa' else ''}OVR↑",
            callback_data=f"fut_club_{offset}_oa",
        ),
        InlineKeyboardButton(
            f"{'▶ ' if sort == 'pos' else ''}Позиция",
            callback_data=f"fut_club_{offset}_pos",
        ),
    ]

    # Пагинация
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_club_{offset - CLUB_PAGE_SIZE}_{sort}"))
    if offset + CLUB_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_club_{offset + CLUB_PAGE_SIZE}_{sort}"))

    kb = card_buttons + [sort_row]
    if nav:
        kb.append(nav)
    kb.append([
        InlineKeyboardButton("🗑 Продать дубликаты", callback_data="fut_sell_dupes"),
    ])
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
    """Детальный вид одной карточки.
    callback_data: fut_card_{club_id}_{offset}_{sort}
    """
    q   = update.callback_query
    await q.answer()

    tail  = q.data[len("fut_card_"):]
    parts = tail.split("_")
    club_id = int(parts[0])
    offset  = int(parts[1]) if len(parts) > 1 else 0
    sort    = parts[2]       if len(parts) > 2 else "od"

    card = _get_card_by_id(club_id)
    if not card:
        await q.answer("Карточка не найдена.", show_alert=True)
        return

    price = _sell_price(card["rating"], card["version"])

    await q.edit_message_text(
        _card_detail_text(card),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"💰 Продать за {_fmt(price)} монет",
                callback_data=f"fut_sell_confirm_{club_id}_{offset}_{sort}",
            )],
            [InlineKeyboardButton(
                "◀ Назад в клуб",
                callback_data=f"fut_club_{offset}_{sort}",
            )],
        ]),
    )


async def cb_fut_sell_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Экран подтверждения продажи.
    callback_data: fut_sell_confirm_{club_id}_{offset}_{sort}
    """
    q   = update.callback_query
    uid = q.from_user.id

    tail  = q.data[len("fut_sell_confirm_"):]
    parts = tail.split("_")
    club_id = int(parts[0])
    offset  = int(parts[1]) if len(parts) > 1 else 0
    sort    = parts[2]       if len(parts) > 2 else "od"

    card = _get_card_by_id(club_id)
    if not card:
        await q.answer("Карточка не найдена.", show_alert=True)
        return

    price   = _sell_price(card["rating"], card["version"])
    rar     = _rarity(card["rating"], card["version"])
    pos_icon = _pos_icon(card["position"])

    # Выполняем продажу сразу — без лишнего экрана (ответ через alert)
    _delete_from_club(club_id)
    db.add_coins(uid, price)
    new_bal = db.get_coins(uid)

    await q.answer(f"✅ Продано! +{_fmt(price)} 💰", show_alert=False)

    # Возвращаем обновлённый список клуба
    q.data = f"fut_club_{offset}_{sort}"
    await cb_fut_club(update, ctx)


async def cb_fut_sell_dupes(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id

    sold, earned = _sell_duplicates(uid)
    if sold == 0:
        await q.answer("Дубликатов нет — все игроки уникальны!", show_alert=True)
        return

    await q.answer(f"🗑 Продано {sold} дублей • +{_fmt(earned)} 💰")
    q.data = "fut_club_0_od"
    await cb_fut_club(update, ctx)


# ─── Registration ─────────────────────────────────────────────────────────────

def fut_handlers() -> list[tuple[str, Any]]:
    return [
        ("^fut_menu$",            cb_fut_menu),
        ("^fut_packs$",           cb_fut_packs),
        ("^fut_buy_",             cb_fut_buy),
        ("^fut_sell_confirm_",    cb_fut_sell_confirm),
        ("^fut_card_",            cb_fut_card),
        ("^fut_club_",            cb_fut_club),
        ("^fut_sell_dupes$",      cb_fut_sell_dupes),
        ("^fut_no_coins$",        cb_fut_no_coins),
    ]
