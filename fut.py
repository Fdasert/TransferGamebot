"""FUT-режим: пакеты карточек и Мой клуб.

Пакеты:
  Bronze  — 200 монет  — 3 карты, OVR 82–84
  Silver  — 500 монет  — 3 карты, OVR 85–87
  Gold    — 1500 монет — 3 карты, OVR 88–91
  Elite   — 4000 монет — 3 карты, OVR 92–97 (шанс TOTY/TOTS)
  Mega    — 8000 монет — 5 карт,  OVR 88–97, гарант. 1× OVR 93+

Мой клуб — просмотр карточек, сортировка, удаление дублей за монеты.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)


# ─── константы пакетов ────────────────────────────────────────────────────────

PACKS: dict[str, dict] = {
    "bronze": {
        "name": "🥉 Бронзовый пак",
        "cost": 200,
        "cards": 3,
        "min_rating": 82,
        "max_rating": 84,
        "guaranteed": None,
        "desc": "3 карты • OVR 82–84",
    },
    "silver": {
        "name": "🥈 Серебряный пак",
        "cost": 500,
        "cards": 3,
        "min_rating": 85,
        "max_rating": 87,
        "guaranteed": None,
        "desc": "3 карты • OVR 85–87",
    },
    "gold": {
        "name": "🥇 Золотой пак",
        "cost": 1_500,
        "cards": 3,
        "min_rating": 88,
        "max_rating": 91,
        "guaranteed": None,
        "desc": "3 карты • OVR 88–91",
    },
    "elite": {
        "name": "💎 Элитный пак",
        "cost": 4_000,
        "cards": 3,
        "min_rating": 92,
        "max_rating": 97,
        "guaranteed": None,
        "desc": "3 карты • OVR 92–97",
    },
    "mega": {
        "name": "⚡ Мега пак",
        "cost": 8_000,
        "cards": 5,
        "min_rating": 88,
        "max_rating": 97,
        "guaranteed": 93,       # гарантирована хотя бы 1 карта OVR 93+
        "desc": "5 карт • OVR 88–97 • Гарант OVR 93+",
    },
}

# Число карточек на страницу в «Моём клубе»
CLUB_PAGE_SIZE = 5

# Редкость по рейтингу (для отображения)
def _rarity(rating: int, version: str) -> str:
    v = version.upper()
    if v in ("TOTY", "TOTS", "FUT BIRTHDAY", "FUTTIES"):
        return "🌟 Спец"
    if rating >= 95: return "🔮 Иконка"
    if rating >= 92: return "💎 Редкая"
    if rating >= 88: return "🥇 Золотая"
    if rating >= 85: return "🥈 Серебряная"
    return "🥉 Бронзовая"


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _pos_icon(pos: str) -> str:
    p = pos.upper()
    if p in ("GK",):                             return "🧤"
    if p in ("CB", "LB", "RB", "LWB", "RWB"):   return "🛡"
    if p in ("CDM", "CM", "CAM", "LM", "RM"):   return "⚙️"
    if p in ("LW", "RW", "LF", "RF", "CF", "ST", "SS"): return "⚽"
    return "🎽"


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _draw_players(min_r: int, max_r: int, n: int) -> list[dict]:
    """Вернуть n случайных игроков из fut_players в диапазоне OVR."""
    res = (
        db.get_client()
        .table("fut_players")
        .select("id, name, club, nation, position, rating, version, pac, sho, pas, dri, def, phy")
        .gte("rating", min_r)
        .lte("rating", max_r)
        .execute()
    )
    pool = res.data or []
    if not pool:
        return []
    return random.sample(pool, min(n, len(pool)))


def _add_to_club(user_id: int, player_ids: list[int]) -> None:
    rows = [{"user_id": user_id, "player_id": pid} for pid in player_ids]
    db.get_client().table("user_club").insert(rows).execute()


def _get_club(user_id: int, offset: int = 0) -> tuple[list[dict], int]:
    """Вернуть (карточки на текущей странице, всего карточек)."""
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
    Возвращает (проданных карточек, заработано монет)."""
    res = (
        db.get_client()
        .table("user_club")
        .select("id, player_id")
        .eq("user_id", user_id)
        .order("acquired_at")
        .execute()
    )
    rows = res.data or []
    seen: set[int] = set()
    to_delete: list[int] = []
    for row in rows:
        pid = row["player_id"]
        if pid in seen:
            to_delete.append(row["id"])
        else:
            seen.add(pid)

    if not to_delete:
        return 0, 0

    for cid in to_delete:
        db.get_client().table("user_club").delete().eq("id", cid).execute()

    coins_per = 50
    earned = len(to_delete) * coins_per
    db.add_coins(user_id, earned)
    return len(to_delete), earned


# ─── card formatter ───────────────────────────────────────────────────────────

def _card_text(p: dict, index: int | None = None) -> str:
    icon = _pos_icon(p["position"])
    rar  = _rarity(p["rating"], p.get("version", ""))
    name = p["name"]
    idx  = f"{index}. " if index is not None else ""
    return (
        f"{idx}{icon} *{name}*\n"
        f"   {rar} • OVR *{p['rating']}* • {p['position']}\n"
        f"   🌍 {p['nation']} • 🏟 {p['club']}"
    )


def _pack_result_text(pack_name: str, cards: list[dict], cost: int, new_bal: int) -> str:
    lines = [f"📦 *{pack_name}*\n"]
    for i, p in enumerate(cards, 1):
        icon = _pos_icon(p["position"])
        rar  = _rarity(p["rating"], p.get("version", ""))
        lines.append(f"{i}. {icon} *{p['name']}*  {rar}  OVR *{p['rating']}*")
        lines.append(f"    {p['nation']} • {p['club']} • {p['position']}")
    lines.append(f"\n💸 Потрачено: *{_fmt(cost)} 💰*")
    lines.append(f"💼 Баланс: *{_fmt(new_bal)} 💰*")
    return "\n".join(lines)


# ─── handlers ────────────────────────────────────────────────────────────────

async def cb_fut_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)

    # Сколько карточек у юзера
    res   = db.get_client().table("user_club").select("id", count="exact").eq("user_id", uid).execute()
    total = res.count or 0

    rows = [
        [InlineKeyboardButton("📦 Открыть пак",  callback_data="fut_packs"),
         InlineKeyboardButton("🏟 Мой клуб",     callback_data="fut_club_0")],
        [InlineKeyboardButton("◀ В меню",        callback_data="menu_back")],
    ]
    await q.edit_message_text(
        "⚽ *FUT КЛУБ*\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n"
        f"🃏 Карточек в клубе: *{total}*\n\n"
        "Открывай паки, собирай игроков и строй свою команду!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
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
    q      = update.callback_query
    uid    = q.from_user.id
    pack_key = q.data[len("fut_buy_"):]

    pack = PACKS.get(pack_key)
    if not pack:
        await q.answer("Неизвестный пак.", show_alert=True); return

    ok, _ = db.spend_coins(uid, pack["cost"])
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return
    await q.answer(f"📦 Открываем {pack['name']}...")

    n_cards  = pack["cards"]
    min_r    = pack["min_rating"]
    max_r    = pack["max_rating"]
    guar     = pack.get("guaranteed")

    cards: list[dict] = []

    if guar:
        # Гарантированная карта OVR guar+
        hi = _draw_players(guar, max_r, 1)
        if hi:
            cards.extend(hi)
        # Остальные в общем диапазоне
        rest = _draw_players(min_r, max_r, n_cards - len(cards))
        cards.extend(rest)
    else:
        cards = _draw_players(min_r, max_r, n_cards)

    if not cards:
        new_bal = db.add_coins(uid, pack["cost"])
        await q.edit_message_text(
            "❌ Не удалось найти игроков в базе. Монеты возвращены.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ Паки", callback_data="fut_packs"),
            ]]),
        )
        return

    _add_to_club(uid, [c["id"] for c in cards])
    new_bal = db.get_coins(uid)

    text = _pack_result_text(pack["name"], cards, pack["cost"], new_bal)
    await q.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Ещё пак",    callback_data="fut_packs"),
             InlineKeyboardButton("🏟 Мой клуб",   callback_data="fut_club_0")],
            [InlineKeyboardButton("◀ FUT меню",    callback_data="fut_menu")],
        ]),
    )


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
    # Обновляем экран клуба
    q.data = "fut_club_0"
    await cb_fut_club(update, ctx)


# ─── registration ─────────────────────────────────────────────────────────────

def fut_handlers() -> list[tuple[str, Any]]:
    return [
        ("^fut_menu$",       cb_fut_menu),
        ("^fut_packs$",      cb_fut_packs),
        ("^fut_buy_",        cb_fut_buy),
        ("^fut_club_",       cb_fut_club),
        ("^fut_sell_dupes$", cb_fut_sell_dupes),
        ("^fut_no_coins$",   cb_fut_no_coins),
    ]
