"""Casino — рулетка, слоты, блэкджек, глобальная рулетка.

Адаптирован из cubeasses. Без VIP-зала, акций и магазина предметов.
Все DB-вызовы синхронные (supabase-py sync client).
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _fmt(n: int) -> str:
    """1000000 → '1 000 000'"""
    return f"{n:,}".replace(",", " ")


# ═════════════════════════════════════════════════════════════════════════════
# Roulette constants
# ═════════════════════════════════════════════════════════════════════════════

_ROULETTE_SECTORS = [
    # (вес, метка, emoji, множитель)  множитель -2 = двойная потеря
    (43, "Пусто",   "💀",  0),
    (8,  "Слив",    "💣", -2),
    (10, "Возврат", "🔄",  1),
    (20, "×2",      "💰",  2),
    (10, "×3",      "💎",  3),
    (4,  "×5",      "🌟",  5),
    (2,  "×10",     "💥", 10),
    (1,  "×25",     "⚡", 25),
    (2,  "Бонус",   "🎁",  3),   # бонус ×3 (вместо предмета из магазина)
]

_ROULETTE_BETS = [50, 100, 250, 500, 1_000, 2_500]

_WHEEL_DISPLAY = (
    "💀 Пусто — 43%\n"
    "💣 Слив ×2 — 8%\n"
    "🔄 Возврат — 10%\n"
    "💰 ×2 — 20%\n"
    "💎 ×3 — 10%\n"
    "🌟 ×5 — 4%\n"
    "💥 ×10 — 2%\n"
    "⚡ ×25 — 1%\n"
    "🎁 Бонус ×3 — 2%"
)

_SPIN_FRAMES = [
    "💀  💣  🔄  💰  💎  🌟  💥  ⚡  🎁",
    "🎁  💀  💣  🔄  💰  💎  🌟  💥  ⚡",
    "⚡  🎁  💀  💣  🔄  💰  💎  🌟  💥",
    "💥  ⚡  🎁  💀  💣  🔄  💰  💎  🌟",
]


def _spin_roulette() -> dict:
    weights = [s[0] for s in _ROULETTE_SECTORS]
    _, label, emoji, mult = random.choices(_ROULETTE_SECTORS, weights=weights, k=1)[0]
    return {
        "label": label, "emoji": emoji, "mult": mult,
        "is_doom":  (mult == -2),
        "is_bonus": (label == "Бонус"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Slot machine constants
# ═════════════════════════════════════════════════════════════════════════════

# (emoji, вес, множитель за тройку)
_SLOT_SYMBOLS: list[tuple[str, int, int]] = [
    ("🍒", 28,  4),
    ("🍋", 22,  8),
    ("🍊", 18, 12),
    ("🍇", 14, 18),
    ("🔔", 10, 30),
    ("💎",  6, 75),
    ("⭐",  2, 150),
]

_SLOT_BONUS_CHANCE = 0.04   # 4% шанс бонус-игры
_SLOT_BONUS_COST   = 20     # покупка бонуса = ×20 ставки
_SLOT_SPIN_SYM     = "🌀"

_BONUS_WILD    = "🌟"
_BONUS_SCATTER = "🔥"

_BONUS_LEVELS: dict[int, dict] = {
    1: {"spins": 3, "mult": 2,  "wild_w": 5,  "scatter_w": 7,  "name": "🥉 Уровень 1"},
    2: {"spins": 3, "mult": 4,  "wild_w": 8,  "scatter_w": 7,  "name": "🥈 Уровень 2"},
    3: {"spins": 3, "mult": 8,  "wild_w": 12, "scatter_w": 0,  "name": "🥇 ФИНАЛ"},
}

_BONUS_SYM_WEIGHTS: dict[int, list] = {
    1: [28, 22, 18, 14, 10, 6, 2],
    2: [26, 20, 17, 13, 10, 7, 3],
    3: [22, 18, 16, 13, 10, 8, 4],
}

_SLOT_LEGEND = (
    "🍒🍒🍒 → ×4    🍋🍋🍋 → ×8\n"
    "🍊🍊🍊 → ×12   🍇🍇🍇 → ×18\n"
    "🔔🔔🔔 → ×30   💎💎💎 → ×75\n"
    "⭐⭐⭐ → ×150 🏆 ДЖЕКПОТ\n"
    "Любая пара → ставка возвращается\n"
    f"🔥 Бонус-игра: 4% шанс или купить за ×{_SLOT_BONUS_COST} ставки"
)


def _spin_slot_reels() -> tuple[str, str, str]:
    emojis  = [s[0] for s in _SLOT_SYMBOLS]
    weights = [s[1] for s in _SLOT_SYMBOLS]
    return tuple(random.choices(emojis, weights=weights, k=3))  # type: ignore


def _eval_slots(s1: str, s2: str, s3: str) -> tuple[str, int]:
    if s1 == s2 == s3:
        mult = next((s[2] for s in _SLOT_SYMBOLS if s[0] == s1), 4)
        return "triple", mult
    if s1 == s2 or s1 == s3 or s2 == s3:
        return "double", 1
    return "miss", 0


def _spin_bonus_reels(level: int) -> tuple[str, str, str]:
    cfg  = _BONUS_LEVELS.get(level, _BONUS_LEVELS[1])
    base = [s[0] for s in _SLOT_SYMBOLS]
    wts  = list(_BONUS_SYM_WEIGHTS.get(level, _BONUS_SYM_WEIGHTS[1]))
    syms = base + [_BONUS_WILD]
    wts  = wts  + [cfg["wild_w"]]
    if cfg["scatter_w"] > 0:
        syms += [_BONUS_SCATTER]
        wts  += [cfg["scatter_w"]]
    return tuple(random.choices(syms, weights=wts, k=3))  # type: ignore


def _eval_bonus_spin(s1: str, s2: str, s3: str) -> tuple[str, int, bool, str]:
    """(kind, base_mult, scatter_hit, disp_sym)"""
    scatter_hit = _BONUS_SCATTER in [s1, s2, s3]
    norm     = [_BONUS_WILD if s == _BONUS_SCATTER else s for s in [s1, s2, s3]]
    non_wild = [s for s in norm if s != _BONUS_WILD]
    n_wild   = 3 - len(non_wild)

    if n_wild == 3:
        return "triple", 150, scatter_hit, "⭐"
    if n_wild == 2:
        sym  = non_wild[0]
        mult = next((s[2] for s in _SLOT_SYMBOLS if s[0] == sym), 4)
        return "triple", mult, scatter_hit, sym
    if n_wild == 1:
        if len(non_wild) >= 2 and non_wild[0] == non_wild[1]:
            sym  = non_wild[0]
            mult = next((s[2] for s in _SLOT_SYMBOLS if s[0] == sym), 4)
            return "triple", mult, scatter_hit, sym
        return "double", 1, scatter_hit, non_wild[0] if non_wild else _BONUS_WILD
    n1, n2, n3 = norm
    if n1 == n2 == n3:
        mult = next((s[2] for s in _SLOT_SYMBOLS if s[0] == n1), 4)
        return "triple", mult, scatter_hit, n1
    if n1 == n2 or n1 == n3 or n2 == n3:
        return "double", 1, scatter_hit, n1
    return "miss", 0, scatter_hit, n1


def _slot_board(r1: str, r2: str, r3: str) -> str:
    return f"{r1}  {r2}  {r3}"


def _slot_result_text(kind: str, mult: int, s1: str, s2: str, s3: str,
                      bet: int, new_balance: int, bonus: bool = False) -> str:
    b_tag = "🌟 *БОНУС* " if bonus else ""
    board = _slot_board(s1, s2, s3)

    if kind == "miss":
        return (
            f"🎰 {b_tag}*СЛОТЫ*\n\n"
            f"{board}\n\n"
            f"💀 *Мимо* — ставка сгорела\n\n"
            f"💼 Баланс: *{_fmt(new_balance)} 💰*"
        )

    if kind == "double":
        return (
            f"🎰 {b_tag}*СЛОТЫ*\n\n"
            f"{board}\n\n"
            f"🔄 *Пара!* — ставка возвращается\n\n"
            f"💼 Баланс: *{_fmt(new_balance)} 💰*"
        )

    # triple
    winnings = bet * mult
    net_gain = winnings - bet
    if s1 == "⭐":
        hdr   = "🏆 *Д Ж Е К П О Т !* 🏆"
        deco  = "⭐  ⭐  ⭐"
    elif mult >= 75:
        hdr   = "💥 *М Е Г А - Т Р О Й К А !* 💥"
        deco  = f"{s1}  {s1}  {s1}"
    elif bonus:
        hdr   = f"✨ *Т Р О Й К А !* ✨"
        deco  = f"{s1}  {s1}  {s1}"
    else:
        hdr   = f"🎉 *Т Р О Й К А !* 🎉"
        deco  = f"{s1}  {s1}  {s1}"

    return (
        f"🎰 {b_tag}*СЛОТЫ*\n\n"
        f"{hdr}\n\n"
        f"{deco}\n\n"
        f"×{mult}  —  Ставка: *{_fmt(bet)} 💰*\n"
        f"Выплата: *{_fmt(winnings)} 💰*  _(+{_fmt(net_gain)} 💰)_\n\n"
        f"💼 Баланс: *{_fmt(new_balance)} 💰*"
    )


def _bonus_progress_bar(level: int, spin_num: int, remaining: int) -> str:
    parts = []
    for lvl in [1, 2, 3]:
        cfg_l = _BONUS_LEVELS[lvl]
        ico   = cfg_l["name"].split()[0]
        if lvl < level:
            parts.append(f"{ico}✅")
        elif lvl == level:
            dots = "●" * spin_num + "○" * remaining
            parts.append(f"{ico}\\[{dots}\\]")
        else:
            parts.append(f"{ico}\\[{'○' * cfg_l['spins']}\\]")
    return " → ".join(parts)


def _bonus_board_block(s1: str, s2: str, s3: str, level: int) -> str:
    label = {1: "🥉 Bronze", 2: "🥈 Silver", 3: "🥇 Gold"}[level]
    return f"_{label}_\n{_slot_board(s1, s2, s3)}"


def _bonus_outcome_text(kind: str, base_mult: int, bm: int, disp_sym: str,
                        bet: int, spin_won: int, scatter_hit: bool, wild_hit: bool,
                        level: int) -> str:
    lines = []
    if kind == "miss":
        lines += ["╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌", "💀  *М И М О*", "_Ставка сгорела_", "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌"]
    elif kind == "double":
        lines += [
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🔄  *П А Р А*  {disp_sym}{disp_sym}",
            f"_Ставка возвращается: +{_fmt(bet)} 💰_",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]
    else:
        total_mult = base_mult * bm
        is_jackpot = (level == 3 and disp_sym == "⭐")
        syms       = f"{disp_sym}{disp_sym}{disp_sym}"
        if is_jackpot:
            lines += [
                "⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡",
                "⚡  *ГРАНД-ДЖЕКПОТ!*  ⚡",
                f"⭐⭐⭐ — ×{base_mult} × ×{bm} = *×{total_mult}*",
                f"*Выплата: {_fmt(spin_won)} 💰*",
                "⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡",
            ]
        elif base_mult >= 75:
            lines += [
                "💥💥💥💥💥💥💥💥💥💥💥💥",
                "💥  *М Е Г А - Т Р О Й К А!*",
                f"{syms} — ×{base_mult} × ×{bm} = *×{total_mult}*",
                f"*Выплата: {_fmt(spin_won)} 💰*",
                "💥💥💥💥💥💥💥💥💥💥💥💥",
            ]
        else:
            lines += [
                "══════════════════════",
                f"✨  *Т Р О Й К А!*  {syms}",
                f"×{base_mult} × ×{bm} = *×{total_mult}*",
                f"*Выплата: {_fmt(spin_won)} 💰*",
                "══════════════════════",
            ]
    if wild_hit and not scatter_hit:
        lines.append("🌟 _Wild сработал — помог тройке!_")
    if scatter_hit:
        lines.append("🔥 _Scatter — выплата + апгрейд!_")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# Blackjack constants
# ═════════════════════════════════════════════════════════════════════════════

_BJ_RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
_BJ_SUITS = ['♠', '♥', '♦', '♣']
_BJ_BETS  = [50, 100, 250, 500, 1_000, 2_500]


def _bj_card_val(rank: str) -> int:
    if rank in ('J', 'Q', 'K'): return 10
    if rank == 'A':              return 11
    return int(rank)


def _bj_hand_val(hand: list) -> int:
    total = sum(_bj_card_val(c[0]) for c in hand)
    aces  = sum(1 for c in hand if c[0] == 'A')
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total


def _bj_card(card: list | tuple) -> str:
    return f"{card[0]}{card[1]}"


def _bj_hand_str(hand: list, hide_last: bool = False) -> str:
    if hide_last and len(hand) >= 2:
        return f"{_bj_card(hand[0])} 🂠"
    return "  ".join(_bj_card(c) for c in hand)


def _bj_make_deck() -> list:
    """6 колод, перемешанные."""
    deck = [[r, s] for r in _BJ_RANKS for s in _BJ_SUITS] * 6
    random.shuffle(deck)
    return deck


def _bj_deal_hand(deck: list) -> tuple[list, list]:
    """Раздаёт 2 карты."""
    d    = list(deck)
    hand = [d.pop(), d.pop()]
    return hand, d


def _bj_deal_one(deck: list) -> tuple[list, list]:
    d    = list(deck)
    card = d.pop()
    return card, d


def _bj_status(hand: list) -> str:
    v = _bj_hand_val(hand)
    if v > 21:                                       return "bust"
    if v == 21 and len(hand) == 2:                   return "blackjack"
    return "ok"


def _bj_board(player: list, dealer: list, hide_dealer: bool = True) -> str:
    pv    = _bj_hand_val(player)
    dv    = _bj_hand_val(dealer) if not hide_dealer else "?"
    p_str = _bj_hand_str(player)
    d_str = _bj_hand_str(dealer, hide_last=hide_dealer)
    return (
        f"🃏 *Дилер:* `{d_str}`   _{'?' if hide_dealer else str(dv)}_\n"
        f"👤 *Вы:*    `{p_str}`   _{pv}_"
    )


def _bj_get_state(uid: int) -> dict | None:
    pa = db.get_pending_action(uid)
    if pa and pa.get("action") == "bj_solo":
        return pa["data"]
    return None


# ═════════════════════════════════════════════════════════════════════════════
# Global roulette constants
# ═════════════════════════════════════════════════════════════════════════════

_GLOBAL_OUTCOMES = [
    # (вес, код, emoji, заголовок, описание)
    (35, "burn",      "💀", "КОТЁЛ СГОРЕЛ",  "Все ставки потеряны"),
    (20, "jackpot",   "🏆", "ДЖЕКПОТ",       "Один игрок забирает весь банк"),
    (20, "split",     "💰", "ДЕЛЕЖ",         "Банк делится поровну"),
    (15, "x2",        "💥", "КОТЁЛ УДВОЕН",  "Банк ×2, делится поровну"),
    (7,  "carryover", "🔄", "КОТЁЛ РАСТЁТ",  "Банк переходит в следующий раунд"),
    (3,  "x5",        "🌟", "МЕГА КОТЁЛ ×5", "Банк ×5, делится поровну"),
]

_GLOBAL_BETS = [100, 250, 500, 1_000, 2_500]


# ═════════════════════════════════════════════════════════════════════════════
# Casino Menu
# ═════════════════════════════════════════════════════════════════════════════

async def cb_casino_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)
    state = db.get_global_roulette_state()
    pot   = state.get("pot", 0)

    text = (
        "🎰 *КАЗИНО*\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n"
        f"🌍 Глобальный котёл: *{_fmt(pot)}* монет\n\n"
        "🎡 *Рулетка* — крути колесо, выиграй до ×25\n"
        "🎰 *Слоты* — три символа, джекпот ×150\n"
        "🃏 *Блэкджек* — набери 21, бей дилера\n"
        "🌍 *Глоб. рулетка* — общий котёл, большие призы"
    )
    rows = [
        [InlineKeyboardButton("🎡 Рулетка",        callback_data="casino_roulette"),
         InlineKeyboardButton("🎰 Слоты",           callback_data="casino_slots")],
        [InlineKeyboardButton("🃏 Блэкджек",        callback_data="casino_bj"),
         InlineKeyboardButton("🌍 Глоб. рулетка",  callback_data="casino_global")],
        [InlineKeyboardButton("◀ В меню",           callback_data="menu_back")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))


# ═════════════════════════════════════════════════════════════════════════════
# Roulette handlers
# ═════════════════════════════════════════════════════════════════════════════

async def cb_casino_roulette(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)

    rows = []
    for i in range(0, len(_ROULETTE_BETS), 2):
        pair = _ROULETTE_BETS[i:i + 2]
        row  = []
        for amt in pair:
            can = coins >= amt
            row.append(InlineKeyboardButton(
                f"{'🪙' if can else '🚫'} {_fmt(amt)}",
                callback_data=f"casino_spin_{amt}" if can else "casino_no_coins",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀ Назад", callback_data="casino_menu")])

    await q.edit_message_text(
        f"🎡 *РУЛЕТКА*\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n\n"
        f"{_WHEEL_DISPLAY}\n\n"
        "Выбери ставку — и крути!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_casino_no_coins(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("Недостаточно монет для этой ставки!", show_alert=True)


async def cb_casino_spin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id
    try:
        bet = int(q.data[len("casino_spin_"):])
    except ValueError:
        await q.answer("Ошибка ставки.", show_alert=True); return

    ok, _ = db.spend_coins(uid, bet)
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return
    await q.answer()

    retry_btn = InlineKeyboardButton("🎡 Крутить ещё", callback_data="casino_roulette")
    back_btn  = InlineKeyboardButton("◀ Казино",       callback_data="casino_menu")

    try:
        for frame in _SPIN_FRAMES:
            await q.edit_message_text(
                f"🎰 *Колесо крутится...*\n\n{frame}\n\n_Ставка: {_fmt(bet)} 💰_",
                parse_mode="Markdown",
            )
            await asyncio.sleep(0.7)

        result   = _spin_roulette()
        mult     = result["mult"]
        emoji    = result["emoji"]
        label    = result["label"]
        is_doom  = result["is_doom"]
        is_bonus = result["is_bonus"]

        if mult == 0:
            new_bal = db.get_coins(uid)
            text = (
                f"💀 *ПУСТО*\n\nВыпало: {emoji} *{label}*\n\n"
                f"Ставка *{_fmt(bet)} 💰* — потеряна.\n\n"
                f"💼 Баланс: *{_fmt(new_bal)} 💰*"
            )

        elif is_doom:
            _, new_bal = db.spend_coins(uid, bet)  # вторая ставка (floor=0 если мало)
            text = (
                f"💣 *СЛИВ!*\n\nВыпало: {emoji} *{label}*\n\n"
                f"Штраф ×2 — ещё *{_fmt(bet)} 💰* сгорело!\n\n"
                f"💼 Баланс: *{_fmt(new_bal)} 💰*"
            )

        elif is_bonus:
            bonus   = bet * 3
            new_bal = db.add_coins(uid, bonus)
            text = (
                f"🎁 *БОНУС ×3!*\n\nВыпало: {emoji} *{label}*\n\n"
                f"Выигрыш: *+{_fmt(bonus)} 💰*\n\n"
                f"💼 Баланс: *{_fmt(new_bal)} 💰*"
            )

        else:
            winnings = bet * mult
            net_gain = winnings - bet
            new_bal  = db.add_coins(uid, winnings)
            if mult == 1:
                text = (
                    f"🔄 *ВОЗВРАТ*\n\nВыпало: {emoji} *{label}*\n\n"
                    f"Ставка *{_fmt(bet)} 💰* возвращена.\n\n"
                    f"💼 Баланс: *{_fmt(new_bal)} 💰*"
                )
            else:
                hdr = (
                    f"⚡ *МЕГА-ВЫИГРЫШ {label}!*"     if mult >= 25 else
                    f"💥 *ОГРОМНЫЙ ВЫИГРЫШ {label}!*" if mult >= 10 else
                    f"🏆 *ВЫИГРЫШ {emoji} {label}!*"
                )
                text = (
                    f"{hdr}\n\nВыпало: {emoji} *{label}*\n\n"
                    f"Ставка: *{_fmt(bet)} 💰*\n"
                    f"Выплата: *{_fmt(winnings)} 💰*\n"
                    f"Чистый выигрыш: *+{_fmt(net_gain)} 💰*\n\n"
                    f"💼 Баланс: *{_fmt(new_bal)} 💰*"
                )

        await q.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[retry_btn, back_btn]]),
        )

    except Exception as exc:
        logger.exception("roulette_spin crash uid=%s bet=%s: %s", uid, bet, exc)
        try:
            rb = db.add_coins(uid, bet)
            await q.edit_message_text(
                f"❌ *Что-то пошло не так*\n\nСтавка *{_fmt(bet)} 💰* возвращена.\n\n"
                f"💼 Баланс: *{_fmt(rb)} 💰*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[retry_btn, back_btn]]),
            )
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
# Slots handlers
# ═════════════════════════════════════════════════════════════════════════════

async def cb_casino_slots(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)

    rows = []
    for i in range(0, len(_ROULETTE_BETS), 2):
        pair = _ROULETTE_BETS[i:i + 2]
        row  = []
        for amt in pair:
            can = coins >= amt
            row.append(InlineKeyboardButton(
                f"{'🪙' if can else '🚫'} {_fmt(amt)}",
                callback_data=f"casino_slotspin_{amt}" if can else "casino_no_coins",
            ))
        rows.append(row)

    for amt in _ROULETTE_BETS:
        cost = amt * _SLOT_BONUS_COST
        can  = coins >= cost
        rows.append([InlineKeyboardButton(
            f"{'🌟' if can else '🚫'} Бонус (ставка {_fmt(amt)}, цена {_fmt(cost)})",
            callback_data=f"casino_bonusbuy_{amt}" if can else "casino_no_coins",
        )])

    rows.append([InlineKeyboardButton("◀ Назад", callback_data="casino_menu")])

    await q.edit_message_text(
        f"🎰 *СЛОТ-МАШИНА*\n\n💰 Баланс: *{_fmt(coins)}* монет\n\n"
        f"{_SLOT_LEGEND}\n\nВыбери ставку:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_casino_slots_spin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id
    try:
        bet = int(q.data[len("casino_slotspin_"):])
    except ValueError:
        await q.answer("Ошибка ставки.", show_alert=True); return

    ok, _ = db.spend_coins(uid, bet)
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return
    await q.answer()

    back_btn   = InlineKeyboardButton("◀ Казино",         callback_data="casino_menu")
    retry_btn  = InlineKeyboardButton(f"🎰 ×{_fmt(bet)} снова", callback_data=f"casino_slotspin_{bet}")
    change_btn = InlineKeyboardButton("🔄 Другая ставка",  callback_data="casino_slots")

    try:
        s1, s2, s3 = _spin_slot_reels()
        spin = _SLOT_SPIN_SYM

        for f1, f2, f3 in [(spin, spin, spin), (s1, spin, spin), (s1, s2, spin)]:
            await q.edit_message_text(
                f"🎰 *СЛОТЫ*\n\n{_slot_board(f1, f2, f3)}\n\n_Ставка: {_fmt(bet)} 💰_",
                parse_mode="Markdown",
            )
            await asyncio.sleep(0.45)

        kind, mult = _eval_slots(s1, s2, s3)
        if kind == "miss":
            new_bal = db.get_coins(uid)
        elif kind == "double":
            new_bal = db.add_coins(uid, bet)
        else:
            new_bal = db.add_coins(uid, bet * mult)

        text = _slot_result_text(kind, mult, s1, s2, s3, bet, new_bal)

        bonus_triggered = random.random() < _SLOT_BONUS_CHANCE
        if bonus_triggered:
            lvl1 = _BONUS_LEVELS[1]
            text += (
                f"\n\n{'━' * 22}\n"
                f"🔥🔥 *Б О Н У С - И Г Р А!* 🔥🔥\n"
                f"🥉\\[○○○\\] → 🥈\\[○○○\\] → 🥇\\[○○○\\]\n"
                f"_Wild🌟 заменяет символы_\n"
                f"_Scatter🔥 = апгрейд на след. уровень_\n"
                f"{'━' * 22}"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"🥉 Начать! Ур.1 ({lvl1['spins']} спина × ×{lvl1['mult']})",
                    callback_data=f"casino_bonusspin_{bet}_{lvl1['spins']}_0_1",
                ),
            ], [back_btn]])
        else:
            kb = InlineKeyboardMarkup([[retry_btn, change_btn], [back_btn]])

        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    except Exception as exc:
        logger.exception("slots_spin crash uid=%s bet=%s: %s", uid, bet, exc)
        try:
            rb = db.add_coins(uid, bet)
            await q.edit_message_text(
                f"❌ *Ошибка* — ставка возвращена.\n\n💼 Баланс: *{_fmt(rb)} 💰*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[retry_btn, change_btn], [back_btn]]),
            )
        except Exception:
            pass


async def cb_casino_bonus_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id
    try:
        bet = int(q.data[len("casino_bonusbuy_"):])
    except ValueError:
        await q.answer("Ошибка.", show_alert=True); return

    cost = bet * _SLOT_BONUS_COST
    ok, _ = db.spend_coins(uid, cost)
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return
    await q.answer("🌟 Бонус-игра активирована!")

    lvl1 = _BONUS_LEVELS[1]
    lvl2 = _BONUS_LEVELS[2]
    lvl3 = _BONUS_LEVELS[3]
    back_btn = InlineKeyboardButton("◀ Казино", callback_data="casino_menu")
    await q.edit_message_text(
        f"🔥 *БОНУС-ИГРА* 🔥\n"
        f"_Потрачено: {_fmt(cost)} 💰 | Ставка: {_fmt(bet)} 💰/спин_\n\n"
        f"🥉 Уровень 1 — {lvl1['spins']} спина, ×{lvl1['mult']}\n"
        f"🥈 Уровень 2 — {lvl2['spins']} спина, ×{lvl2['mult']} + 🔥 Scatter\n"
        f"🥇 Финал — {lvl3['spins']} спина, ×{lvl3['mult']} + 🔥 Scatter\n"
        f"⚡ Гранд-Джекпот: ⭐⭐⭐\n\n"
        f"🌟 Wild — заменяет любой символ\n"
        f"🔥 Scatter — мгновенный апгрейд уровня",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"🥉 Начать! Ур.1 ({lvl1['spins']} спина × ×{lvl1['mult']})",
                callback_data=f"casino_bonusspin_{bet}_{lvl1['spins']}_0_1",
            ),
        ], [back_btn]]),
    )


async def cb_casino_bonus_spin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """casino_bonusspin_<bet>_<remaining>_<total_won>_<level>"""
    q   = update.callback_query
    uid = q.from_user.id

    try:
        parts     = q.data.split("_")  # ["casino","bonusspin",bet,remaining,won,level]
        bet       = int(parts[2])
        remaining = int(parts[3])
        total_won = int(parts[4])
        level     = int(parts[5])
    except (IndexError, ValueError):
        await q.answer("Бонус-игра не активна.", show_alert=True); return

    if remaining <= 0:
        await q.answer("Бонус-игра завершена.", show_alert=True); return

    await q.answer()

    cfg      = _BONUS_LEVELS.get(level, _BONUS_LEVELS[1])
    bm       = cfg["mult"]
    spin_num = cfg["spins"] - remaining + 1
    spin     = _SLOT_SPIN_SYM
    back_btn = InlineKeyboardButton("◀ Казино", callback_data="casino_menu")
    anim_sym = {1: "✨", 2: "💫", 3: "⭐"}[level]

    try:
        for f1, f2, f3 in [(spin, spin, spin), (anim_sym, spin, spin), (anim_sym, anim_sym, spin)]:
            await q.edit_message_text(
                f"{cfg['name']}\n"
                f"_Спин {spin_num}/{cfg['spins']} | ×{bm} к выигрышу_\n\n"
                f"{_bonus_board_block(f1, f2, f3, level)}",
                parse_mode="Markdown",
            )
            await asyncio.sleep(0.4)

        s1, s2, s3 = _spin_bonus_reels(level)
        kind, base_mult, scatter_hit, disp_sym = _eval_bonus_spin(s1, s2, s3)
        wild_hit = _BONUS_WILD in [s1, s2, s3]

        if kind == "miss":
            spin_won = 0
        elif kind == "double":
            spin_won = bet
            db.add_coins(uid, spin_won)
        else:
            spin_won = bet * base_mult * bm
            db.add_coins(uid, spin_won)

        total_won  += spin_won
        remaining  -= 1
        new_balance = db.get_coins(uid)

        prog    = _bonus_progress_bar(level, spin_num, remaining)
        board   = _bonus_board_block(s1, s2, s3, level)
        outcome = _bonus_outcome_text(kind, base_mult, bm, disp_sym, bet, spin_won, scatter_hit, wild_hit, level)
        footer  = (
            f"\n💼 Баланс: *{_fmt(new_balance)} 💰*\n"
            f"_+{_fmt(spin_won)} 💰 этот спин  |  Итого бонус: +{_fmt(total_won)} 💰_"
        )
        text = f"{cfg['name']}\n{prog}\n\n{board}\n\n{outcome}{footer}"

        if scatter_hit and level < 3:
            next_lvl = level + 1
            next_cfg = _BONUS_LEVELS[next_lvl]
            next_ico = next_cfg["name"].split()[0]
            next_cd  = f"casino_bonusspin_{bet}_{next_cfg['spins']}_{total_won}_{next_lvl}"
            text += (
                f"\n\n{'━' * 22}\n"
                f"🔥🔥 *А П Г Р Е Й Д !* 🔥🔥\n"
                f"{cfg['name'].split()[0]} → {next_cfg['name']}\n"
                f"Множитель: ×{bm} → *×{next_cfg['mult']}*\n"
                f"{'━' * 22}"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"{next_ico} На уровень {next_lvl}! ({next_cfg['spins']} спина × ×{next_cfg['mult']})",
                    callback_data=next_cd,
                ),
            ], [back_btn]])

        elif remaining > 0:
            next_cd  = f"casino_bonusspin_{bet}_{remaining}_{total_won}_{level}"
            next_num = spin_num + 1
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"{cfg['name'].split()[0]} Спин {next_num}/{cfg['spins']}  →",
                    callback_data=next_cd,
                ),
            ], [back_btn]])

        else:
            if level == 3:
                all_done = "🥉✅ → 🥈✅ → 🥇✅"
                text = (
                    f"🏆 *ГРАНД-ФИНАЛ ЗАВЕРШЁН!* 🏆\n\n"
                    f"{all_done}\n\n"
                    f"💰 *Итого бонус: {_fmt(total_won)} монет*\n\n"
                    f"💼 Баланс: *{_fmt(new_balance)} 💰*"
                )
            else:
                completed = " → ".join(
                    f"{_BONUS_LEVELS[l]['name'].split()[0]}✅" if l <= level
                    else f"{_BONUS_LEVELS[l]['name'].split()[0]}✗"
                    for l in [1, 2, 3]
                )
                text += f"\n\n🏁 *Бонус завершён*\n{completed}\nОбщий выигрыш: *+{_fmt(total_won)} 💰*"

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎰 Ещё раз", callback_data="casino_slots"),
                back_btn,
            ]])

        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    except Exception as exc:
        logger.exception("bonus_spin crash uid=%s level=%s: %s", uid, level, exc)
        try:
            await q.edit_message_text(
                "❌ *Ошибка в бонус-игре.* Прогресс сохранён в балансе.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[back_btn]]),
            )
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
# Blackjack handlers
# ═════════════════════════════════════════════════════════════════════════════

async def cb_casino_bj(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Mode selection: Solo vs PvP."""
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)

    await q.edit_message_text(
        "🃏 *БЛЭКДЖЕК*\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n\n"
        "Выбери режим:\n\n"
        "🤖 *Соло* — против дилера\n"
        "  Блэкджек → ×2.5  |  Победа → ×2  |  Дабл-даун\n\n"
        "🤝 *ПвП* — против другого игрока\n"
        "  Победа → ×2  |  Ничья → ставка назад",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Соло (vs дилер)", callback_data="casino_bj_solo")],
            [InlineKeyboardButton("🤝 ПвП Блэкджек",   callback_data="casino_bj_pvp")],
            [InlineKeyboardButton("◀ Назад",             callback_data="casino_menu")],
        ]),
    )


async def cb_casino_bj_solo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Solo blackjack — bet selection."""
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)

    rows = []
    for i in range(0, len(_BJ_BETS), 2):
        pair = _BJ_BETS[i:i + 2]
        row  = []
        for amt in pair:
            can = coins >= amt
            row.append(InlineKeyboardButton(
                f"{'🪙' if can else '🚫'} {_fmt(amt)}",
                callback_data=f"casino_bjbet_{amt}" if can else "casino_no_coins",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀ Назад", callback_data="casino_bj")])

    await q.edit_message_text(
        "🃏 *БЛЭКДЖЕК — Соло*\n\n"
        "Набери 21 или ближе к нему, чем дилер.\n"
        "• Блэкджек (туз + 10) → ×2.5\n"
        "• Победа → ×2\n"
        "• Ничья → ставка возвращается\n"
        "• Дабл-даун: ×2 ставка, одна карта\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n\nВыбери ставку:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_casino_bj_bet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id
    try:
        bet = int(q.data[len("casino_bjbet_"):])
    except ValueError:
        await q.answer("Ошибка ставки.", show_alert=True); return

    # Не позволяем начинать блэкджек в середине игры
    pa = db.get_pending_action(uid)
    if pa and pa.get("action") in ("in_game", "my_turn", "solo_game"):
        await q.answer("Ты сейчас в игре! Сначала заверши её.", show_alert=True); return

    ok, _ = db.spend_coins(uid, bet)
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return
    await q.answer()

    deck         = _bj_make_deck()
    player, deck = _bj_deal_hand(deck)
    dealer, deck = _bj_deal_hand(deck)

    db.set_pending_action(uid, "bj_solo", {"player": player, "dealer": dealer, "deck": deck, "bet": bet})

    back_btn = InlineKeyboardButton("◀ Казино", callback_data="casino_menu")
    pstatus  = _bj_status(player)

    if pstatus == "blackjack":
        dstatus = _bj_status(dealer)
        if dstatus == "blackjack":
            payout = bet
            result = "🤝 *НИЧЬЯ — оба блэкджека!*"
        else:
            payout = int(bet * 2.5)
            result = "♠ *БЛЭКДЖЕК! Выигрыш ×2.5!*"
        new_bal = db.add_coins(uid, payout)
        db.clear_pending_action(uid)
        await q.edit_message_text(
            f"🃏 *БЛЭКДЖЕК*\n\n{_bj_board(player, dealer, hide_dealer=False)}\n\n"
            f"{result}\nСтавка: *{_fmt(bet)} 💰*  →  Выплата: *{_fmt(payout)} 💰*\n\n"
            f"💼 Баланс: *{_fmt(new_bal)} 💰*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🃏 Ещё раз", callback_data="casino_bj"),
                back_btn,
            ]]),
        )
        return

    await q.edit_message_text(
        f"🃏 *БЛЭКДЖЕК*\n\n{_bj_board(player, dealer)}\n\nСтавка: *{_fmt(bet)} 💰*\n\nТвой ход:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👆 Ещё",  callback_data="casino_bjhit"),
             InlineKeyboardButton("✋ Стоп", callback_data="casino_bjstand")],
            [InlineKeyboardButton("💰 Дабл", callback_data="casino_bjdouble")],
            [back_btn],
        ]),
    )


async def _bj_finish(q, uid: int, player: list, dealer: list, bet: int) -> None:
    """Дилер добирает карты, считаем результат."""
    d = list(dealer)
    while _bj_hand_val(d) < 17:
        d.append([random.choice(_BJ_RANKS), random.choice(_BJ_SUITS)])

    pv = _bj_hand_val(player)
    dv = _bj_hand_val(d)
    ps = _bj_status(player)
    ds = _bj_status(d)

    if ps == "bust":
        payout = 0
        result = "💥 *ВЫ ПЕРЕБРАЛИ! Проигрыш.*"
    elif ds == "bust":
        payout = bet * 2
        result = "🏆 *Дилер перебрал! Выигрыш!*"
    elif pv > dv:
        payout = bet * 2
        result = f"🏆 *Победа! {pv} против {dv}*"
    elif pv == dv:
        payout = bet
        result = f"🤝 *Ничья! {pv} = {dv}*"
    else:
        payout = 0
        result = f"😞 *Проигрыш. {pv} против {dv}*"

    new_bal = db.add_coins(uid, payout)
    db.clear_pending_action(uid)

    back_btn = InlineKeyboardButton("◀ Казино", callback_data="casino_menu")
    net      = payout - bet
    net_str  = f"+{_fmt(net)}" if net >= 0 else _fmt(net)
    await q.edit_message_text(
        f"🃏 *БЛЭКДЖЕК*\n\n{_bj_board(player, d, hide_dealer=False)}\n\n"
        f"{result}\nСтавка: *{_fmt(bet)} 💰*  |  Изменение: *{net_str} 💰*\n\n"
        f"💼 Баланс: *{_fmt(new_bal)} 💰*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🃏 Ещё раз", callback_data="casino_bj"),
            back_btn,
        ]]),
    )


async def cb_casino_bj_hit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q     = update.callback_query
    uid   = q.from_user.id
    state = _bj_get_state(uid)
    if not state:
        await q.answer("Игра не найдена.", show_alert=True); return
    await q.answer()

    player = state["player"]
    dealer = state["dealer"]
    deck   = state["deck"]
    bet    = state["bet"]

    card, deck = _bj_deal_one(deck)
    player.append(card)

    if _bj_status(player) == "bust":
        db.clear_pending_action(uid)
        new_bal  = db.get_coins(uid)
        back_btn = InlineKeyboardButton("◀ Казино", callback_data="casino_menu")
        await q.edit_message_text(
            f"🃏 *БЛЭКДЖЕК*\n\n{_bj_board(player, dealer, hide_dealer=False)}\n\n"
            f"💥 *ПЕРЕБОР! {_bj_hand_val(player)} > 21*\n"
            f"Ставка *{_fmt(bet)} 💰* — потеряна.\n\n"
            f"💼 Баланс: *{_fmt(new_bal)} 💰*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🃏 Ещё раз", callback_data="casino_bj"),
                back_btn,
            ]]),
        )
        return

    state["player"] = player
    state["deck"]   = deck
    db.set_pending_action(uid, "bj_solo", state)

    back_btn = InlineKeyboardButton("◀ Казино", callback_data="casino_menu")
    await q.edit_message_text(
        f"🃏 *БЛЭКДЖЕК*\n\n{_bj_board(player, dealer)}\n\nСтавка: *{_fmt(bet)} 💰*\n\nТвой ход:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👆 Ещё",  callback_data="casino_bjhit"),
             InlineKeyboardButton("✋ Стоп", callback_data="casino_bjstand")],
            [back_btn],
        ]),
    )


async def cb_casino_bj_stand(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q     = update.callback_query
    uid   = q.from_user.id
    state = _bj_get_state(uid)
    if not state:
        await q.answer("Игра не найдена.", show_alert=True); return
    await q.answer()
    await _bj_finish(q, uid, state["player"], state["dealer"], state["bet"])


async def cb_casino_bj_double(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q     = update.callback_query
    uid   = q.from_user.id
    state = _bj_get_state(uid)
    if not state:
        await q.answer("Игра не найдена.", show_alert=True); return

    bet    = state["bet"]
    player = state["player"]
    dealer = state["dealer"]
    deck   = state["deck"]

    ok, _ = db.spend_coins(uid, bet)
    if not ok:
        await q.answer("Недостаточно монет для дабла!", show_alert=True); return
    await q.answer("💰 Дабл-даун!")

    card, deck = _bj_deal_one(deck)
    player.append(card)
    new_bet = bet * 2
    state.update({"bet": new_bet, "player": player, "deck": deck})
    db.set_pending_action(uid, "bj_solo", state)
    await _bj_finish(q, uid, player, dealer, new_bet)


# ═════════════════════════════════════════════════════════════════════════════
# Blackjack PvP handlers
# ═════════════════════════════════════════════════════════════════════════════

def _bj_pvp_board(my_hand: list, opp_name: str, bet: int) -> str:
    mv = _bj_hand_val(my_hand)
    return (
        f"👤 *Твои карты:* `{_bj_hand_str(my_hand)}`   _{mv}_\n"
        f"🤝 *Соперник ({opp_name}):* карты скрыты\n\n"
        f"Ставка: *{_fmt(bet)} 💰*"
    )


def _bj_pvp_get_state(uid: int) -> tuple[str | None, dict | None, int | None]:
    """Returns (action, data, opponent_id) for a PvP BJ player, or (None, None, None)."""
    pa = db.get_pending_action(uid)
    if not pa:
        return None, None, None
    action = pa.get("action")
    if action == "bj_pvp_host":
        return action, pa["data"], pa["data"].get("guest_id")
    if action == "bj_pvp_guest":
        return action, pa["data"], pa["data"].get("host_id")
    return None, None, None


async def _bj_pvp_check_finish(ctx: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    """If both players are done, resolve the game."""
    action, data, opp_id = _bj_pvp_get_state(uid)
    if not action or not opp_id:
        return

    is_host  = action == "bj_pvp_host"
    host_id  = uid    if is_host else opp_id
    guest_id = opp_id if is_host else uid

    host_pa  = db.get_pending_action(host_id)
    guest_pa = db.get_pending_action(guest_id)
    if not host_pa or not guest_pa:
        return  # already resolved

    if host_pa["data"].get("done") and guest_pa["data"].get("done"):
        await _bj_pvp_finish(ctx, host_id, host_pa["data"], guest_id, guest_pa["data"])


async def _bj_pvp_finish(
    ctx: ContextTypes.DEFAULT_TYPE,
    host_id: int, host_data: dict,
    guest_id: int, guest_data: dict,
) -> None:
    """Compare hands, distribute coins, notify both players."""
    bet        = host_data["bet"]
    host_hand  = host_data["hand"]
    guest_hand = guest_data["hand"]

    hv = _bj_hand_val(host_hand)
    gv = _bj_hand_val(guest_hand)
    host_bust  = hv > 21
    guest_bust = gv > 21

    if host_bust and guest_bust:
        host_payout = 0;       guest_payout = 0
        result_h = "💥 Оба перебрали — ставки потеряны"
        result_g = "💥 Оба перебрали — ставки потеряны"
    elif host_bust:
        host_payout = 0;       guest_payout = bet * 2
        result_h = f"💥 Перебор ({hv}) — проигрыш"
        result_g = f"🏆 Победа! Соперник перебрал ({hv})"
    elif guest_bust:
        host_payout = bet * 2; guest_payout = 0
        result_h = f"🏆 Победа! Соперник перебрал ({gv})"
        result_g = f"💥 Перебор ({gv}) — проигрыш"
    elif hv > gv:
        host_payout = bet * 2; guest_payout = 0
        result_h = f"🏆 Победа! {hv} против {gv}"
        result_g = f"😞 Проигрыш. {gv} против {hv}"
    elif gv > hv:
        host_payout = 0;       guest_payout = bet * 2
        result_h = f"😞 Проигрыш. {hv} против {gv}"
        result_g = f"🏆 Победа! {gv} против {hv}"
    else:
        host_payout = bet;     guest_payout = bet
        result_h = f"🤝 Ничья! {hv} = {gv}"
        result_g = f"🤝 Ничья! {gv} = {hv}"

    host_bal  = db.add_coins(host_id,  host_payout)
    guest_bal = db.add_coins(guest_id, guest_payout)
    db.clear_pending_action(host_id)
    db.clear_pending_action(guest_id)

    host_user  = db.get_user(host_id)
    guest_user = db.get_user(guest_id)
    host_name  = host_user.get("display_name", "???") if host_user else "???"
    guest_name = guest_user.get("display_name", "???") if guest_user else "???"

    replay_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🃏 Играть снова", callback_data="casino_bj"),
        InlineKeyboardButton("◀ Казино",        callback_data="casino_menu"),
    ]])

    for uid, my_hand, my_val, opp_hand, opp_val, opp_name, payout, result, bal in [
        (host_id,  host_hand,  hv, guest_hand, gv, guest_name, host_payout,  result_h, host_bal),
        (guest_id, guest_hand, gv, host_hand,  hv, host_name,  guest_payout, result_g, guest_bal),
    ]:
        net     = payout - bet
        net_str = f"+{_fmt(net)}" if net >= 0 else _fmt(net)
        try:
            await ctx.bot.send_message(
                uid,
                f"🃏 *БЛЭКДЖЕК ПвП — Финал*\n\n"
                f"👤 *Твои карты:* `{_bj_hand_str(my_hand)}`   _{my_val}_\n"
                f"🤝 *{opp_name}:* `{_bj_hand_str(opp_hand)}`   _{opp_val}_\n\n"
                f"{result}\n"
                f"Ставка: *{_fmt(bet)} 💰*  |  Изменение: *{net_str} 💰*\n\n"
                f"💼 Баланс: *{_fmt(bal)} 💰*",
                parse_mode="Markdown",
                reply_markup=replay_kb,
            )
        except Exception:
            pass


async def cb_casino_bj_pvp(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """PvP lobby browser."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    lobbies = db.get_pvp_bj_lobbies(exclude_uid=uid)
    coins   = db.get_coins(uid)

    rows = []
    for lobby in lobbies[:5]:
        host_uid  = lobby["user_id"]
        bet       = lobby["data"]["bet"]
        host_user = db.get_user(host_uid)
        host_name = host_user.get("display_name", "???") if host_user else "???"
        can_join  = coins >= bet
        rows.append([InlineKeyboardButton(
            f"{'⚔️' if can_join else '🚫'} {host_name}  —  {_fmt(bet)} 💰",
            callback_data=f"casino_bjpvp_join_{host_uid}" if can_join else "casino_no_coins",
        )])

    lobby_hdr = f"Открытых лобби: *{len(lobbies)}*" if lobbies else "_Нет открытых лобби_"

    rows.append([InlineKeyboardButton("➕ Создать лобби", callback_data="casino_bjpvp_create")])
    rows.append([InlineKeyboardButton("◀ Назад",          callback_data="casino_bj")])

    await q.edit_message_text(
        f"🃏 *БЛЭКДЖЕК ПвП*\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n\n"
        f"{lobby_hdr}\n\n"
        "Присоединись к лобби или создай своё:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_casino_bjpvp_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Bet selection for creating a PvP lobby."""
    q     = update.callback_query
    await q.answer()
    uid   = q.from_user.id
    coins = db.get_coins(uid)

    rows = []
    for i in range(0, len(_BJ_BETS), 2):
        pair = _BJ_BETS[i:i + 2]
        row  = []
        for amt in pair:
            can = coins >= amt
            row.append(InlineKeyboardButton(
                f"{'🪙' if can else '🚫'} {_fmt(amt)}",
                callback_data=f"casino_bjpvp_bet_{amt}" if can else "casino_no_coins",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀ Назад", callback_data="casino_bj_pvp")])

    await q.edit_message_text(
        "🃏 *СОЗДАТЬ ПвП ЛОББИ*\n\n"
        "Выбери ставку — соперник поставит столько же.\n"
        "• Победа → ×2 ставки\n"
        "• Ничья → ставка назад\n"
        "• Оба перебрали → обе ставки сгорают\n\n"
        f"💰 Баланс: *{_fmt(coins)}* монет\n\nВыбери ставку:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_casino_bjpvp_bet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Create PvP lobby: spend coins, save waiting state."""
    q   = update.callback_query
    uid = q.from_user.id
    try:
        bet = int(q.data[len("casino_bjpvp_bet_"):])
    except ValueError:
        await q.answer("Ошибка ставки.", show_alert=True); return

    pa = db.get_pending_action(uid)
    if pa and pa.get("action") in ("in_game", "my_turn", "solo_game", "bj_solo", "bj_pvp_host", "bj_pvp_guest"):
        await q.answer("Ты уже в игре!", show_alert=True); return

    ok, _ = db.spend_coins(uid, bet)
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return
    await q.answer()

    db.set_pending_action(uid, "bj_pvp_host", {
        "bet":      bet,
        "status":   "waiting",
        "hand":     None,
        "deck":     None,
        "done":     False,
        "guest_id": None,
    })

    await q.edit_message_text(
        f"🃏 *БЛЭКДЖЕК ПвП*\n\n"
        f"⏳ *Ожидание соперника...*\n\n"
        f"Ставка: *{_fmt(bet)} 💰*\n\n"
        "_Как только кто-то присоединится, тебе придёт сообщение._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data="casino_bjpvp_cancel"),
        ]]),
    )


async def cb_casino_bjpvp_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Guest joins a PvP lobby, deals hands, starts game."""
    q   = update.callback_query
    uid = q.from_user.id
    try:
        host_id = int(q.data[len("casino_bjpvp_join_"):])
    except ValueError:
        await q.answer("Ошибка.", show_alert=True); return

    if host_id == uid:
        await q.answer("Нельзя играть с собой!", show_alert=True); return

    my_pa = db.get_pending_action(uid)
    if my_pa and my_pa.get("action") in ("in_game", "my_turn", "solo_game", "bj_solo", "bj_pvp_host", "bj_pvp_guest"):
        await q.answer("Ты уже в игре!", show_alert=True); return

    host_pa = db.get_pending_action(host_id)
    if not host_pa or host_pa.get("action") != "bj_pvp_host":
        await q.answer("Лобби уже не существует.", show_alert=True); return
    host_data = host_pa["data"]
    if host_data.get("status") != "waiting":
        await q.answer("Игра уже началась.", show_alert=True); return

    bet = host_data["bet"]
    ok, _ = db.spend_coins(uid, bet)
    if not ok:
        await q.answer(f"Нужно {_fmt(bet)} 💰 для этой ставки!", show_alert=True); return
    await q.answer("⚔️ Игра начинается!")

    deck             = _bj_make_deck()
    host_hand, deck  = _bj_deal_hand(deck)
    guest_hand, deck = _bj_deal_hand(deck)
    deck_copy        = list(deck)

    guest_id   = uid
    host_user  = db.get_user(host_id)
    guest_user = db.get_user(guest_id)
    host_name  = host_user.get("display_name",  "???") if host_user  else "???"
    guest_name = guest_user.get("display_name", "???") if guest_user else "???"

    host_done  = _bj_hand_val(host_hand)  == 21
    guest_done = _bj_hand_val(guest_hand) == 21

    host_data.update({
        "status":   "playing",
        "hand":     host_hand,
        "deck":     deck_copy,
        "done":     host_done,
        "guest_id": guest_id,
    })
    db.set_pending_action(host_id, "bj_pvp_host", host_data)

    guest_state = {
        "host_id": host_id,
        "bet":     bet,
        "hand":    guest_hand,
        "deck":    deck_copy,
        "done":    guest_done,
    }
    db.set_pending_action(guest_id, "bj_pvp_guest", guest_state)

    # Instant resolve if both have 21 on deal
    if host_done and guest_done:
        await q.edit_message_text(
            "🃏 *БЛЭКДЖЕК ПвП*\n\n⚡ У обоих 21 с первых карт! Считаем результат...",
            parse_mode="Markdown",
        )
        await _bj_pvp_finish(ctx, host_id, host_data, guest_id, guest_state)
        return

    # Notify host
    host_msg = (
        f"🃏 *БЛЭКДЖЕК ПвП* — Игра началась!\n\n"
        f"Соперник: *{guest_name}*\n\n"
        f"{_bj_pvp_board(host_hand, guest_name, bet)}"
    )
    if host_done:
        host_msg += "\n\n♠ *Блэкджек (21)! Ты автоматически встал.*\n_Ждём соперника..._"
        host_kb   = None
    else:
        host_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("👆 Ещё",  callback_data="casino_bjpvp_hit"),
            InlineKeyboardButton("✋ Стоп", callback_data="casino_bjpvp_stand"),
        ]])
    try:
        await ctx.bot.send_message(host_id, host_msg, parse_mode="Markdown", reply_markup=host_kb)
    except Exception:
        pass

    # Show guest their board
    guest_msg = (
        f"🃏 *БЛЭКДЖЕК ПвП* — Игра началась!\n\n"
        f"Соперник: *{host_name}*\n\n"
        f"{_bj_pvp_board(guest_hand, host_name, bet)}"
    )
    if guest_done:
        guest_msg += "\n\n♠ *Блэкджек (21)! Ты автоматически встал.*\n_Ждём соперника..._"
        guest_kb   = None
    else:
        guest_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("👆 Ещё",  callback_data="casino_bjpvp_hit"),
            InlineKeyboardButton("✋ Стоп", callback_data="casino_bjpvp_stand"),
        ]])

    await q.edit_message_text(guest_msg, parse_mode="Markdown", reply_markup=guest_kb)


async def cb_casino_bjpvp_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel a waiting PvP lobby and refund bet."""
    q   = update.callback_query
    uid = q.from_user.id

    pa = db.get_pending_action(uid)
    if not pa or pa.get("action") != "bj_pvp_host":
        await q.answer("Лобби не найдено.", show_alert=True); return

    data = pa["data"]
    if data.get("status") != "waiting":
        await q.answer("Игра уже началась — отмена невозможна.", show_alert=True); return

    bet     = data["bet"]
    new_bal = db.add_coins(uid, bet)
    db.clear_pending_action(uid)
    await q.answer("❌ Лобби отменено.")

    await q.edit_message_text(
        f"❌ *Лобби отменено*\n\n"
        f"Ставка *{_fmt(bet)} 💰* возвращена.\n\n"
        f"💼 Баланс: *{_fmt(new_bal)} 💰*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🃏 Блэкджек", callback_data="casino_bj"),
            InlineKeyboardButton("◀ Казино",    callback_data="casino_menu"),
        ]]),
    )


async def cb_casino_bjpvp_hit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id

    action, data, opp_id = _bj_pvp_get_state(uid)
    if not action:
        await q.answer("Игра не найдена.", show_alert=True); return
    if data.get("status") == "waiting":
        await q.answer("Игра ещё не началась.", show_alert=True); return
    if data.get("done"):
        await q.answer("Ты уже закончил ход.", show_alert=True); return

    await q.answer()

    hand = data["hand"]
    deck = data["deck"]
    bet  = data["bet"]

    card, deck   = _bj_deal_one(deck)
    hand.append(card)
    data["hand"] = hand
    data["deck"] = deck

    opp_user = db.get_user(opp_id) if opp_id else None
    opp_name = opp_user.get("display_name", "???") if opp_user else "???"

    if _bj_status(hand) == "bust":
        data["done"] = True
        db.set_pending_action(uid, action, data)
        pv = _bj_hand_val(hand)
        await q.edit_message_text(
            f"🃏 *БЛЭКДЖЕК ПвП*\n\n"
            f"👤 *Твои карты:* `{_bj_hand_str(hand)}`   _{pv}_\n"
            f"🤝 *Соперник ({opp_name}):* карты скрыты\n\n"
            f"💥 *ПЕРЕБОР! {pv} > 21*\n\n"
            "_Ожидаем соперника..._",
            parse_mode="Markdown",
        )
        await _bj_pvp_check_finish(ctx, uid)
        return

    db.set_pending_action(uid, action, data)

    await q.edit_message_text(
        f"🃏 *БЛЭКДЖЕК ПвП*\n\n"
        f"{_bj_pvp_board(hand, opp_name, bet)}\n\nТвой ход:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👆 Ещё",  callback_data="casino_bjpvp_hit"),
            InlineKeyboardButton("✋ Стоп", callback_data="casino_bjpvp_stand"),
        ]]),
    )


async def cb_casino_bjpvp_stand(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id

    action, data, opp_id = _bj_pvp_get_state(uid)
    if not action:
        await q.answer("Игра не найдена.", show_alert=True); return
    if data.get("status") == "waiting":
        await q.answer("Игра ещё не началась.", show_alert=True); return
    if data.get("done"):
        await q.answer("Ты уже закончил ход.", show_alert=True); return

    await q.answer("✋ Стоп!")

    data["done"] = True
    db.set_pending_action(uid, action, data)

    hand = data["hand"]
    pv   = _bj_hand_val(hand)
    bet  = data["bet"]

    opp_user = db.get_user(opp_id) if opp_id else None
    opp_name = opp_user.get("display_name", "???") if opp_user else "???"

    await q.edit_message_text(
        f"🃏 *БЛЭКДЖЕК ПвП*\n\n"
        f"👤 *Твои карты:* `{_bj_hand_str(hand)}`   _{pv}_\n"
        f"🤝 *Соперник ({opp_name}):* карты скрыты\n\n"
        f"✋ *Стоп — ждём соперника...*\n\n"
        f"Ставка: *{_fmt(bet)} 💰*",
        parse_mode="Markdown",
    )
    await _bj_pvp_check_finish(ctx, uid)


# ═════════════════════════════════════════════════════════════════════════════
# Global Roulette handlers
# ═════════════════════════════════════════════════════════════════════════════

async def _global_roulette_tick(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Крутим глобальную рулетку и отправляем результаты участникам."""
    try:
        state = db.get_global_roulette_state()
        rnd   = state.get("round", 0)
        pot   = int(state.get("pot", 0))

        bets = db.get_global_roulette_bets(rnd)
        if not bets:
            db.close_global_roulette_round(pot)  # котёл переходит, раунд меняется
            return

        players: dict[int, int] = {}
        for b in bets:
            players[b["user_id"]] = players.get(b["user_id"], 0) + b["amount"]

        weights = [o[0] for o in _GLOBAL_OUTCOMES]
        outcome = random.choices(_GLOBAL_OUTCOMES, weights=weights, k=1)[0]
        _, code, emoji, title, desc = outcome

        winners: dict[int, int] = {}

        if code == "burn":
            new_pot = 0
            summary = f"{emoji} *{title}*\n_{desc}_\n\nВсе ставки сгорели. 😢"

        elif code == "jackpot":
            winner_uid = random.choice(list(players.keys()))
            winners[winner_uid] = pot
            new_pot = 0
            wu = db.get_user(winner_uid)
            w_name = wu.get("display_name", "???") if wu else "???"
            summary = (
                f"{emoji} *{title}!*\n_{desc}_\n\n"
                f"🎊 Победитель: *{w_name}*\nВыигрыш: *{_fmt(pot)} 💰*"
            )

        elif code == "split":
            share   = pot // max(len(players), 1)
            winners = {uid: share for uid in players}
            new_pot = pot - share * len(players)
            summary = (
                f"{emoji} *{title}!*\n_{desc}_\n\n"
                f"Каждый получает: *{_fmt(share)} 💰*\nУчастников: *{len(players)}*"
            )

        elif code == "x2":
            total   = pot * 2
            share   = total // max(len(players), 1)
            winners = {uid: share for uid in players}
            new_pot = 0
            summary = (
                f"{emoji} *{title}!*\n_{desc}_\n\n"
                f"Банк удвоен → *{_fmt(total)} 💰*\nКаждый получает: *{_fmt(share)} 💰*"
            )

        elif code == "carryover":
            new_pot = pot
            summary = (
                f"{emoji} *{title}*\n_{desc}_\n\n"
                f"Банк *{_fmt(pot)} 💰* переходит!\n_Ставьте снова..._"
            )

        else:  # x5
            total   = pot * 5
            share   = total // max(len(players), 1)
            winners = {uid: share for uid in players}
            new_pot = 0
            summary = (
                f"{emoji} *{title}!*\n_{desc}_\n\n"
                f"Банк ×5 → *{_fmt(total)} 💰*\nКаждый получает: *{_fmt(share)} 💰*"
            )

        for uid, payout in winners.items():
            db.add_coins(uid, payout)

        db.close_global_roulette_round(new_pot)

        for uid, stake in players.items():
            payout  = winners.get(uid, 0)
            net     = payout - stake
            net_str = f"+{_fmt(net)}" if net >= 0 else _fmt(net)
            bal     = db.get_coins(uid)
            personal = (
                f"🌍 *Глобальная рулетка — результат*\n\n"
                f"{summary}\n\n"
                f"Твоя ставка: *{_fmt(stake)} 💰*\n"
                f"Выплата: *{_fmt(payout)} 💰*  ({net_str})\n\n"
                f"💼 Баланс: *{_fmt(bal)} 💰*"
            )
            try:
                await ctx.bot.send_message(
                    uid, personal, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🌍 Поставить снова", callback_data="casino_global"),
                        InlineKeyboardButton("◀ Казино",           callback_data="casino_menu"),
                    ]]),
                )
            except Exception:
                pass

    except Exception as exc:
        logger.exception("global_roulette_tick error: %s", exc)


async def cb_casino_global(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Lazy-spin: если прошло ≥60 сек с последнего спина — крутим."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    state     = db.get_global_roulette_state()
    last_spin = state.get("last_spin_at")
    if last_spin:
        now = datetime.now(timezone.utc)
        try:
            ls = datetime.fromisoformat(last_spin)
            if ls.tzinfo is None:
                ls = ls.replace(tzinfo=timezone.utc)
        except Exception:
            ls = now
        if (now - ls).total_seconds() >= 60:
            await _global_roulette_tick(ctx)
            state = db.get_global_roulette_state()

    coins = db.get_coins(uid)
    pot   = state.get("pot", 0)
    rnd   = state.get("round", 0)

    rows = []
    for i in range(0, len(_GLOBAL_BETS), 2):
        pair = _GLOBAL_BETS[i:i + 2]
        row  = []
        for amt in pair:
            can = coins >= amt
            row.append(InlineKeyboardButton(
                f"{'🎲' if can else '🚫'} {_fmt(amt)}",
                callback_data=f"casino_globalbet_{amt}" if can else "casino_no_coins",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀ Казино", callback_data="casino_menu")])

    bets_list = db.get_global_roulette_bets(rnd)
    n_players = len({b["user_id"] for b in bets_list})

    outcomes_txt = "\n".join(
        f"{e} {hdr} — {desc}" for _, _, e, hdr, desc in _GLOBAL_OUTCOMES
    )

    await q.edit_message_text(
        f"🌍 *ГЛОБАЛЬНАЯ РУЛЕТКА*\n\n"
        f"🏦 Текущий банк: *{_fmt(pot)} 💰*\n"
        f"👥 Участников: *{n_players}*\n"
        f"⏱ Прокрутка каждую минуту\n\n"
        f"*Возможные исходы:*\n{outcomes_txt}\n\n"
        f"💰 Твой баланс: *{_fmt(coins)}* монет\n\nВыбери ставку:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_casino_global_bet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q   = update.callback_query
    uid = q.from_user.id
    try:
        bet = int(q.data[len("casino_globalbet_"):])
    except ValueError:
        await q.answer("Ошибка ставки.", show_alert=True); return

    ok, new_bal = db.add_global_roulette_bet(uid, bet)
    if not ok:
        await q.answer("Недостаточно монет!", show_alert=True); return

    state = db.get_global_roulette_state()
    pot   = state.get("pot", 0)
    await q.answer(f"✅ Ставка {_fmt(bet)} 💰 принята!")
    await q.edit_message_text(
        f"🌍 *СТАВКА ПРИНЯТА*\n\n"
        f"Ты поставил *{_fmt(bet)} 💰* в глобальный котёл.\n\n"
        f"🏦 Текущий банк: *{_fmt(pot)} 💰*\n\n"
        f"_Результат придёт в личку в конце текущей минуты._\n\n"
        f"💼 Баланс: *{_fmt(new_bal)} 💰*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌍 Ещё ставка", callback_data="casino_global"),
            InlineKeyboardButton("◀ Казино",       callback_data="casino_menu"),
        ]]),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Handler registration helper
# ═════════════════════════════════════════════════════════════════════════════

def casino_handlers() -> list[tuple[str, object]]:
    """Возвращает список (pattern, handler) для регистрации в create_application()."""
    return [
        # Menu
        ("^casino_menu$",            cb_casino_menu),
        # Roulette
        ("^casino_roulette$",        cb_casino_roulette),
        ("^casino_spin_",            cb_casino_spin),
        # Slots — более специфичные паттерны ПЕРВЫМИ
        ("^casino_bonusspin_",       cb_casino_bonus_spin),
        ("^casino_bonusbuy_",        cb_casino_bonus_buy),
        ("^casino_slotspin_",        cb_casino_slots_spin),
        ("^casino_slots$",           cb_casino_slots),
        # Blackjack PvP — специфичные паттерны ПЕРЕД общими bj
        ("^casino_bjpvp_join_",      cb_casino_bjpvp_join),
        ("^casino_bjpvp_bet_",       cb_casino_bjpvp_bet),
        ("^casino_bjpvp_cancel$",    cb_casino_bjpvp_cancel),
        ("^casino_bjpvp_hit$",       cb_casino_bjpvp_hit),
        ("^casino_bjpvp_stand$",     cb_casino_bjpvp_stand),
        ("^casino_bjpvp_create$",    cb_casino_bjpvp_create),
        ("^casino_bj_pvp$",          cb_casino_bj_pvp),
        ("^casino_bj_solo$",         cb_casino_bj_solo),
        # Blackjack solo
        ("^casino_bj$",              cb_casino_bj),
        ("^casino_bjbet_",           cb_casino_bj_bet),
        ("^casino_bjhit$",           cb_casino_bj_hit),
        ("^casino_bjstand$",         cb_casino_bj_stand),
        ("^casino_bjdouble$",        cb_casino_bj_double),
        # Global roulette — специфичный паттерн ПЕРВЫМ
        ("^casino_globalbet_",       cb_casino_global_bet),
        ("^casino_global$",          cb_casino_global),
        # Common
        ("^casino_no_coins$",        cb_casino_no_coins),
    ]
