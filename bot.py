"""Transfer Guesser Bot — main entry point."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

import database as db
import casino as casino_module
import fut as fut_module
from scoring import calculate_points, calculate_elo, calculate_placement_rating, format_fee, parse_fee_input
from config import (
    BOT_TOKEN,
    TOTAL_ROUNDS,
    MAX_HINTS,
    HINT_TYPES,
    HINT_LABELS,
    TIER_LABELS,
    CALIBRATION_GAMES,
    ELO_K_CALIBRATION,
    ELO_K_RATED,
    ELO_EXACT_BONUS,
    ELO_CLOSE_BONUS,
    ELO_HINT_PENALTY,
    COINS_WIN_BONUS,
    COINS_DRAW_BONUS,
    COINS_EXACT_BONUS,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Achievement definitions ───────────────────────────────────────────────────

ACHIEVEMENTS: dict[str, dict] = {
    # ── 🎯 Угадывание трансферов ─────────────────────────────────────────
    "first_exact": {
        "emoji": "🎯", "name": "Снайпер",
        "desc": "Угадать трансфер точно в первый раз",
        "reward": 500, "secret": False,
    },
    "silent_exact": {
        "emoji": "🤫", "name": "Тихий снайпер",
        "desc": "Точное попадание без единой подсказки",
        "reward": 1_000, "secret": False,
    },
    "hattrick": {
        "emoji": "🔱", "name": "Хет-трик",
        "desc": "Три точных попадания в одной игре",
        "reward": 2_000, "secret": False,
    },
    "perfect_game": {
        "emoji": "💎", "name": "Идеальная игра",
        "desc": "Три точных попадания без единой подсказки",
        "reward": 5_000, "secret": False,
    },
    "no_hints_win": {
        "emoji": "🧠", "name": "Чистая победа",
        "desc": "Победа без использования подсказок",
        "reward": 2_000, "secret": False,
    },
    "exact_10": {
        "emoji": "🏹", "name": "Глаз-алмаз",
        "desc": "10 точных попаданий суммарно",
        "reward": 3_000, "secret": False,
    },
    "exact_50": {
        "emoji": "🦅", "name": "Орлиный глаз",
        "desc": "50 точных попаданий суммарно",
        "reward": 10_000, "secret": False,
    },
    "exact_100": {
        "emoji": "🔮", "name": "Оракул",
        "desc": "100 точных попаданий суммарно",
        "reward": 25_000, "secret": True,
    },
    # ── 🏆 Соревновательные ──────────────────────────────────────────────
    "first_win": {
        "emoji": "⚡", "name": "Первая победа",
        "desc": "Одержать первую победу",
        "reward": 500, "secret": False,
    },
    "calibrated": {
        "emoji": "📊", "name": "Откалиброван",
        "desc": "Завершить калибровку и получить рейтинг",
        "reward": 1_000, "secret": False,
    },
    "win_streak_3": {
        "emoji": "🔥", "name": "На коне",
        "desc": "3 победы подряд",
        "reward": 1_500, "secret": False,
    },
    "win_streak_5": {
        "emoji": "💥", "name": "Доминатор",
        "desc": "5 побед подряд",
        "reward": 5_000, "secret": True,
    },
    "rating_1000": {
        "emoji": "🥈", "name": "Эксперт",
        "desc": "Достичь рейтинга 1000",
        "reward": 3_000, "secret": False,
    },
    "rating_1500": {
        "emoji": "🥇", "name": "Мастер",
        "desc": "Достичь рейтинга 1500",
        "reward": 8_000, "secret": True,
    },
    "games_10": {
        "emoji": "🎮", "name": "Втянулся",
        "desc": "Сыграть 10 игр",
        "reward": 1_000, "secret": False,
    },
    "games_50": {
        "emoji": "🏟", "name": "Старожил",
        "desc": "Сыграть 50 игр",
        "reward": 5_000, "secret": False,
    },
    # ── ⚽ FUT Клуб ──────────────────────────────────────────────────────
    "first_pack": {
        "emoji": "📦", "name": "Первый пак",
        "desc": "Открыть первый пак карточек",
        "reward": 0, "secret": False,
    },
    "got_97": {
        "emoji": "👑", "name": "Золотой грааль",
        "desc": "Вытащить карточку OVR 97",
        "reward": 15_000, "secret": True,
    },
    "rich_100k": {
        "emoji": "💰", "name": "Нувориш",
        "desc": "Накопить 100,000 монет",
        "reward": 0, "secret": True,
    },
}


# ── Cosmetic definitions ──────────────────────────────────────────────────────

TITLES: dict[str, dict] = {
    "silent":       {"emoji": "🤫", "label": "Тихоня",        "from_ach": "silent_exact"},
    "hattrick":     {"emoji": "🔱", "label": "Хет-трикер",    "from_ach": "hattrick"},
    "perfect":      {"emoji": "💎", "label": "Перфекционист", "from_ach": "perfect_game"},
    "telepath":     {"emoji": "🧠", "label": "Телепат",       "from_ach": "no_hints_win"},
    "archer":       {"emoji": "🏹", "label": "Лучник",        "from_ach": "exact_10"},
    "eagle":        {"emoji": "🦅", "label": "Снайпер",       "from_ach": "exact_50"},
    "oracle":       {"emoji": "🔮", "label": "Оракул",        "from_ach": "exact_100"},
    "onfire":       {"emoji": "🔥", "label": "Горящий",       "from_ach": "win_streak_3"},
    "dominator":    {"emoji": "💥", "label": "Доминатор",     "from_ach": "win_streak_5"},
    "master":       {"emoji": "🥇", "label": "Мастер",        "from_ach": "rating_1500"},
}

PHRASES: dict[str, dict] = {
    "p_sniper":     {"text": "🎯 Угадал с первого раза. Случайность? Навряд ли.", "from_ach": "first_exact"},
    "p_silent":     {"text": "🤫 Мне не нужны подсказки.",                         "from_ach": "silent_exact"},
    "p_hattrick":   {"text": "🔱 Три из трёх. Просто подумай об этом.",            "from_ach": "hattrick"},
    "p_perfect":    {"text": "💎 Идеальная игра. Ты видел что-нибудь подобное?",  "from_ach": "perfect_game"},
    "p_telepath":   {"text": "🧠 Победил без единой подсказки.",                   "from_ach": "no_hints_win"},
    "p_eagle":      {"text": "🦅 50 точных. Я просто знаю цены.",                  "from_ach": "exact_50"},
    "p_oracle":     {"text": "🔮 100 точных попаданий. Я и есть рынок.",           "from_ach": "exact_100"},
    "p_onfire":     {"text": "🔥 Три подряд. Ты уверен что хочешь продолжать?",   "from_ach": "win_streak_3"},
    "p_dominator":  {"text": "💥 Пять побед подряд. Добро пожаловать в мой кошмар.", "from_ach": "win_streak_5"},
    "p_master":     {"text": "🥇 Мастер рынка приветствует тебя.",                 "from_ach": "rating_1500"},
}

# achievement_id → list of (cosmetic_type, cosmetic_id) to award
ACH_COSMETICS: dict[str, list[tuple[str, str]]] = {
    "first_exact":  [("phrase", "p_sniper")],
    "silent_exact": [("title", "silent"),    ("phrase", "p_silent")],
    "hattrick":     [("title", "hattrick"),  ("phrase", "p_hattrick")],
    "perfect_game": [("title", "perfect"),   ("phrase", "p_perfect")],
    "no_hints_win": [("title", "telepath"),  ("phrase", "p_telepath")],
    "exact_10":     [("title", "archer")],
    "exact_50":     [("title", "eagle"),     ("phrase", "p_eagle")],
    "exact_100":    [("title", "oracle"),    ("phrase", "p_oracle")],
    "win_streak_3": [("title", "onfire"),    ("phrase", "p_onfire")],
    "win_streak_5": [("title", "dominator"), ("phrase", "p_dominator")],
    "rating_1500":  [("title", "master"),    ("phrase", "p_master")],
}


# ── Keyboard helpers ─────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Играть", callback_data="menu_play"),
         InlineKeyboardButton("👤 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton("🏆 Рейтинг", callback_data="menu_leaderboard"),
         InlineKeyboardButton("❓ Помощь", callback_data="menu_help")],
        [InlineKeyboardButton("🎰 Казино", callback_data="casino_menu"),
         InlineKeyboardButton("⚽ FUT Клуб", callback_data="fut_menu")],
    ])


def play_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Вызов игрока",      callback_data="play_challenge")],
        [InlineKeyboardButton("🎲 Случайный соперник", callback_data="play_random")],
        [InlineKeyboardButton("🤖 Тренировка",         callback_data="play_training")],
        [InlineKeyboardButton("← Назад",               callback_data="menu_back")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("← В меню", callback_data="menu_back")]])


def leagues_kb() -> InlineKeyboardMarkup:
    leagues = db.get_leagues()
    buttons = [
        InlineKeyboardButton(f"{lg['flag']} {lg['league_name']}", callback_data=f"gl_{lg['league_id']}")
        for lg in leagues
    ]
    rows = [[b] for b in buttons]
    rows.append([InlineKeyboardButton("← Отмена", callback_data="game_cancel")])
    return InlineKeyboardMarkup(rows)


def clubs_kb(league_id: str, page: int = 0) -> InlineKeyboardMarkup:
    clubs = db.get_clubs_by_league(league_id)
    page_size = 10
    start = page * page_size
    chunk = clubs[start: start + page_size]

    rows = []
    for c in chunk:
        cnt = db.count_transfers_for_club(c["club_id"])
        label = f"{c['club_name']} ({cnt})" if cnt else f"{c['club_name']} —"
        rows.append([InlineKeyboardButton(label, callback_data=f"gc_{c['club_id']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"gcp_{league_id}_{page-1}"))
    if start + page_size < len(clubs):
        nav.append(InlineKeyboardButton("▶️", callback_data=f"gcp_{league_id}_{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("← Назад", callback_data="game_pick_league")])
    return InlineKeyboardMarkup(rows)


def transfers_kb(transfers: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for t in transfers:
        label = f"{t['player_name']}  ({t['season']})"
        rows.append([InlineKeyboardButton(label, callback_data=f"gt_{t['id']}")])
    rows.append([InlineKeyboardButton("← Назад к клубам", callback_data="game_pick_league")])
    return InlineKeyboardMarkup(rows)


def hints_kb(used: list[str]) -> InlineKeyboardMarkup:
    rows = []
    available = [h for h in HINT_TYPES if h not in used]
    for h in available:
        rows.append([InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"gh_{h}")])
    rows.append([InlineKeyboardButton("✅ Угадать без подсказки", callback_data="gh_skip")])
    return InlineKeyboardMarkup(rows)


def result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Реванш", callback_data="result_rematch"),
         InlineKeyboardButton("🏠 Меню", callback_data="menu_back")],
    ])


# ── Photo helper ─────────────────────────────────────────────────────────────

# In-memory cache: photo_url → telegram file_id (avoids re-uploading)
_photo_file_id_cache: dict[str, str] = {}

PHOTO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.transfermarkt.com/",
}


async def _fetch_photo_bytes(url: str) -> bytes | None:
    """Download photo bytes in a thread so we don't block the event loop."""
    import httpx
    try:
        async with httpx.AsyncClient(headers=PHOTO_HEADERS, timeout=10) as client:
            r = await client.get(url)
            if r.status_code == 200:
                return r.content
    except Exception as e:
        logger.debug("Photo fetch failed for %s: %s", url, e)
    return None


async def _send_photo_message(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    photo_url: str | None,
    caption: str,
    reply_markup=None,
) -> Message:
    """Send message with player photo if available, else plain text."""
    if photo_url:
        # Check cache first
        file_id = _photo_file_id_cache.get(photo_url)
        if file_id:
            try:
                return await ctx.bot.send_photo(
                    chat_id, photo=file_id, caption=caption,
                    parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup,
                )
            except TelegramError:
                pass  # cache miss / expired — re-download

        photo_bytes = await _fetch_photo_bytes(photo_url)
        if photo_bytes:
            try:
                msg = await ctx.bot.send_photo(
                    chat_id, photo=photo_bytes, caption=caption,
                    parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup,
                )
                # Cache the file_id returned by Telegram
                if msg.photo:
                    _photo_file_id_cache[photo_url] = msg.photo[-1].file_id
                return msg
            except TelegramError as e:
                logger.debug("send_photo failed: %s", e)

    # Fallback: plain text
    return await ctx.bot.send_message(
        chat_id, caption,
        parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup,
    )


# ── Formatting ───────────────────────────────────────────────────────────────

def rating_display(user: dict) -> str:
    if not user.get("is_calibrated"):
        done = user.get("calibration_games", 0)
        return f"Калибровка {done}/{CALIBRATION_GAMES}"
    return str(user["rating"])


def profile_text(user: dict) -> str:
    gp = user.get("games_played", 0)
    wins = user.get("wins", 0)
    losses = user.get("losses", 0)
    coins = user.get("coins", 0)
    wr = f"{wins/gp*100:.0f}%" if gp else "—"
    titles = db.get_user_cosmetics(user["user_id"], "title")
    phrases = db.get_user_cosmetics(user["user_id"], "phrase")
    cosmetics_line = f"\n🎨 Косметика: {len(titles)} титул\\(ов\\) · {len(phrases)} фраз\\(ы\\)" if (titles or phrases) else ""
    return (
        f"👤 *{_esc(_display_name(user))}*\n"
        f"🏅 Рейтинг: *{_esc(rating_display(user))}*\n"
        f"🪙 Монеты: *{coins}*\n"
        f"🎮 Игр: {gp} \\| ✅ Побед: {wins} \\| ❌ Поражений: {losses}\n"
        f"📊 Винрейт: {wr}"
        f"{cosmetics_line}"
    )


def _esc(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _display_name(user: dict) -> str:
    """Return display name with active title prefix if set."""
    name = user.get("display_name", "?")
    title_id = user.get("active_title")
    if title_id and title_id in TITLES:
        t = TITLES[title_id]
        return f"{t['emoji']} {t['label']} • {name}"
    return name


def tier_effect(tier: str, points: int) -> str:
    effects = {
        "exact": "🎯🎯🎯 ТОЧНОЕ ПОПАДАНИЕ\\! 🎯🎯🎯\n✨⭐💫✨⭐💫✨",
        "5pct":  "🔥🔥 Почти идеал\\! 🔥🔥\n⭐✨⭐",
        "10pct": "👍 Неплохо\\!",
        "20pct": "😅 Близко\\.\\.\\.",
        "miss":  "❌ Мимо",
    }
    base = effects.get(tier, "")
    return f"{base}\n\n*\\+{points} очков*"


# ── State helpers ─────────────────────────────────────────────────────────────

async def get_state(user_id: int) -> tuple[str | None, dict]:
    row = db.get_pending_action(user_id)
    if row:
        return row["action"], row["data"]
    return None, {}


async def set_state(user_id: int, action: str, data: dict) -> None:
    db.set_pending_action(user_id, action, data)


async def clear_state(user_id: int) -> None:
    db.clear_pending_action(user_id)


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username
    existing = db.get_user(user_id)

    if existing:
        # Refresh username in case it changed
        if existing.get("username") != username:
            db.update_user(user_id, username=username)
        await update.message.reply_text(
            f"С возвращением, *{_esc(existing['display_name'])}*\\! 👋",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_menu_kb(),
        )
    else:
        await set_state(user_id, "registering", {})
        await update.message.reply_text(
            "👋 Добро пожаловать в *Transfer Guesser*\\!\n\n"
            "Угадывай стоимость трансферов и зарабатывай рейтинг\\.\n\n"
            "Введи своё *игровое имя*:",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ── /cancel ───────────────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await clear_state(user_id)
    await update.message.reply_text("Действие отменено.", reply_markup=main_menu_kb())


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_help(update.message)


async def _send_help(msg: Message) -> None:
    text = (
        "*Transfer Guesser — правила*\n\n"
        "🎮 *Формат:* 1vs1, 6 раундов \\(по 3 для каждого\\)\n\n"
        "*Раунд:*\n"
        "• Выбирающий выбирает лигу → клуб → трансфер\n"
        "• Угадывающий видит имя игрока и пытается угадать сумму\n\n"
        "*Очки за точность:*\n"
        "🎯 Точное попадание — 10 очков\n"
        "🔥 В пределах 5% — 8 очков\n"
        "👍 В пределах 10% — 6 очков\n"
        "😅 В пределах 20% — 4 очка\n"
        "❌ Мимо — 0 очков\n\n"
        "*Подсказки \\(макс\\. 2\\):*\n"
        "Каждая подсказка снижает очки на 1\n\n"
        "*Ввод суммы:* числом в евро, например:\n"
        "`45M` или `45000000` или `500K`\n\n"
        "*ELO:* первые 10 игр — калибровка\\. Рейтинг начисляется после\\."
    )
    await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=back_kb())


# ── Menu callbacks ────────────────────────────────────────────────────────────

async def cb_menu_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Как хочешь играть?", reply_markup=play_menu_kb())


async def cb_menu_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = db.get_user(q.from_user.id)
    if not user:
        await q.edit_message_text("Сначала зарегистрируйся через /start")
        return
    profile_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏅 Достижения", callback_data="achievements"),
         InlineKeyboardButton("🎨 Косметика", callback_data="cosmetics_menu")],
        [InlineKeyboardButton("← В меню", callback_data="menu_back")],
    ])
    await q.edit_message_text(
        profile_text(user),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=profile_kb,
    )


async def cb_achievements(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    earned_ids = set(db.get_user_achievements(uid))
    total = len(ACHIEVEMENTS)
    earned_count = len(earned_ids)

    lines = [f"🏅 *ДОСТИЖЕНИЯ* — {earned_count}/{total}\n"]

    categories = [
        ("🎯 Угадывание трансферов", ["first_exact", "silent_exact", "hattrick", "perfect_game", "no_hints_win", "exact_10", "exact_50", "exact_100"]),
        ("🏆 Соревновательные", ["first_win", "calibrated", "win_streak_3", "win_streak_5", "rating_1000", "rating_1500", "games_10", "games_50"]),
        ("⚽ FUT Клуб", ["first_pack", "got_97", "rich_100k"]),
    ]

    for cat_name, ach_ids in categories:
        lines.append(f"\n*{_esc(cat_name)}*")
        for ach_id in ach_ids:
            ach = ACHIEVEMENTS[ach_id]
            if ach_id in earned_ids:
                lines.append(f"✅ {ach['emoji']} *{_esc(ach['name'])}* — _{_esc(ach['desc'])}_")
            elif ach.get("secret"):
                lines.append(f"🔒 *???* — _Секретное достижение_")
            else:
                lines.append(f"⬜ {ach['emoji']} *{_esc(ach['name'])}* — _{_esc(ach['desc'])}_")

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("← Назад", callback_data="menu_profile"),
        ]]),
    )


async def cb_cosmetics_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Main cosmetics menu: shows titles and phrases."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    owned_titles = db.get_user_cosmetics(uid, "title")
    owned_phrases = db.get_user_cosmetics(uid, "phrase")
    active_title = db.get_active_title(uid)

    lines = ["🎨 *КОСМЕТИКА*\n"]

    if owned_titles:
        lines.append("*🏷 Титулы:*")
        for tid in owned_titles:
            t = TITLES.get(tid, {})
            active_mark = " ✅" if tid == active_title else ""
            lines.append(f"  {t.get('emoji','')} {_esc(t.get('label','?'))}{active_mark}")
    else:
        lines.append("_Нет титулов — зарабатывай достижения\\!_")

    if owned_phrases:
        lines.append("\n*💬 Фразы:*")
        for pid_p in owned_phrases:
            p = PHRASES.get(pid_p, {})
            lines.append(f"  _{_esc(p.get('text', ''))}_")

    rows = []
    if owned_titles:
        rows.append([InlineKeyboardButton("🏷 Выбрать титул", callback_data="cosmetics_titles")])
    rows.append([InlineKeyboardButton("← Профиль", callback_data="menu_profile")])

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_cosmetics_titles(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """List owned titles with option to set/clear active."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    owned_titles = db.get_user_cosmetics(uid, "title")
    active_title = db.get_active_title(uid)

    rows = []
    for tid in owned_titles:
        t = TITLES.get(tid, {})
        label = f"{t.get('emoji','')} {t.get('label','?')}"
        if tid == active_title:
            label += " ✅"
        rows.append([InlineKeyboardButton(label, callback_data=f"set_title_{tid}")])

    if active_title:
        rows.append([InlineKeyboardButton("❌ Снять титул", callback_data="set_title_none")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="cosmetics_menu")])

    await q.edit_message_text(
        "🏷 *Выбери активный титул:*\n_Он будет виден всем игрокам\\._",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_set_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """set_title_<title_id> or set_title_none — set or clear active title."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data  # e.g. "set_title_oracle" or "set_title_none"
    title_id = data[len("set_title_"):]

    if title_id == "none":
        db.set_active_title(uid, None)
        await q.answer("Титул снят", show_alert=False)
    else:
        owned = db.get_user_cosmetics(uid, "title")
        if title_id in owned:
            db.set_active_title(uid, title_id)
            t = TITLES.get(title_id, {})
            await q.answer(f"Титул установлен: {t.get('emoji','')} {t.get('label','')}", show_alert=False)

    # Refresh titles screen
    await cb_cosmetics_titles(update, ctx)


async def cb_taunt_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """taunt_menu_<opponent_id> — show phrase selection to taunt opponent."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    opp_id = int(q.data.split("_")[-1])

    owned_phrases = db.get_user_cosmetics(uid, "phrase")
    if not owned_phrases:
        await q.answer("У тебя нет фраз!", show_alert=True)
        return

    rows = []
    for pid_p in owned_phrases:
        p = PHRASES.get(pid_p, {})
        short = p.get("text", "")[:35] + "…" if len(p.get("text","")) > 35 else p.get("text","")
        rows.append([InlineKeyboardButton(short, callback_data=f"taunt_send_{pid_p}_{opp_id}")])
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data="taunt_cancel")])

    await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))


async def cb_taunt_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """taunt_send_<phrase_id>_<opponent_id> — send the taunt phrase to opponent."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    parts = q.data.split("_")
    # format: taunt_send_<phrase_id>_<opp_id>
    # phrase_id may contain underscores (e.g. p_sniper), opp_id is last part
    opp_id = int(parts[-1])
    phrase_id = "_".join(parts[2:-1])

    owned_phrases = db.get_user_cosmetics(uid, "phrase")
    if phrase_id not in owned_phrases:
        await q.answer("Фраза не найдена.", show_alert=True)
        return

    phrase = PHRASES.get(phrase_id, {})
    sender = db.get_user(uid)
    sender_name = _display_name(sender) if sender else "Соперник"

    phrase_text = phrase.get("text", "")
    msg = (
        f"💬 *{_esc(sender_name)}:*\n"
        f"_{_esc(phrase_text)}_"
    )
    try:
        await ctx.bot.send_message(opp_id, msg, parse_mode=ParseMode.MARKDOWN_V2)
        await q.answer("Фраза отправлена! 💬", show_alert=False)
    except TelegramError:
        await q.answer("Не удалось отправить.", show_alert=True)

    # Restore original result keyboard
    await q.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Реванш", callback_data="result_rematch"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu_back"),
        ]])
    )


async def cb_taunt_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Реванш", callback_data="result_rematch"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu_back"),
        ]])
    )


async def cb_menu_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    leaders = db.get_leaderboard(10)
    if not leaders:
        await q.edit_message_text("Рейтинг пока пуст.", reply_markup=back_kb())
        return

    lines = ["🏆 *Топ игроков*\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, u in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}\\."
        name = _esc(_display_name(u))
        rating = _esc(rating_display(u))
        gp = u.get("games_played", 0)
        lines.append(f"{medal} *{name}* — {rating} \\({gp} игр\\)")

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=back_kb(),
    )


async def cb_menu_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await _send_help(q.message)


async def cb_menu_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await clear_state(q.from_user.id)
    await q.edit_message_text("Главное меню:", reply_markup=main_menu_kb())


# ── Challenge flow ────────────────────────────────────────────────────────────

def _players_list_kb(current_user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated list of all registered players except current user."""
    players = db.get_all_users(exclude_user_id=current_user_id)
    page_size = 8
    start = page * page_size
    chunk = players[start: start + page_size]

    rows = []
    for p in chunk:
        rating = p.get("rating", 0)
        label = f"{p['display_name']}  •  {rating}⭐"
        rows.append([InlineKeyboardButton(label, callback_data=f"chp_{p['user_id']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"chpp_{current_user_id}_{page - 1}"))
    if start + page_size < len(players):
        nav.append(InlineKeyboardButton("▶️", callback_data=f"chpp_{current_user_id}_{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("← Отмена", callback_data="menu_back")])
    return InlineKeyboardMarkup(rows)


async def cb_play_challenge(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = db.get_user(q.from_user.id)
    if not user:
        await q.edit_message_text("Сначала зарегистрируйся через /start")
        return

    players = db.get_all_users(exclude_user_id=q.from_user.id)
    if not players:
        await q.edit_message_text(
            "Пока нет других зарегистрированных игроков\\. Пригласи друзей\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="menu_back")]]),
        )
        return

    await q.edit_message_text(
        "⚔️ *Выбери соперника:*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_players_list_kb(q.from_user.id),
    )


async def cb_players_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Pagination for the players list: chpp_{current_user_id}_{page}"""
    q = update.callback_query
    await q.answer()
    parts = q.data[5:].rsplit("_", 1)
    current_user_id, page = int(parts[0]), int(parts[1])
    await q.edit_message_reply_markup(reply_markup=_players_list_kb(current_user_id, page))


async def cb_select_opponent(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked an opponent from the list: chp_{opponent_id}"""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    opponent_id = int(q.data[4:])  # strip "chp_"

    user = db.get_user(user_id)
    target = db.get_user(opponent_id)
    if not user or not target:
        await q.edit_message_text("Игрок не найден.")
        return

    challenge = db.create_challenge(user_id, target["user_id"])
    challenge_id = challenge["id"]

    await set_state(user_id, "waiting_for_opponent", {
        "challenge_id": challenge_id,
        "challenged_id": target["user_id"],
    })
    await set_state(target["user_id"], "challenge_received", {
        "challenge_id": challenge_id,
        "challenger_id": user_id,
    })

    # Show target's stats to challenger
    gp = target.get("games_played", 0)
    wins = target.get("wins", 0)
    losses = target.get("losses", 0)
    wr = f"{wins/gp*100:.0f}%" if gp else "—"
    await q.edit_message_text(
        f"📊 *{_esc(target['display_name'])}*\n"
        f"🏅 Рейтинг: {_esc(rating_display(target))}\n"
        f"🎮 Игр: {gp} \\| ✅ Побед: {wins} \\| ❌ Поражений: {losses}\n"
        f"📊 Винрейт: {_esc(wr)}\n\n"
        f"Вызов отправлен\\. Ждём ответа\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить вызов", callback_data="menu_back")]]),
    )

    # Notify challenged player
    gp_c = user.get("games_played", 0)
    wins_c = user.get("wins", 0)
    losses_c = user.get("losses", 0)
    wr_c = f"{wins_c/gp_c*100:.0f}%" if gp_c else "—"
    try:
        await ctx.bot.send_message(
            target["user_id"],
            f"⚔️ *{_esc(_display_name(user))}* вызывает тебя\\!\n\n"
            f"🏅 Рейтинг: {_esc(rating_display(user))}\n"
            f"🎮 Игр: {gp_c} \\| ✅ Побед: {wins_c} \\| ❌ Поражений: {losses_c}\n"
            f"📊 Винрейт: {_esc(wr_c)}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Принять", callback_data=f"challenge_accept_{challenge_id}_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"challenge_decline_{challenge_id}_{user_id}"),
            ]]),
        )
    except TelegramError as e:
        logger.warning("Could not DM challenged player %s: %s", target["user_id"], e)
        await q.edit_message_text(
            "⚠️ Не удалось отправить уведомление сопернику\\. Возможно, они не запустили бота\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        await clear_state(user_id)


async def cb_play_random(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    user = db.get_user(user_id)
    if not user:
        await q.edit_message_text("Сначала зарегистрируйся через /start")
        return

    action, data = await get_state(user_id)
    if action == "in_random_queue":
        await q.answer("Ты уже в очереди!", show_alert=True)
        return

    # Check if someone else is in the queue
    res = (
        db.get_client().table("pending_actions")
        .select("user_id, data")
        .eq("action", "in_random_queue")
        .neq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if res.data:
        opponent_id = res.data[0]["user_id"]
        opponent = db.get_user(opponent_id)
        if opponent:
            await clear_state(opponent_id)
            await _start_game(ctx, user, opponent, q.message)
            return

    await set_state(user_id, "in_random_queue", {})
    await q.edit_message_text(
        "🔍 Ищу соперника\\.\\.\\.\n\nКак только найдётся — игра начнётся автоматически\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Выйти из очереди", callback_data="menu_back")]]),
    )


async def cb_challenge_accept(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")  # challenge_accept_{id}_{challenger_id}
    challenge_id = int(parts[2])
    challenger_id = int(parts[3])

    challenge = db.get_challenge(challenge_id)
    if not challenge or challenge["status"] != "pending":
        await q.edit_message_text("Этот вызов уже неактуален.")
        return

    db.update_challenge_status(challenge_id, "accepted")

    challenger = db.get_user(challenger_id)
    challenged = db.get_user(q.from_user.id)
    if not challenger or not challenged:
        await q.edit_message_text("Ошибка: игрок не найден.")
        return

    await clear_state(challenger_id)
    await clear_state(q.from_user.id)
    await _start_game(ctx, challenger, challenged, q.message)


async def cb_challenge_decline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Вызов отклонён", show_alert=True)
    parts = q.data.split("_")  # challenge_decline_{id}_{challenger_id}
    challenge_id = int(parts[2])
    challenger_id = int(parts[3])

    db.update_challenge_status(challenge_id, "declined")
    await clear_state(q.from_user.id)

    decliner = db.get_user(q.from_user.id)
    name = decliner["display_name"] if decliner else "Соперник"
    try:
        await ctx.bot.send_message(
            challenger_id,
            f"😔 *{_esc(name)}* отклонил вызов\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_menu_kb(),
        )
    except TelegramError:
        pass

    await q.edit_message_text("Вызов отклонён.", reply_markup=main_menu_kb())


# ── Game start ────────────────────────────────────────────────────────────────

async def _start_game(
    ctx: ContextTypes.DEFAULT_TYPE,
    player_a: dict,
    player_b: dict,
    origin_msg: Message,
) -> None:
    """Coin flip → create game → send first turn."""
    a_id = player_a["user_id"]
    b_id = player_b["user_id"]

    # Coin flip
    first_player, second_player = (
        (player_a, player_b) if random.random() < 0.5 else (player_b, player_a)
    )
    first_id = first_player["user_id"]
    second_id = second_player["user_id"]

    game = db.create_game(first_id, second_id)
    game_id = game["game_id"]

    # Animate coin flip for both players
    coin_msg_a = await ctx.bot.send_message(a_id, "🪙 Подбрасываю монетку\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    coin_msg_b = await ctx.bot.send_message(b_id, "🪙 Подбрасываю монетку\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

    await asyncio.sleep(0.8)
    for msg in [coin_msg_a, coin_msg_b]:
        try:
            await msg.edit_text("🪙 В воздухе\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramError:
            pass

    await asyncio.sleep(0.8)
    result_text = (
        f"✅ Первым ходит *{_esc(first_player['display_name'])}*\\!"
    )
    for msg in [coin_msg_a, coin_msg_b]:
        try:
            await msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramError:
            pass

    await asyncio.sleep(1.0)

    # Create first round
    round_row = db.create_round(game_id, 1, first_id, second_id)

    # Set states
    await set_state(first_id, "picking_league", {
        "game_id": game_id,
        "round_num": 1,
        "opponent_id": second_id,
    })
    await set_state(second_id, "waiting_for_pick", {
        "game_id": game_id,
        "round_num": 1,
        "picker_id": first_id,
        "opponent_id": first_id,
    })

    # Notify picker
    await ctx.bot.send_message(
        first_id,
        f"⚔️ Игра против *{_esc(second_player['display_name'])}*\\!\n\n"
        f"Раунд *1/{TOTAL_ROUNDS}* — твой ход\\. Выбери лигу:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=leagues_kb(),
    )

    # Notify guesser
    await ctx.bot.send_message(
        second_id,
        f"⚔️ Игра против *{_esc(first_player['display_name'])}*\\!\n\n"
        f"Раунд *1/{TOTAL_ROUNDS}* — соперник выбирает трансфер\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ── Picker flow ───────────────────────────────────────────────────────────────

async def cb_pick_league(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, data = await get_state(user_id)
    if action not in ("picking_league", "picking_club"):
        await q.answer("Сейчас не твой ход.", show_alert=True)
        return

    league_id = q.data[3:]  # strip "gl_"
    data["league_id"] = league_id
    await set_state(user_id, "picking_club", data)

    leagues = {lg["league_id"]: lg for lg in db.get_leagues()}
    lg = leagues.get(league_id, {})
    await q.edit_message_text(
        f"{lg.get('flag','')} *{_esc(lg.get('league_name',''))}* — выбери клуб:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=clubs_kb(league_id),
    )


async def cb_clubs_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    # gcp_{league_id}_{page}
    parts = q.data[4:].rsplit("_", 1)
    league_id, page = parts[0], int(parts[1])
    await q.edit_message_reply_markup(reply_markup=clubs_kb(league_id, page))


async def cb_pick_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, data = await get_state(user_id)
    if action != "picking_club":
        await q.answer("Сейчас не твой ход.", show_alert=True)
        return

    club_id = q.data[3:]  # strip "gc_"
    transfers = db.get_transfers_by_club(club_id)
    if not transfers:
        await q.answer("У этого клуба нет трансферов в базе.", show_alert=True)
        return

    data["club_id"] = club_id
    data["transfer_ids"] = [t["id"] for t in transfers]
    await set_state(user_id, "picking_transfer", data)

    # Find club name
    clubs = db.get_clubs_by_league(data.get("league_id", ""))
    club_name = next((c["club_name"] for c in clubs if c["club_id"] == club_id), club_id)

    await q.edit_message_text(
        f"🔍 *{_esc(club_name)}* — выбери трансфер для соперника:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=transfers_kb(transfers),
    )

    # Notify the waiting guesser which club was chosen
    opponent_id = data.get("opponent_id")
    if opponent_id:
        try:
            await ctx.bot.send_message(
                opponent_id,
                f"🏟 Соперник выбрал клуб: *{_esc(club_name)}*\nВыбирает трансфер\\.\\.\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except TelegramError:
            pass


async def cb_pick_league_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Back button from club list → league list."""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, data = await get_state(user_id)
    if action not in ("picking_club", "picking_transfer"):
        return
    await set_state(user_id, "picking_league", data)
    await q.edit_message_text("Выбери лигу:", reply_markup=leagues_kb())


async def cb_pick_transfer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, data = await get_state(user_id)
    if action != "picking_transfer":
        await q.answer("Сейчас не твой ход.", show_alert=True)
        return

    transfer_id = int(q.data[3:])  # strip "gt_"
    transfer = db.get_transfer(transfer_id)
    if not transfer:
        await q.answer("Трансфер не найден.", show_alert=True)
        return

    game_id = data["game_id"]
    round_num = data["round_num"]
    opponent_id = data["opponent_id"]

    # Update round with chosen transfer
    round_row = db.get_round(game_id, round_num)
    if round_row:
        db.update_round(round_row["id"], transfer_id=transfer_id)

    # Switch picker to waiting
    await set_state(user_id, "waiting_for_guess", {
        "game_id": game_id,
        "round_num": round_num,
        "opponent_id": opponent_id,
    })

    # Send guesser their task
    await set_state(opponent_id, "guessing", {
        "game_id": game_id,
        "round_num": round_num,
        "transfer_id": transfer_id,
        "player_name": transfer["player_name"],
        "actual_fee": transfer["transfer_fee"],
        "hints_used": 0,
        "used_hint_types": [],
        "picker_id": user_id,
    })

    picker = db.get_user(user_id)
    picker_name = picker["display_name"] if picker else "Соперник"

    await q.edit_message_text(
        f"✅ Трансфер выбран\\!\n\n"
        f"👤 Игрок: *{_esc(transfer['player_name'])}*\n"
        f"💰 Настоящая цена: *{_esc(format_fee(transfer['transfer_fee']))}*\n\n"
        f"Ждём ответа соперника\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    game = db.get_game(game_id)
    p1_score = game["player1_score"]
    p2_score = game["player2_score"]

    await _send_guess_prompt(ctx, opponent_id, transfer, round_num, 0, [], p1_score, p2_score, picker_name)


async def _send_guess_prompt(
    ctx: ContextTypes.DEFAULT_TYPE,
    guesser_id: int,
    transfer: dict,
    round_num: int,
    hints_used: int,
    used_hint_types: list[str],
    p1_score: int,
    p2_score: int,
    picker_name: str,
) -> None:
    hint_lines = _build_hint_lines(transfer, used_hint_types)
    can_hint = hints_used < MAX_HINTS

    text = (
        f"⚽ Раунд *{round_num}/{TOTAL_ROUNDS}*\n"
        f"Трансфер от *{_esc(picker_name)}*\n\n"
        f"👤 Игрок: *{_esc(transfer['player_name'])}*\n"
    )
    if hint_lines:
        text += "\n" + "\n".join(hint_lines) + "\n"

    text += (
        f"\n💰 Назови сумму трансфера \\(в евро\\)\\:\n"
        f"_Например: 45M, 45000000, 500K_"
    )

    kb_rows = []
    if can_hint:
        available = [h for h in HINT_TYPES if h not in used_hint_types]
        for h in available:
            kb_rows.append([InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"gh_{h}")])

    kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None
    await _send_photo_message(ctx, guesser_id, transfer.get("photo_url"), text, kb)


def _build_hint_lines(transfer: dict, used_hint_types: list[str]) -> list[str]:
    lines = []
    mapping = {
        "position":    ("🎽 Позиция", transfer.get("position")),
        "age":         ("🎂 Возраст", str(transfer["age"]) + " лет" if transfer.get("age") else None),
        "nationality": ("🌍 Национальность", transfer.get("nationality")),
        "from_club":   ("🏟 Откуда пришёл", transfer.get("from_club")),
        "season":      ("📅 Сезон", transfer.get("season")),
    }
    for ht in used_hint_types:
        label, val = mapping.get(ht, ("", None))
        if val:
            lines.append(f"{label}: *{_esc(str(val))}*")
    return lines


# ── Hint callback ─────────────────────────────────────────────────────────────

async def cb_hint(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user_id = q.from_user.id
    action, data = await get_state(user_id)

    if action != "guessing":
        await q.answer("Сейчас не твоя очередь угадывать.", show_alert=True)
        return

    hint_type = q.data[3:]  # strip "gh_"
    used = data.get("used_hint_types", [])
    hints_used = data.get("hints_used", 0)

    if hints_used >= MAX_HINTS:
        await q.answer("Лимит подсказок исчерпан!", show_alert=True)
        return

    if hint_type in used:
        await q.answer("Эта подсказка уже использована.", show_alert=True)
        return

    used.append(hint_type)
    hints_used += 1
    data["used_hint_types"] = used
    data["hints_used"] = hints_used
    await set_state(user_id, "guessing", data)

    transfer = db.get_transfer(data["transfer_id"])
    mapping = {
        "position":    ("🎽 Позиция", transfer.get("position")),
        "age":         ("🎂 Возраст", str(transfer["age"]) + " лет" if transfer.get("age") else None),
        "nationality": ("🌍 Национальность", transfer.get("nationality")),
        "from_club":   ("🏟 Откуда пришёл", transfer.get("from_club")),
        "season":      ("📅 Сезон", transfer.get("season")),
    }
    label, val = mapping.get(hint_type, ("?", None))
    val_str = str(val) if val else "неизвестно"

    await q.answer(f"{label}: {val_str}", show_alert=True)

    # Update keyboard — remove used hint, keep remaining
    remaining = [h for h in HINT_TYPES if h not in used]
    kb_rows = [[InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"gh_{h}")] for h in remaining]
    try:
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None)
    except TelegramError:
        pass


# ── Text input router ─────────────────────────────────────────────────────────

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    action, data = await get_state(user_id)

    if action == "registering":
        await _handle_registration(update, text)
    elif action == "guessing":
        await _handle_guess(update, ctx, text, data)
    elif action == "training_guessing":
        await _handle_training_guess(update, ctx, text, data)
    elif action in ("dbg_set_coins", "dbg_set_rating"):
        if _is_superadmin(user_id):
            await _handle_dbg_input(update, ctx, action, data)
    elif await fut_module.handle_fut_text(update, ctx):
        pass  # обработано FUT модулем (рынок / трейды)
    else:
        await update.message.reply_text(
            "Используй меню ниже 👇", reply_markup=main_menu_kb()
        )


async def _handle_registration(update: Update, text: str) -> None:
    user_id = update.effective_user.id
    if len(text) < 2 or len(text) > 20:
        await update.message.reply_text("Имя должно быть от 2 до 20 символов. Попробуй ещё раз:")
        return
    username = update.effective_user.username
    db.create_user(user_id, username, text)
    await clear_state(user_id)
    await update.message.reply_text(
        f"✅ Добро пожаловать, *{_esc(text)}*\\!\n\nВыбери действие:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=main_menu_kb(),
    )


# ── Guess handler ─────────────────────────────────────────────────────────────

async def _handle_guess(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    text: str,
    data: dict,
) -> None:
    user_id = update.effective_user.id
    guess = parse_fee_input(text)
    if guess is None:
        await update.message.reply_text(
            "Не могу распознать сумму\\. Примеры: `45M`, `45000000`, `500K`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    actual_fee = data["actual_fee"]
    hints_used = data.get("hints_used", 0)
    used_hint_types = data.get("used_hint_types", [])
    game_id = data["game_id"]
    round_num = data["round_num"]
    transfer_id = data["transfer_id"]
    picker_id = data["picker_id"]
    player_name = data["player_name"]

    tier, points = calculate_points(guess, actual_fee, hints_used)

    # Update round in DB
    round_row = db.get_round(game_id, round_num)
    if round_row:
        dev = abs(guess - actual_fee) / actual_fee * 100 if actual_fee else 0
        db.update_round(
            round_row["id"],
            guess_amount=guess,
            accuracy_percent=round(dev, 2),
            accuracy_tier=tier,
            points_earned=points,
            hints_used=hints_used,
            hint_types=used_hint_types,
            completed=True,
        )

    # Update game scores
    game = db.get_game(game_id)
    p1_id = game["player1_id"]
    p2_id = game["player2_id"]
    p1_score = game["player1_score"]
    p2_score = game["player2_score"]

    if user_id == p1_id:
        p1_score += points
    else:
        p2_score += points

    db.update_game(game_id, player1_score=p1_score, player2_score=p2_score)

    effect = tier_effect(tier, points)

    # Result card shown to both players
    def _result_card(is_guesser: bool) -> str:
        role = "Твой результат" if is_guesser else "Результат соперника"
        card = (
            f"{effect}\n\n"
            f"👤 *{_esc(player_name)}*\n"
            f"✅ Правильная цена: *{_esc(format_fee(actual_fee))}*\n"
            f"🎯 {'Твой ответ' if is_guesser else 'Ответ соперника'}: *{_esc(format_fee(guess))}*"
        )
        if hints_used:
            card += f"\n💡 Подсказок использовано: {hints_used} \\(\\-{hints_used} к очкам\\)"
        return card

    # Send to guesser
    await update.message.reply_text(
        _result_card(is_guesser=True),
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # Send to picker
    try:
        await ctx.bot.send_message(
            picker_id,
            _result_card(is_guesser=False),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except TelegramError:
        pass

    await clear_state(user_id)

    # Advance to next round or finish
    next_round = round_num + 1
    if next_round > TOTAL_ROUNDS:
        await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
    else:
        # Swap roles: who was guesser becomes picker
        new_picker_id = user_id
        new_guesser_id = picker_id

        db.create_round(game_id, next_round, new_picker_id, new_guesser_id)
        db.update_game(game_id, current_round=next_round)

        await set_state(new_picker_id, "picking_league", {
            "game_id": game_id,
            "round_num": next_round,
            "opponent_id": new_guesser_id,
        })
        await set_state(new_guesser_id, "waiting_for_pick", {
            "game_id": game_id,
            "round_num": next_round,
            "picker_id": new_picker_id,
            "opponent_id": new_picker_id,
        })

        # Determine guesser's score to show progress
        my_score = p1_score if user_id == p1_id else p2_score
        opp_score = p2_score if user_id == p1_id else p1_score

        await ctx.bot.send_message(
            new_picker_id,
            f"📊 Счёт: *{my_score}* — *{opp_score}*\n\n"
            f"Раунд *{next_round}/{TOTAL_ROUNDS}* — твой ход\\. Выбери лигу:",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=leagues_kb(),
        )

        opp_score2 = p1_score if new_guesser_id == p1_id else p2_score
        my_score2 = p2_score if new_guesser_id == p1_id else p1_score
        await ctx.bot.send_message(
            new_guesser_id,
            f"📊 Счёт: *{my_score2}* — *{opp_score2}*\n\n"
            f"Раунд *{next_round}/{TOTAL_ROUNDS}* — соперник выбирает трансфер\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ── Achievement checker ───────────────────────────────────────────────────────

async def _check_achievements(
    ctx: ContextTypes.DEFAULT_TYPE,
    uid: int,
    *,
    my_rounds: list[dict],
    won: bool,
    lost: bool,
    my_score: int,
    new_rating: int,
    just_calibrated: bool,
    user_before: dict,
) -> None:
    """Check all achievements for a player after a game. Awards coins for new ones."""
    earned_set = set(db.get_user_achievements(uid))
    newly_earned: list[str] = []

    def _try_award(ach_id: str) -> bool:
        if ach_id in earned_set:
            return False
        if db.award_achievement(uid, ach_id):
            earned_set.add(ach_id)
            newly_earned.append(ach_id)
            return True
        return False

    completed = [r for r in my_rounds if r.get("completed")]
    exact_rounds = [r for r in completed if r.get("accuracy_tier") == "exact"]
    total_hints = sum(r.get("hints_used", 0) or 0 for r in completed)
    silent_exacts = [r for r in exact_rounds if (r.get("hints_used") or 0) == 0]

    # ── Transfer guessing ─────────────────────────────────────────────────
    if exact_rounds:
        _try_award("first_exact")
    if silent_exacts:
        _try_award("silent_exact")
    if len(exact_rounds) >= 3:
        _try_award("hattrick")
    if len(exact_rounds) >= 3 and total_hints == 0:
        _try_award("perfect_game")
    if won and total_hints == 0:
        _try_award("no_hints_win")

    # Cumulative exact guesses
    if exact_rounds:
        total_exact = db.get_total_exact_guesses(uid)
        if total_exact >= 10:
            _try_award("exact_10")
        if total_exact >= 50:
            _try_award("exact_50")
        if total_exact >= 100:
            _try_award("exact_100")

    # ── Competitive ───────────────────────────────────────────────────────
    if won:
        if user_before.get("wins", 0) == 0:
            _try_award("first_win")
        streak = db.get_win_streak(uid) + 1
        db.set_win_streak(uid, streak)
        if streak >= 3:
            _try_award("win_streak_3")
        if streak >= 5:
            _try_award("win_streak_5")
    elif lost:
        db.set_win_streak(uid, 0)

    if just_calibrated:
        _try_award("calibrated")

    if new_rating >= 1000:
        _try_award("rating_1000")
    if new_rating >= 1500:
        _try_award("rating_1500")

    games_after = user_before.get("games_played", 0) + 1
    if games_after >= 10:
        _try_award("games_10")
    if games_after >= 50:
        _try_award("games_50")

    # Coin balance check
    user_now = db.get_user(uid)
    if user_now and user_now.get("coins", 0) >= 100_000:
        _try_award("rich_100k")

    if not newly_earned:
        return

    # ── Send achievement notification ─────────────────────────────────────
    for ach_id in newly_earned:
        ach = ACHIEVEMENTS.get(ach_id, {})
        reward = ach.get("reward", 0)
        if reward:
            db.add_coins(uid, reward)

        emoji = ach.get("emoji", "🏅")
        name = ach.get("name", ach_id)
        desc = ach.get("desc", "")
        reward_line = f"\n💰 *\\+{reward:,} монет*".replace(",", " ") if reward else ""

        text = (
            f"🏅 *НОВОЕ ДОСТИЖЕНИЕ\\!*\n"
            f"{'─' * 22}\n"
            f"{emoji} *{_esc(name)}*\n"
            f"_{_esc(desc)}_"
            f"{reward_line}"
        )
        try:
            await ctx.bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramError:
            pass

    # ── Award cosmetics for new achievements ──────────────────────────────
    for ach_id in newly_earned:
        for c_type, c_id in ACH_COSMETICS.get(ach_id, []):
            if db.award_cosmetic(uid, c_type, c_id):
                if c_type == "title":
                    t = TITLES.get(c_id, {})
                    text = (
                        f"🎨 *НОВАЯ КОСМЕТИКА\\!*\n"
                        f"{'─' * 22}\n"
                        f"🏷 *Титул разблокирован:* {t.get('emoji','')} {_esc(t.get('label',''))}\n"
                        f"_Установи его в Профиль → Косметика_"
                    )
                    try:
                        await ctx.bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN_V2)
                    except TelegramError:
                        pass
                elif c_type == "phrase":
                    p = PHRASES.get(c_id, {})
                    text = (
                        f"🎨 *НОВАЯ КОСМЕТИКА\\!*\n"
                        f"{'─' * 22}\n"
                        f"💬 *Фраза разблокирована:*\n"
                        f"_{_esc(p.get('text', ''))}_\n"
                        f"_Используй её после матча\\!_"
                    )
                    try:
                        await ctx.bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN_V2)
                    except TelegramError:
                        pass


# ── Game finish ───────────────────────────────────────────────────────────────

async def _finish_game(
    ctx: ContextTypes.DEFAULT_TYPE,
    game_id: int,
    p1_id: int,
    p2_id: int,
    p1_score: int,
    p2_score: int,
) -> None:
    if p1_score > p2_score:
        winner_id = p1_id
    elif p2_score > p1_score:
        winner_id = p2_id
    else:
        winner_id = None

    db.finish_game(game_id, winner_id, p1_score, p2_score)

    # Fetch rounds first — needed for ELO skill bonuses
    rounds = db.get_all_rounds(game_id)

    p1 = db.get_user(p1_id)
    p2 = db.get_user(p2_id)

    # Calibration state BEFORE this game counts
    was_cal1 = p1["is_calibrated"]
    was_cal2 = p2["is_calibrated"]
    new_cal1 = min(p1["calibration_games"] + 1, CALIBRATION_GAMES)
    new_cal2 = min(p2["calibration_games"] + 1, CALIBRATION_GAMES)
    just_finished_cal1 = not was_cal1 and new_cal1 >= CALIBRATION_GAMES
    just_finished_cal2 = not was_cal2 and new_cal2 >= CALIBRATION_GAMES

    # Save old ratings BEFORE any update
    old_r1 = p1["rating"]
    old_r2 = p2["rating"]

    rounds_p1 = [r for r in rounds if r["guesser_id"] == p1_id]
    rounds_p2 = [r for r in rounds if r["guesser_id"] == p2_id]

    a_won = True if winner_id == p1_id else (False if winner_id == p2_id else None)

    # ── Resolve new ratings ───────────────────────────────────────────────────
    # Rated players: standard performance ELO with skill bonuses
    # Calibrating players: rating frozen; on game 10 → placement rating assigned
    def _resolve_rating(
        user: dict, pid: int, score: int,
        opp_user: dict, opp_score: int,
        was_calibrated: bool, just_cal: bool,
        my_rounds: list[dict], opp_rounds: list[dict],
    ) -> tuple[int, int, str]:
        """Returns (new_rating, delta, mode) where mode ∈ 'elo'|'placement'|'calibrating'."""
        if was_calibrated:
            # Both players need ELO run — compute independently
            nr, _, d, _ = calculate_elo(
                user["rating"], opp_user["rating"],
                score, opp_score,
                True, opp_user["is_calibrated"],
                user["calibration_games"], opp_user["calibration_games"],
                my_rounds, opp_rounds,
            )
            return nr, d, "elo"
        elif just_cal:
            # This game completes calibration — assign placement
            # game_rounds for this game are already saved, so query includes them
            total_score = db.get_user_total_guessing_score(pid)
            wins_total  = user["wins"] + (1 if winner_id == pid else 0)
            draws_total = (
                user["games_played"] - user["wins"] - user["losses"]
                + (1 if winner_id is None else 0)
            )
            placement = calculate_placement_rating(wins_total, draws_total, CALIBRATION_GAMES, total_score)
            return placement, placement - user["rating"], "placement"
        else:
            # Still calibrating — freeze rating
            return user["rating"], 0, "calibrating"

    new_r1, delta1, mode1 = _resolve_rating(
        p1, p1_id, p1_score, p2, p2_score,
        was_cal1, just_finished_cal1, rounds_p1, rounds_p2,
    )
    new_r2, delta2, mode2 = _resolve_rating(
        p2, p2_id, p2_score, p1, p1_score,
        was_cal2, just_finished_cal2, rounds_p2, rounds_p1,
    )

    db.apply_elo_result(p1, p2, new_r1, new_r2, a_won)

    # Save old user dicts BEFORE re-fetch (needed for achievement checks)
    old_p1, old_p2 = p1, p2

    # Refresh for display
    p1 = db.get_user(p1_id)
    p2 = db.get_user(p2_id)

    # Pre-fetch transfer names for the breakdown
    transfer_names: dict[int, str] = {}
    for r in rounds:
        tid = r.get("transfer_id")
        if tid and tid not in transfer_names:
            t = db.get_transfer(tid)
            if t:
                transfer_names[tid] = t["player_name"]

    TIER_ICON = {"exact": "🎯", "5pct": "🔥", "10pct": "👍", "20pct": "😅", "miss": "❌"}

    def _calculate_coins(player_id: int, my_score: int) -> tuple[int, list[str]]:
        """Returns (total_coins, breakdown_lines)."""
        breakdown = []
        total = my_score
        breakdown.append(f"🎮 Очки в игре: \\+{my_score}")

        # Win/draw bonus
        if winner_id == player_id:
            total += COINS_WIN_BONUS
            breakdown.append(f"🏆 Бонус за победу: \\+{COINS_WIN_BONUS}")
        elif winner_id is None:
            total += COINS_DRAW_BONUS
            breakdown.append(f"🤝 Бонус за ничью: \\+{COINS_DRAW_BONUS}")

        # Exact guess bonus
        exact_count = sum(
            1 for r in rounds
            if r["guesser_id"] == player_id
            and r.get("accuracy_tier") == "exact"
            and r["completed"]
        )
        if exact_count:
            bonus = exact_count * COINS_EXACT_BONUS
            total += bonus
            breakdown.append(f"🎯 Точных попаданий ×{exact_count}: \\+{bonus}")

        return total, breakdown

    def _rounds_block(player_id: int) -> str:
        lines = []
        total = 0
        for r in rounds:
            if r["guesser_id"] != player_id or not r["completed"]:
                continue
            pts = r["points_earned"]
            total += pts
            tier = r.get("accuracy_tier", "miss")
            icon = TIER_ICON.get(tier, "•")
            tid = r.get("transfer_id")
            name = _esc(transfer_names.get(tid, "—")) if tid else "—"
            hints = r.get("hints_used", 0)
            hint_str = f" \\(\\-{hints} подск\\.\\)" if hints else ""
            lines.append(f"{icon} *{name}*{hint_str} — \\+{pts}")
        lines.append(f"\n*Итого: {total} очков*")
        return "\n".join(lines) if lines else "—"

    # Calculate and award coins
    p1_coins, p1_coin_breakdown = _calculate_coins(p1_id, p1_score)
    p2_coins, p2_coin_breakdown = _calculate_coins(p2_id, p2_score)
    db.add_coins(p1_id, p1_coins)
    db.add_coins(p2_id, p2_coins)

    async def _send_result(pid: int, my_score: int, opp_score: int,
                           opponent: dict, new_r: int, old_r: int, delta: int,
                           coins_earned: int, coin_breakdown: list[str],
                           rating_mode: str) -> None:
        me = p1 if pid == p1_id else p2
        diff = new_r - old_r
        diff_str = f"\\+{diff}" if diff >= 0 else str(diff)
        opp_name = _esc(opponent["display_name"])
        my_name = _esc(me["display_name"])

        # ── Header ──
        if winner_id is None:
            header = (
                "🤝 *Н И Ч Ь Я*\n"
                "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
            )
        elif pid == winner_id:
            header = (
                "🏆 *П О Б Е Д А* 🏆\n"
                "⭐✨⭐✨⭐✨⭐✨⭐✨"
            )
        else:
            header = (
                "💔 *П О Р А Ж Е Н И Е*\n"
                "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
            )

        # ── Score ──
        if pid == winner_id:
            score_line = f"*{my_score}* \\: {opp_score}"
        elif winner_id is None:
            score_line = f"*{my_score}* \\: *{opp_score}*"
        else:
            score_line = f"{my_score} \\: *{opp_score}*"

        score_block = (
            f"┌─────────────────────┐\n"
            f"       {my_name}  vs  {opp_name}\n"
            f"            {score_line}\n"
            f"└─────────────────────┘"
        )

        # ── Rounds ──
        rounds_block = _rounds_block(pid)

        # ── Rating ──
        my_rounds_r = rounds_p1 if pid == p1_id else rounds_p2
        if rating_mode == "calibrating":
            cal_done = me.get("calibration_games", 0)
            cal_left = max(0, CALIBRATION_GAMES - cal_done)
            rating_block = (
                f"🔄 *Калибровка:* {cal_done}/{CALIBRATION_GAMES} "
                f"— ещё {cal_left} игр до рейтинга"
            )
        elif rating_mode == "placement":
            rating_block = (
                f"🎉 *Калибровка завершена\\!*\n"
                f"Твой начальный рейтинг: *{new_r}* ⭐\n"
                f"_\\(на основе {CALIBRATION_GAMES} калибровочных игр\\)_"
            )
        else:
            # Rated ELO
            arrow = "📈" if delta >= 0 else "📉"
            delta_str = f"\\+{delta}" if delta >= 0 else str(delta)

            exact_cnt = sum(1 for r in my_rounds_r if r.get("accuracy_tier") == "exact" and r.get("completed"))
            close_cnt = sum(1 for r in my_rounds_r if r.get("accuracy_tier") == "5pct"  and r.get("completed"))
            hints_cnt = sum((r.get("hints_used") or 0) for r in my_rounds_r if r.get("completed"))

            detail_parts = []
            if exact_cnt:
                detail_parts.append(f"🎯×{exact_cnt} \\+{exact_cnt * ELO_EXACT_BONUS}")
            if close_cnt:
                detail_parts.append(f"🔥×{close_cnt} \\+{close_cnt * ELO_CLOSE_BONUS}")
            if hints_cnt:
                detail_parts.append(f"💡×{hints_cnt} \\-{hints_cnt * ELO_HINT_PENALTY}")
            detail = f" _\\({', '.join(detail_parts)}\\)_" if detail_parts else ""

            rating_block = (
                f"{arrow} *Рейтинг:* {old_r} → *{new_r}* \\({delta_str}\\){detail}"
            )

        # ── Coins ──
        coin_lines = "\n".join(coin_breakdown)
        coins_block = (
            f"💰 *Заработано монет:* \\+{coins_earned}\n"
            f"{coin_lines}\n"
            f"*Баланс: {me.get('coins', 0) + coins_earned} 🪙*"
        )

        text = (
            f"{header}\n\n"
            f"{score_block}\n\n"
            f"*Твои угадывания:*\n"
            f"{rounds_block}\n\n"
            f"{coins_block}\n\n"
            f"{rating_block}"
        )

        # Build result keyboard with optional taunt button
        res_rows = [
            [InlineKeyboardButton("🔄 Реванш", callback_data="result_rematch"),
             InlineKeyboardButton("🏠 Меню", callback_data="menu_back")],
        ]
        my_phrases = db.get_user_cosmetics(pid, "phrase")
        opp_id = p2_id if pid == p1_id else p1_id
        if my_phrases:
            res_rows.append([InlineKeyboardButton(
                "💬 Дразнить соперника",
                callback_data=f"taunt_menu_{opp_id}",
            )])
        result_markup = InlineKeyboardMarkup(res_rows)

        await clear_state(pid)
        try:
            await ctx.bot.send_message(
                pid, text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=result_markup,
            )
        except TelegramError as e:
            logger.warning("Could not send result to %s: %s", pid, e)

    await _send_result(p1_id, p1_score, p2_score, p2, new_r1, old_r1, delta1, p1_coins, p1_coin_breakdown, mode1)
    await _send_result(p2_id, p2_score, p1_score, p1, new_r2, old_r2, delta2, p2_coins, p2_coin_breakdown, mode2)

    # ── Check achievements for both players ───────────────────────────────
    await _check_achievements(
        ctx, p1_id,
        my_rounds=rounds_p1,
        won=(winner_id == p1_id),
        lost=(winner_id == p2_id),
        my_score=p1_score,
        new_rating=new_r1,
        just_calibrated=just_finished_cal1,
        user_before=old_p1,
    )
    await _check_achievements(
        ctx, p2_id,
        my_rounds=rounds_p2,
        won=(winner_id == p2_id),
        lost=(winner_id == p1_id),
        my_score=p2_score,
        new_rating=new_r2,
        just_calibrated=just_finished_cal2,
        user_before=old_p2,
    )


# ── Rematch ───────────────────────────────────────────────────────────────────

async def cb_result_rematch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "Хочешь реванш? Вызови соперника через меню\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=play_menu_kb(),
    )


# ── Game cancel ───────────────────────────────────────────────────────────────

async def cb_game_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await clear_state(q.from_user.id)
    await q.edit_message_text("Действие отменено.", reply_markup=main_menu_kb())


# ══════════════════════════════════════════════════════════════════════════════
# ── Debug panel (superadmin only) ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _is_superadmin(user_id: int) -> bool:
    from config import SUPERADMIN_IDS
    return user_id in SUPERADMIN_IDS


def debug_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Выбрать игрока", callback_data="dbg_lookup")],
        [InlineKeyboardButton("← Меню", callback_data="menu_back")],
    ])


def _dbg_users_kb(page: int = 0) -> InlineKeyboardMarkup:
    """Paginated list of all users for debug panel."""
    users = db.get_all_users()
    page_size = 8
    start = page * page_size
    chunk = users[start: start + page_size]

    rows = []
    for u in chunk:
        cal = u.get("calibration_games", 0)
        rating = u.get("rating", 0)
        status = f"{rating}⭐" if u.get("is_calibrated") else f"cal {cal}/10"
        label = f"{u['display_name']}  •  {status}"
        rows.append([InlineKeyboardButton(label, callback_data=f"dbg_su_{u['user_id']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"dbg_up_{page - 1}"))
    if start + page_size < len(users):
        nav.append(InlineKeyboardButton("▶️", callback_data=f"dbg_up_{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("← Назад", callback_data="dbg_back")])
    return InlineKeyboardMarkup(rows)


def debug_user_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Изменить монеты",  callback_data=f"dbg_coins_{uid}"),
         InlineKeyboardButton("🏅 Изменить рейтинг", callback_data=f"dbg_rating_{uid}")],
        [InlineKeyboardButton("🔄 Сбросить калибровку", callback_data=f"dbg_resetcal_{uid}")],
        [InlineKeyboardButton("🗑 Очистить состояние",  callback_data=f"dbg_clearstate_{uid}")],
        [InlineKeyboardButton("← Назад", callback_data="dbg_back")],
    ])


async def cmd_debug(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_superadmin(update.effective_user.id):
        return
    await set_state(update.effective_user.id, "dbg_main", {})
    await update.message.reply_text(
        "🛠 *Дебаг панель*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=debug_main_kb(),
    )


async def cb_dbg_lookup(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    await q.edit_message_text(
        "👥 *Выбери игрока:*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_users_kb(),
    )


async def cb_dbg_userpage(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Pagination for debug user list: dbg_up_{page}"""
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    page = int(q.data.split("_")[2])
    await q.edit_message_reply_markup(reply_markup=_dbg_users_kb(page))


async def cb_dbg_select_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User selected from debug list: dbg_su_{uid}"""
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    target = db.get_user(uid)
    if not target:
        await q.answer("Игрок не найден.", show_alert=True)
        return
    await q.edit_message_text(
        _user_dbg_text(target),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=debug_user_kb(uid),
    )


async def cb_dbg_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await set_state(q.from_user.id, "dbg_main", {})
    await q.edit_message_text("🛠 *Дебаг панель*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=debug_main_kb())


def _user_dbg_text(user: dict) -> str:
    return (
        f"👤 *{_esc(user['display_name'])}* \\(@{_esc(user.get('username') or '—')}\\)\n"
        f"🆔 ID: `{user['user_id']}`\n"
        f"🏅 Рейтинг: *{user['rating']}*\n"
        f"🪙 Монеты: *{user.get('coins', 0)}*\n"
        f"🎮 Игр: {user.get('games_played',0)} \\| ✅ {user.get('wins',0)} \\| ❌ {user.get('losses',0)}\n"
        f"🔄 Калибровка: {user.get('calibration_games',0)}/10 "
        f"\\({'✅' if user.get('is_calibrated') else '⏳'}\\)"
    )


async def cb_dbg_coins(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    await set_state(q.from_user.id, "dbg_set_coins", {"target_uid": uid})
    await q.edit_message_text(
        "💰 Введи количество монет \\(положительное — добавить, отрицательное — снять\\):\n"
        "_Например: 100 или \\-50_",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="dbg_back")]]),
    )


async def cb_dbg_rating(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    await set_state(q.from_user.id, "dbg_set_rating", {"target_uid": uid})
    await q.edit_message_text(
        "🏅 Введи новое значение рейтинга или изменение:\n"
        "_Например: 1500 \\(установить\\) или \\+100 или \\-50_",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="dbg_back")]]),
    )


async def cb_dbg_resetcal(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    db.update_user(uid, is_calibrated=False, calibration_games=0)
    target = db.get_user(uid)
    await q.edit_message_text(
        f"✅ Калибровка сброшена\\.\n\n{_user_dbg_text(target)}",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=debug_user_kb(uid),
    )


async def cb_dbg_clearstate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    db.clear_pending_action(uid)
    await q.answer("✅ Состояние очищено", show_alert=True)


async def _handle_dbg_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE, action: str, data: dict) -> None:
    """Handle text input for debug states."""
    text = update.message.text.strip()
    admin_id = update.effective_user.id

    if action == "dbg_set_coins":
        uid = data["target_uid"]
        try:
            amount = int(text.replace("+", ""))
        except ValueError:
            await update.message.reply_text("❌ Введи число, например: 100 или -50")
            return
        target = db.get_user(uid)
        new_coins = max(0, target.get("coins", 0) + amount)
        db.update_user(uid, coins=new_coins)
        target = db.get_user(uid)
        await set_state(admin_id, "dbg_main", {})
        sign = "\\+" if amount >= 0 else ""
        await update.message.reply_text(
            f"✅ Монеты изменены на *{sign}{amount}*\\. Баланс: *{new_coins}*\n\n{_user_dbg_text(target)}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=debug_user_kb(uid),
        )

    elif action == "dbg_set_rating":
        uid = data["target_uid"]
        target = db.get_user(uid)
        try:
            if text.startswith("+") or text.startswith("-"):
                new_rating = max(100, target["rating"] + int(text))
            else:
                new_rating = max(100, int(text))
        except ValueError:
            await update.message.reply_text("❌ Введи число, например: 1500 или +100 или -50")
            return
        db.update_user(uid, rating=new_rating)
        target = db.get_user(uid)
        await set_state(admin_id, "dbg_main", {})
        await update.message.reply_text(
            f"✅ Рейтинг установлен: *{new_rating}*\n\n{_user_dbg_text(target)}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=debug_user_kb(uid),
        )


# ══════════════════════════════════════════════════════════════════════════════
# ── Training mode (vs bot, no rating changes) ──────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

async def cb_play_training(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    user = db.get_user(user_id)
    if not user:
        await q.edit_message_text("Сначала зарегистрируйся через /start")
        return

    await q.edit_message_text(
        "🤖 *Режим тренировки*\n\n"
        "6 раундов против бота\\. Рейтинг не меняется\\.\n\n"
        "Раунды 1, 3, 5 — бот выбирает, ты угадываешь\\.\n"
        "Раунды 2, 4, 6 — ты выбираешь, бот угадывает\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Начать", callback_data="training_start")],
            [InlineKeyboardButton("← Назад",   callback_data="menu_play")],
        ]),
    )


async def cb_training_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id

    state = {
        "round_num": 1,
        "player_score": 0,
        "bot_score": 0,
        "rounds_data": [],
        "is_player_guessing": True,  # odd rounds: player guesses
    }
    await set_state(user_id, "training_game", state)
    await q.edit_message_text("🎮 Тренировка начинается\\!", parse_mode=ParseMode.MARKDOWN_V2)
    await _training_next_round(ctx, user_id, state)


async def _training_next_round(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    state: dict,
) -> None:
    round_num = state["round_num"]
    is_player_guessing = state["is_player_guessing"]

    if is_player_guessing:
        # Bot picks a random transfer → player guesses
        transfer = _bot_pick_transfer()
        if not transfer:
            await ctx.bot.send_message(user_id, "⚠️ Нет данных для тренировки\\. Дождись окончания загрузки трансферов\\.", parse_mode=ParseMode.MARKDOWN_V2)
            await clear_state(user_id)
            return

        state["current_transfer_id"] = transfer["id"]
        state["current_actual_fee"] = transfer["transfer_fee"]
        state["hints_used"] = 0
        state["used_hint_types"] = []
        await set_state(user_id, "training_guessing", state)

        kb_rows = [[InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"tgh_{h}")] for h in HINT_TYPES]
        caption = (
            f"🤖 Раунд *{round_num}/{TOTAL_ROUNDS}* — Бот выбрал трансфер:\n\n"
            f"👤 Игрок: *{_esc(transfer['player_name'])}*\n\n"
            f"💰 Назови сумму трансфера:\n_Например: 45M, 45000000, 500K_"
        )
        await _send_photo_message(ctx, user_id, transfer.get("photo_url"), caption, InlineKeyboardMarkup(kb_rows))
    else:
        # Player picks → show league selector
        state_copy = dict(state)
        await set_state(user_id, "training_picking_league", state_copy)
        await ctx.bot.send_message(
            user_id,
            f"⚽ Раунд *{round_num}/{TOTAL_ROUNDS}* — Твой ход\\! Выбери лигу:",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=training_leagues_kb(),
        )


def _bot_pick_transfer() -> dict | None:
    """Pick a random transfer from the DB for the bot to use."""
    import random as _random
    leagues = db.get_leagues()
    _random.shuffle(leagues)
    for league in leagues:
        clubs = db.get_clubs_by_league(league["league_id"])
        if not clubs:
            continue
        club = _random.choice(clubs)
        transfers = db.get_transfers_by_club(club["club_id"], limit=20)
        if transfers:
            return _random.choice(transfers)
    return None


def _bot_guess(actual_fee: int) -> int:
    """Simulate bot guess — roughly within ±35% with occasional accuracy."""
    import random as _random
    roll = _random.random()
    if roll < 0.08:    # 8% exact
        return actual_fee
    elif roll < 0.20:  # 12% within 5%
        error = _random.uniform(-0.05, 0.05)
    elif roll < 0.45:  # 25% within 15%
        error = _random.uniform(-0.15, 0.15)
    else:              # 55% within 35%
        error = _random.uniform(-0.35, 0.35)
    return max(100_000, round(actual_fee * (1 + error) / 100_000) * 100_000)


def training_leagues_kb() -> InlineKeyboardMarkup:
    leagues = db.get_leagues()
    rows = [[InlineKeyboardButton(f"{lg['flag']} {lg['league_name']}", callback_data=f"tgl_{lg['league_id']}")] for lg in leagues]
    rows.append([InlineKeyboardButton("❌ Завершить тренировку", callback_data="training_abort")])
    return InlineKeyboardMarkup(rows)


def training_clubs_kb(league_id: str, page: int = 0) -> InlineKeyboardMarkup:
    clubs = db.get_clubs_by_league(league_id)
    page_size = 10
    start = page * page_size
    chunk = clubs[start: start + page_size]

    rows = [[InlineKeyboardButton(c["club_name"], callback_data=f"tgc_{c['club_id']}")] for c in chunk]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"tgcp_{league_id}_{page - 1}"))
    if start + page_size < len(clubs):
        nav.append(InlineKeyboardButton("▶️", callback_data=f"tgcp_{league_id}_{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("← Назад", callback_data="training_pick_league")])
    return InlineKeyboardMarkup(rows)


def training_transfers_kb(transfers: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{t['player_name']} ({t['season']})", callback_data=f"tgt_{t['id']}")] for t in transfers]
    rows.append([InlineKeyboardButton("← Назад", callback_data="training_pick_league")])
    return InlineKeyboardMarkup(rows)


async def cb_training_pick_league(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, state = await get_state(user_id)
    if action not in ("training_picking_league", "training_picking_club"):
        return
    league_id = q.data[4:]  # strip "tgl_"
    state["league_id"] = league_id
    await set_state(user_id, "training_picking_club", state)
    await q.edit_message_reply_markup(reply_markup=training_clubs_kb(league_id))


async def cb_training_clubs_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    # tgcp_{league_id}_{page}
    parts = q.data[5:].rsplit("_", 1)
    league_id, page = parts[0], int(parts[1])
    await q.edit_message_reply_markup(reply_markup=training_clubs_kb(league_id, page))


async def cb_training_pick_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, state = await get_state(user_id)
    if action != "training_picking_club":
        return
    club_id = q.data[4:]  # strip "tgc_"
    transfers = db.get_transfers_by_club(club_id)
    if not transfers:
        await q.answer("У этого клуба нет трансферов в базе.", show_alert=True)
        return
    state["club_id"] = club_id
    await set_state(user_id, "training_picking_transfer", state)
    await q.edit_message_reply_markup(reply_markup=training_transfers_kb(transfers))


async def cb_training_pick_transfer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, state = await get_state(user_id)
    if action != "training_picking_transfer":
        return

    transfer_id = int(q.data[4:])  # strip "tgt_"
    transfer = db.get_transfer(transfer_id)
    if not transfer:
        return

    actual_fee = transfer["transfer_fee"]
    bot_guess = _bot_guess(actual_fee)
    tier, points = calculate_points(bot_guess, actual_fee, 0)

    state["bot_score"] += points
    state["rounds_data"].append({
        "round_num": state["round_num"],
        "guesser": "bot",
        "player_name": transfer["player_name"],
        "actual_fee": actual_fee,
        "guess": bot_guess,
        "tier": tier,
        "points": points,
    })

    tier_icon = {"exact": "🎯", "5pct": "🔥", "10pct": "👍", "20pct": "😅", "miss": "❌"}.get(tier, "•")
    await q.edit_message_text(
        f"🤖 Бот угадывал: *{_esc(transfer['player_name'])}*\n"
        f"✅ Цена: *{_esc(format_fee(actual_fee))}*\n"
        f"🤖 Ответ бота: *{_esc(format_fee(bot_guess))}*\n\n"
        f"{tier_icon} {TIER_LABELS.get(tier, tier)} — бот получает *\\+{points}* очков",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    await _training_advance(ctx, user_id, state)


async def cb_training_hint(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user_id = q.from_user.id
    action, data = await get_state(user_id)
    if action != "training_guessing":
        await q.answer("Сейчас не твоя очередь угадывать.", show_alert=True)
        return

    hint_type = q.data[4:]  # strip "tgh_"
    used = data.get("used_hint_types", [])
    hints_used = data.get("hints_used", 0)

    if hints_used >= MAX_HINTS:
        await q.answer("Лимит подсказок исчерпан!", show_alert=True)
        return
    if hint_type in used:
        await q.answer("Эта подсказка уже использована.", show_alert=True)
        return

    transfer = db.get_transfer(data["current_transfer_id"])
    mapping = {
        "position":    ("🎽 Позиция",       transfer.get("position")),
        "age":         ("🎂 Возраст",        str(transfer["age"]) + " лет" if transfer.get("age") else None),
        "nationality": ("🌍 Национальность", transfer.get("nationality")),
        "from_club":   ("🏟 Откуда пришёл", transfer.get("from_club")),
        "season":      ("📅 Сезон",          transfer.get("season")),
    }
    label, val = mapping.get(hint_type, ("?", None))
    await q.answer(f"{label}: {val or 'неизвестно'}", show_alert=True)

    used.append(hint_type)
    data["used_hint_types"] = used
    data["hints_used"] = hints_used + 1
    await set_state(user_id, "training_guessing", data)

    remaining = [h for h in HINT_TYPES if h not in used]
    kb_rows = [[InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"tgh_{h}")] for h in remaining]
    try:
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None)
    except TelegramError:
        pass


async def _handle_training_guess(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str, data: dict) -> None:
    user_id = update.effective_user.id
    guess = parse_fee_input(text)
    if guess is None:
        await update.message.reply_text(
            "Не могу распознать сумму\\. Примеры: `45M`, `45000000`, `500K`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    actual_fee = data["current_actual_fee"]
    hints_used = data.get("hints_used", 0)
    transfer = db.get_transfer(data["current_transfer_id"])
    player_name = transfer["player_name"] if transfer else "?"

    tier, points = calculate_points(guess, actual_fee, hints_used)
    data["player_score"] += points
    data["rounds_data"].append({
        "round_num": data["round_num"],
        "guesser": "player",
        "player_name": player_name,
        "actual_fee": actual_fee,
        "guess": guess,
        "tier": tier,
        "points": points,
        "hints_used": hints_used,
    })

    effect = tier_effect(tier, points)
    await update.message.reply_text(
        f"{effect}\n\n"
        f"👤 *{_esc(player_name)}*\n"
        f"✅ Правильная цена: *{_esc(format_fee(actual_fee))}*\n"
        f"🎯 Твой ответ: *{_esc(format_fee(guess))}*",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    await _training_advance(ctx, user_id, data)


async def _training_advance(ctx: ContextTypes.DEFAULT_TYPE, user_id: int, state: dict) -> None:
    next_round = state["round_num"] + 1
    if next_round > TOTAL_ROUNDS:
        await _training_finish(ctx, user_id, state)
        return

    state["round_num"] = next_round
    state["is_player_guessing"] = (next_round % 2 == 1)  # odd → player guesses
    await set_state(user_id, "training_game", state)
    await asyncio.sleep(1.0)
    await _training_next_round(ctx, user_id, state)


async def cb_training_abort(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await clear_state(q.from_user.id)
    await q.edit_message_text("Тренировка завершена.", reply_markup=main_menu_kb())


async def cb_training_back_league(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    action, state = await get_state(user_id)
    await set_state(user_id, "training_picking_league", state)
    await q.edit_message_reply_markup(reply_markup=training_leagues_kb())


async def _training_finish(ctx: ContextTypes.DEFAULT_TYPE, user_id: int, state: dict) -> None:
    player_score = state["player_score"]
    bot_score = state["bot_score"]
    rounds_data = state["rounds_data"]

    TIER_ICON = {"exact": "🎯", "5pct": "🔥", "10pct": "👍", "20pct": "😅", "miss": "❌"}

    if player_score > bot_score:
        header = "🏆 *П О Б Е Д А* 🏆\n⭐✨⭐✨⭐✨⭐✨⭐✨"
        score_line = f"*{player_score}* \\: {bot_score}"
    elif bot_score > player_score:
        header = "💔 *П О Р А Ж Е Н И Е*\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
        score_line = f"{player_score} \\: *{bot_score}*"
    else:
        header = "🤝 *Н И Ч Ь Я*\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
        score_line = f"*{player_score}* \\: *{bot_score}*"

    score_block = (
        f"┌─────────────────────┐\n"
        f"        Ты  vs  🤖 Бот\n"
        f"          {score_line}\n"
        f"└─────────────────────┘"
    )

    player_rounds = [r for r in rounds_data if r["guesser"] == "player"]
    lines = []
    for r in player_rounds:
        icon = TIER_ICON.get(r["tier"], "•")
        hints = r.get("hints_used", 0)
        hint_str = f" \\(\\-{hints} подск\\.\\)" if hints else ""
        lines.append(f"{icon} *{_esc(r['player_name'])}*{hint_str} — \\+{r['points']}")
    lines.append(f"\n*Итого: {player_score} очков*")
    rounds_block = "\n".join(lines)

    text = (
        f"{header}\n\n"
        f"{score_block}\n\n"
        f"*Твои угадывания:*\n{rounds_block}\n\n"
        f"🔄 *Тренировка* — рейтинг не изменился"
    )

    await clear_state(user_id)
    await ctx.bot.send_message(
        user_id, text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Ещё раз",  callback_data="training_start"),
             InlineKeyboardButton("🏠 Меню",     callback_data="menu_back")],
        ]),
    )


# ── Application setup ─────────────────────────────────────────────────────────

def create_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("debug",  cmd_debug))

    # Callback queries — specific patterns before general ones
    handlers = [
        # Menu
        ("^menu_play$",           cb_menu_play),
        ("^menu_profile$",        cb_menu_profile),
        ("^achievements$",        cb_achievements),
        ("^cosmetics_menu$",      cb_cosmetics_menu),
        ("^cosmetics_titles$",    cb_cosmetics_titles),
        ("^set_title_",           cb_set_title),
        ("^taunt_menu_",          cb_taunt_menu),
        ("^taunt_send_",          cb_taunt_send),
        ("^taunt_cancel$",        cb_taunt_cancel),
        ("^menu_leaderboard$",    cb_menu_leaderboard),
        ("^menu_help$",           cb_menu_help),
        ("^menu_back$",           cb_menu_back),
        # Play
        ("^play_challenge$",      cb_play_challenge),
        ("^chpp_",                cb_players_page),
        ("^chp_",                 cb_select_opponent),
        ("^play_random$",         cb_play_random),
        ("^play_training$",       cb_play_training),
        # Challenges
        ("^challenge_accept_",    cb_challenge_accept),
        ("^challenge_decline_",   cb_challenge_decline),
        # Results
        ("^result_rematch$",      cb_result_rematch),
        ("^result_menu$",         cb_menu_back),
        # Game
        ("^game_cancel$",         cb_game_cancel),
        ("^game_pick_league$",    cb_pick_league_back),
        ("^gl_",                  cb_pick_league),
        ("^gcp_",                 cb_clubs_page),
        ("^gc_",                  cb_pick_club),
        ("^gt_",                  cb_pick_transfer),
        ("^gh_",                  cb_hint),
        # Training
        ("^training_start$",      cb_training_start),
        ("^training_abort$",      cb_training_abort),
        ("^training_pick_league$",cb_training_back_league),
        ("^tgl_",                 cb_training_pick_league),
        ("^tgcp_",                cb_training_clubs_page),
        ("^tgc_",                 cb_training_pick_club),
        ("^tgt_",                 cb_training_pick_transfer),
        ("^tgh_",                 cb_training_hint),
        # Debug
        ("^dbg_lookup$",          cb_dbg_lookup),
        ("^dbg_up_",              cb_dbg_userpage),
        ("^dbg_su_",              cb_dbg_select_user),
        ("^dbg_back$",            cb_dbg_back),
        ("^dbg_coins_",           cb_dbg_coins),
        ("^dbg_rating_",          cb_dbg_rating),
        ("^dbg_resetcal_",        cb_dbg_resetcal),
        ("^dbg_clearstate_",      cb_dbg_clearstate),
        # Casino
        *casino_module.casino_handlers(),
        # FUT
        *fut_module.fut_handlers(),
    ]
    for pattern, handler in handlers:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return app


def main() -> None:
    app = create_application()
    logger.info("Bot started. Polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
