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

Анимация открытия: 3–5 фаз, интенсивность зависит от топ-карты пака.
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

# ─── Веса рейтингов: меньше число → реже ──────────────────────────────────────
# (пропорционально, т.е. OVR 82 выпадает в ~32× чаще OVR 97)

RATING_WEIGHTS: dict[int, float] = {
    # Bronze
    82: 65.0,  83: 25.0,  84: 10.0,
    # Silver
    85: 60.0,  86: 28.0,  87: 12.0,
    # Gold
    88: 50.0,  89: 28.0,  90: 15.0,  91: 7.0,
    # Elite / Mega upper
    92: 38.0,  93: 28.0,  94: 18.0,  95: 9.0,  96: 5.0,  97: 2.0,
}

# Специальные версии (в 10× реже обычной карты того же OVR)
SPECIAL_VERSIONS = {
    "TOTY", "TOTS", "FUT BIRTHDAY", "FUTTIES",
    "HEROES", "RTTK", "OTW", "FLASHBACK", "ICON",
}
SPECIAL_MULT = 0.10

# Уровни «восхищения» для анимации
_LVL_LEGENDARY = "legendary"   # OVR 96–97 или TOTY/TOTS
_LVL_EPIC      = "epic"        # OVR 94–95 или любая спец-версия
_LVL_RARE      = "rare"        # OVR 92–93
_LVL_NORMAL    = "normal"


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _rarity(rating: int, version: str) -> str:
    v = version.upper()
    if v in SPECIAL_VERSIONS:      return "🌟 Спец"
    if rating >= 95:               return "🔮 Иконка"
    if rating >= 92:               return "💎 Редкая"
    if rating >= 88:               return "🥇 Золотая"
    if rating >= 85:               return "🥈 Серебряная"
    return "🥉 Бронзовая"


def _pos_icon(pos: str) -> str:
    p = pos.upper()
    if p in ("GK",):                                    return "🧤"
    if p in ("CB", "LB", "RB", "LWB", "RWB"):          return "🛡"
    if p in ("CDM", "CM", "CAM", "LM", "RM"):          return "⚙️"
    if p in ("LW", "RW", "LF", "RF", "CF", "ST", "SS"): return "⚽"
    return "🎽"


def _excitement(cards: list[dict]) -> str:
    """Определяем «уровень крутости» вытянутых карт."""
    max_r = max(c["rating"] for c in cards)
    versions = {c.get("version", "").upper() for c in cards}
    has_toty_tots = bool(versions & {"TOTY", "TOTS"})
    has_any_spec  = bool(versions & SPECIAL_VERSIONS)

    if has_toty_tots or max_r >= 96:
        return _LVL_LEGENDARY
    if has_any_spec or max_r >= 94:
        return _LVL_EPIC
    if max_r >= 92:
        return _LVL_RARE
    return _LVL_NORMAL


# ─── Взвешенная выборка без возврата ──────────────────────────────────────────

def _weighted_sample(pool: list[dict], n: int) -> list[dict]:
    """Взвешенная случайная выборка без повторений.
    Вес = RATING_WEIGHTS[ovr] × (SPECIAL_MULT если спец-версия)."""
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
        cumul = 0.0
        idx = len(available) - 1
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


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _add_to_club(user_id: int, player_ids: list[int]) -> None:
    rows = [{"user_id": user_id, "player_id": pid} for pid in player_ids]
    db.get_client().table("user_club").insert(rows).execute()


def _get_club(user_id: int, offset: int = 0) -> tuple[list[dict], int]:
    res = (
        db.get_client()
        .table("user_club")
        .select(
            "id, acquired_at, fut_players(id, name, club, nation, position, rating, version)",
            count="exact",
        )
        .eq("user_id", user_id)
        .order("acquired_at", desc=True)
        .range(offset, offset + CLUB_PAGE_SIZE - 1)
        .execute()
    )
    total = res.count or 0
    cards = []
    for row in (res.data or []):
        p = row.get("fut_players") or {}
        cards.append({
            "club_id":  row["id"],
            "name":     p.get("name", "?"),
            "club":     p.get("club", "?"),
            "nation":   p.get("nation", "?"),
            "position": p.get("position", "?"),
            "rating":   p.get("rating", 0),
            "version":  p.get("version", ""),
        })
    return cards, total


def _sell_duplicates(user_id: int) -> tuple[int, int]:
    """Продать дубликаты (оставить 1 экземпляр каждого игрока).
    Возвращает (проданных, заработано монет)."""
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

def _card_text(p: dict, index: int | None = None) -> str:
    icon = _pos_icon(p["position"])
    rar  = _rarity(p["rating"], p.get("version", ""))
    idx  = f"{index}. " if index is not None else ""
    return (
        f"{idx}{icon} *{p['name']}*\n"
        f"   {rar} • OVR *{p['rating']}* • {p['position']}\n"
        f"   🌍 {p['nation']} • 🏟 {p['club']}"
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
        is_spec = v in SPECIAL_VERSIONS

        if is_spec or p["rating"] >= 95:
            # Жирная подсветка для топ-карт
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

async def _animate_open(
    query,
    pack_name: str,
    cards: list[dict],
    cost: int,
    new_bal: int,
) -> None:
    """Многоэтапная анимация; количество и интенсивность фаз зависит от крутости карт."""
    level = _excitement(cards)
    slots = "🎴 " * len(cards)

    # ── Фаза 1: начало открытия (мгновенно) ──
    await query.edit_message_text(
        f"📦 *{pack_name}*\n\n{slots}\n_Перемешиваем колоду..._",
        parse_mode="Markdown",
    )
    await asyncio.sleep(1.2)

    # ── Фаза 2: тянем карты ──
    await query.edit_message_text(
        f"📦 *{pack_name}*\n\n✨ ✨ ✨\n_Тянем карточки..._",
        parse_mode="Markdown",
    )
    await asyncio.sleep(1.2)

    # ── Фазы 3–4: нагнетание (зависит от уровня) ──
    if level == _LVL_LEGENDARY:
        await query.edit_message_text(
            "🌟 *ЧТО-ТО НЕВЕРОЯТНОЕ!* 🌟\n\n"
            "⚡ ⚡ ⚡ ⚡ ⚡\n"
            "_Это должно быть..._",
            parse_mode="Markdown",
        )
        await asyncio.sleep(1.4)
        await query.edit_message_text(
            "🏆 *Л Е Г Е Н Д А* 🏆\n\n"
            "🔱 🔱 🔱 🔱 🔱\n"
            "_Открываем..._",
            parse_mode="Markdown",
        )
        await asyncio.sleep(1.4)

    elif level == _LVL_EPIC:
        await query.edit_message_text(
            "🔥 *РЕДЧАЙШАЯ КАРТА ЗАМЕЧЕНА!* 🔥\n\n"
            "💎 💎 💎 💎\n"
            "_Открываем..._",
            parse_mode="Markdown",
        )
        await asyncio.sleep(1.4)

    elif level == _LVL_RARE:
        await query.edit_message_text(
            "💎 *ОЙ, ЧТО ЭТО?* 💎\n\n"
            "✨ ✨ ✨ ✨\n"
            "_Почти..._",
            parse_mode="Markdown",
        )
        await asyncio.sleep(1.1)

    # ── Финальный экран с картами ──
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Ещё пак",  callback_data="fut_packs"),
         InlineKeyboardButton("🏟 Мой клуб", callback_data="fut_club_0")],
        [InlineKeyboardButton("◀ FUT меню",  callback_data="fut_menu")],
    ])
    await query.edit_message_text(
        _pack_result_text(pack_name, cards, cost, new_bal),
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ─── Handlers ────────────────────────────────────────────────────────────────

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
             InlineKeyboardButton("🏟 Мой клуб",    callback_data="fut_club_0")],
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

    await q.answer()   # подтверждаем сразу, далее — анимация через edit

    n_cards = pack["cards"]
    min_r   = pack["min_rating"]
    max_r   = pack["max_rating"]
    guar    = pack.get("guaranteed")

    cards: list[dict] = []
    if guar:
        hi = _draw_players(guar, max_r, 1)
        if hi:
            cards.extend(hi)
        cards.extend(_draw_players(min_r, max_r, n_cards - len(cards)))
    else:
        cards = _draw_players(min_r, max_r, n_cards)

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


async def cb_fut_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q      = update.callback_query
    await q.answer()
    uid    = q.from_user.id
    offset = int(q.data[len("fut_club_"):])

    cards, total = _get_club(uid, offset)

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

    pages      = (total + CLUB_PAGE_SIZE - 1) // CLUB_PAGE_SIZE
    cur_page   = offset // CLUB_PAGE_SIZE + 1
    card_lines = "\n\n".join(_card_text(c, i + offset + 1) for i, c in enumerate(cards))

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("◀ Пред", callback_data=f"fut_club_{offset - CLUB_PAGE_SIZE}"))
    if offset + CLUB_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("След ▶", callback_data=f"fut_club_{offset + CLUB_PAGE_SIZE}"))

    kb = []
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🗑 Продать дубликаты (+50💰/шт)", callback_data="fut_sell_dupes")])
    kb.append([InlineKeyboardButton("📦 Паки",    callback_data="fut_packs"),
               InlineKeyboardButton("◀ FUT меню", callback_data="fut_menu")])

    await q.edit_message_text(
        f"🏟 *МОЙ КЛУБ*  _{cur_page}/{pages}_  •  Всего: *{total}* карточек\n\n{card_lines}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_fut_sell_dupes(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id

    sold, earned = _sell_duplicates(uid)
    if sold == 0:
        await q.answer("Дубликатов нет — все игроки уникальны!", show_alert=True)
        return

    await q.answer(f"🗑 Продано {sold} дублей • +{_fmt(earned)} 💰")
    q.data = "fut_club_0"
    await cb_fut_club(update, ctx)


# ─── Registration ─────────────────────────────────────────────────────────────

def fut_handlers() -> list[tuple[str, Any]]:
    return [
        ("^fut_menu$",       cb_fut_menu),
        ("^fut_packs$",      cb_fut_packs),
        ("^fut_buy_",        cb_fut_buy),
        ("^fut_club_",       cb_fut_club),
        ("^fut_sell_dupes$", cb_fut_sell_dupes),
        ("^fut_no_coins$",   cb_fut_no_coins),
    ]
