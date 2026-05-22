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
from patch_notes import PATCH_NOTES
from club_emblems import CLUB_EMBLEMS, club_emblem_html, has_emblem
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

# ── Bot version ───────────────────────────────────────────────────────────────
BOT_VERSION = "v1.4"

# ── Derby definitions ─────────────────────────────────────────────────────────

DERBY_PAIRS: dict[frozenset, tuple[str, int]] = {
    frozenset(["418", "131"]): ("⚽ Эль Класико", 1),
    frozenset(["281", "985"]): ("🔵🔴 Манчестерское дерби", 1),
    frozenset(["11",  "148"]): ("🔴⚪ Северолондонское дерби", 1),
    frozenset(["31",  "29" ]): ("💙❤️ Мерсисайдское дерби", 1),
    frozenset(["46",  "5"  ]): ("⚫🔵 Дерби делла Мадоннина", 1),
    frozenset(["12",  "398"]): ("🟡🔵 Дерби делла Капитале", 1),
    frozenset(["506", "416"]): ("⚫⚪ Дерби делла Моле", 1),
    frozenset(["13",  "418"]): ("❤️⚪ Мадридское дерби", 1),
    frozenset(["583", "244"]): ("🔵🔴 Ле Классик", 1),
    frozenset(["27",  "16" ]): ("🔴🟡 Дер Классикер", 1),
    frozenset(["232", "2410"]): ("🔴🔵 Московское дерби", 1),
    frozenset(["232", "964"]): ("🔴🔵 Дерби двух столиц", 1),
    frozenset(["2410","964"]): ("🔵🔴 Дерби ЦСКА–Зенит", 1),
}

_LEAGUE_CLUB_IDS: dict[str, list[str]] = {
    "PL":  ["281","31","11","985","631","148","762","405","379","1237","29","1003","873","1148","931","703","989","543","180","677"],
    "LL":  ["418","131","13","368","681","150","12321","621","1050","3709","1049","940","367","237","331","714","472","1108","366","1244"],
    "BL":  ["27","16","15","23826","24","79","89","82","60","39","18","533","167","80","86","2036","35","269"],
    "SA":  ["46","5","506","6195","12","398","800","430","1025","1047","130","410","416","276","252","2919","1390","749","1005","607"],
    "L1":  ["583","162","244","1082","1041","417","3911","273","995","969","826","667","415","738","618","1420","290","1421"],
    "RPL": ["964","2410","232","932","121","16704","3725","1083"],
}


def _detect_derby(club1_id: str, club2_id: str) -> tuple[int, str] | None:
    """Returns (level, derby_name) or None if no derby."""
    pair = frozenset([club1_id, club2_id])
    if pair in DERBY_PAIRS:
        name, level = DERBY_PAIRS[pair]
        return level, name
    for clubs in _LEAGUE_CLUB_IDS.values():
        if club1_id in clubs and club2_id in clubs:
            return 2, "🏟 Лиговое дерби"
    return None


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
    # ── 🏟 Преданность клубу ─────────────────────────────────────────────
    "club_fan_25": {
        "emoji": "🏆", "name": "Преданный фанат",
        "desc": "Угадать 25 трансферов из одного клуба",
        "reward": 5_000, "secret": False,
    },
}


# ── Club loyalty levels ───────────────────────────────────────────────────────
# (min_guesses, display_label, emoji, fan_bonus_coins)
CLUB_LOYALTY_LEVELS: list[tuple[int, str, str, int]] = [
    (50, "Легенда",   "🏆", 50),
    (30, "Ультрас",   "🔥", 30),
    (15, "Фанат",     "⭐", 20),
    (5,  "Болельщик", "💚", 15),
]

# ── Reverse round config ───────────────────────────────────────────────────────
# attr → {label, points, text_input}
REVERSE_ATTRS: dict[str, dict] = {
    "nationality": {"label": "🌍 Национальность", "points": 3, "text_input": False},
    "from_club":   {"label": "🏟 Откуда пришёл",   "points": 5, "text_input": False},
    "age":         {"label": "🎂 Возраст",           "points": 5, "text_input": True},
}

# ── Difficulty settings ───────────────────────────────────────────────────────

DIFFICULTY: dict[str, dict] = {
    "easy": {
        "emoji": "🟢", "name": "Легко",
        "desc": "Известные трансферы • 3 подсказки • слабый бот",
        "min_fee": 40_000_000, "max_fee": None,
        "max_hints": 3, "auto_hint": "nationality",
        "coin_mult": 0.7,
    },
    "medium": {
        "emoji": "🟡", "name": "Средне",
        "desc": "Стандартная игра • 2 подсказки",
        "min_fee": None, "max_fee": None,
        "max_hints": 2, "auto_hint": None,
        "coin_mult": 1.0,
    },
    "hard": {
        "emoji": "🔴", "name": "Сложно",
        "desc": "Малоизвестные трансферы • без подсказок • сильный бот",
        "min_fee": None, "max_fee": 20_000_000,
        "max_hints": 0, "auto_hint": None,
        "coin_mult": 1.5,
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
        [InlineKeyboardButton("📋 Патчноуты", callback_data="patch_notes")],
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


def leagues_kb(game_id: int | None = None) -> InlineKeyboardMarkup:
    leagues = db.get_leagues()
    buttons = [
        InlineKeyboardButton(f"{lg['flag']} {lg['league_name']}", callback_data=f"gl_{lg['league_id']}")
        for lg in leagues
    ]
    rows = [[b] for b in buttons]
    rows.append([InlineKeyboardButton("← Отмена", callback_data="game_cancel")])
    if game_id:
        rows.append([InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")])
    return InlineKeyboardMarkup(rows)


def clubs_kb(league_id: str, page: int = 0, game_id: int | None = None) -> InlineKeyboardMarkup:
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
    if game_id:
        rows.append([InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")])
    return InlineKeyboardMarkup(rows)


def transfers_kb(transfers: list[dict], game_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    for t in transfers:
        label = f"{t['player_name']}  ({t['season']})"
        rows.append([InlineKeyboardButton(label, callback_data=f"gt_{t['id']}")])
    rows.append([InlineKeyboardButton("← Назад к клубам", callback_data="game_pick_league")])
    if game_id:
        rows.append([InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")])
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


def profile_text(user: dict, club_count: int = 0) -> str:
    """Returns HTML-formatted profile string."""
    gp     = user.get("games_played", 0)
    wins   = user.get("wins", 0)
    losses = user.get("losses", 0)
    coins  = user.get("coins", 0)
    wr     = f"{wins/gp*100:.0f}%" if gp else "—"

    titles  = db.get_user_cosmetics(user["user_id"], "title")
    phrases = db.get_user_cosmetics(user["user_id"], "phrase")
    cosmetics_line = (
        f"\n🎨 Косметика: {len(titles)} титул(ов) · {len(phrases)} фраз(ы)"
        if (titles or phrases) else ""
    )

    allegiance_id  = str(user.get("club_allegiance") or "")
    allegiance_line = ""
    banner_line     = ""

    if allegiance_id:
        try:
            clubs_res = (
                db.get_client().table("clubs")
                .select("club_name").eq("club_id", allegiance_id).execute()
            )
            cname = clubs_res.data[0]["club_name"] if clubs_res.data else allegiance_id
        except Exception:
            cname = allegiance_id

        level_label, level_emoji, fan_bonus, _ = _club_loyalty(club_count)
        emblem = club_emblem_html(allegiance_id, "🏟")
        badge  = f" {level_emoji} <b>{_hesc(level_label)}</b>" if level_label else ""
        bonus_hint = f" <i>(+{fan_bonus} монет за угадывание)</i>" if fan_bonus else ""
        allegiance_line = (
            f"\n🏟 Клуб-фан: {emblem} <b>{_hesc(cname)}</b>{badge}{bonus_hint}"
        )
        # Баннер — только для Легенды (50+ угаданных)
        if club_count >= CLUB_LOYALTY_LEVELS[0][0]:
            banner_line = f"🏆 ══ {emblem} <b>{_hesc(cname.upper())}</b> ══ 🏆\n\n"

    return (
        f"{banner_line}"
        f"👤 <b>{_hesc(_display_name(user))}</b>\n"
        f"🏅 Рейтинг: <b>{_hesc(rating_display(user))}</b>\n"
        f"🪙 Монеты: <b>{coins}</b>\n"
        f"🎮 Игр: {gp} | ✅ Побед: {wins} | ❌ Поражений: {losses}\n"
        f"📊 Винрейт: {wr}"
        f"{cosmetics_line}"
        f"{allegiance_line}"
    )


def _esc(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _hesc(text: str) -> str:
    """HTML-escape for messages using ParseMode.HTML."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _club_loyalty(count: int) -> tuple[str, str, int, int | None]:
    """
    Return (label, emoji, fan_bonus_coins, next_threshold_or_None).
    next_threshold is None if already at max level.
    """
    for i, (threshold, label, emoji, bonus) in enumerate(CLUB_LOYALTY_LEVELS):
        if count >= threshold:
            next_th = CLUB_LOYALTY_LEVELS[i - 1][0] if i > 0 else None
            return label, emoji, bonus, next_th
    # Below first level — return next threshold to show progress toward it
    return "", "", 0, CLUB_LOYALTY_LEVELS[-1][0]


_cosm_overrides_cache: dict[str, dict] = {}


def _reload_cosm_overrides() -> None:
    """Reload cosmetic definition overrides from Supabase into cache."""
    global _cosm_overrides_cache
    try:
        _cosm_overrides_cache = db.get_cosmetic_overrides()
    except Exception:
        pass


def _get_title(tid: str) -> dict:
    """Return title definition merged: hardcoded defaults + DB overrides."""
    base = dict(TITLES.get(tid, {}))
    ov = _cosm_overrides_cache.get(tid, {})
    if ov.get("emoji"):
        base["emoji"] = ov["emoji"]
    if ov.get("label"):
        base["label"] = ov["label"]
    return base


def _get_phrase(pid: str) -> dict:
    """Return phrase definition merged: hardcoded defaults + DB overrides."""
    base = dict(PHRASES.get(pid, {}))
    ov = _cosm_overrides_cache.get(pid, {})
    if ov.get("body"):
        base["text"] = ov["body"]
    if ov.get("emoji"):
        base["emoji"] = ov["emoji"]
    return base


def _display_name(user: dict) -> str:
    """Return display name with active title prefix if set (plain text, MarkdownV2-safe)."""
    name = user.get("display_name", "?")
    title_id = user.get("active_title")
    if title_id:
        t = _get_title(title_id)
        if t:
            return f"{t['emoji']} {t['label']} • {name}"
    return name


def _display_name_html(user: dict) -> str:
    """Return HTML-formatted display name with title and club emblem (for HTML parse_mode messages)."""
    name = _hesc(user.get("display_name", "?"))
    title_id = user.get("active_title")
    if title_id:
        t = _get_title(title_id)
        if t:
            name = f"{t['emoji']} {_hesc(t['label'])} • {name}"
    allegiance_id = str(user.get("club_allegiance") or "")
    if allegiance_id:
        emblem = club_emblem_html(allegiance_id, "🏟")
        name = f"{emblem} {name}"
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

async def _maybe_notify_update(user_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a one-time update notification if user hasn't seen the latest patch."""
    user = db.get_user(user_id)
    if not user:
        return
    if user.get("last_seen_patch") == BOT_VERSION:
        return
    db.update_user(user_id, last_seen_patch=BOT_VERSION)
    try:
        await ctx.bot.send_message(
            user_id,
            f"🆕 *Вышло обновление {_esc(BOT_VERSION)}\\!*\n\n"
            f"Нажми 📋 *Патчноуты* в меню чтобы узнать что нового\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except TelegramError:
        pass


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username
    existing = db.get_user(user_id)

    if existing:
        # Refresh username in case it changed
        if existing.get("username") != username:
            db.update_user(user_id, username=username)
        await _maybe_notify_update(user_id, ctx)
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


def _help_rules_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏟 Фан клубы", callback_data="help_fanclubs"),
         InlineKeyboardButton("⚔️ Дерби", callback_data="help_derby")],
        [InlineKeyboardButton("← В меню", callback_data="menu_back")],
    ])


def _help_fanclubs_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Смена клуба", callback_data="help_club_switch")],
        [InlineKeyboardButton("← Правила", callback_data="help_rules")],
        [InlineKeyboardButton("← В меню", callback_data="menu_back")],
    ])


def _help_derby_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("← Правила", callback_data="help_rules")],
        [InlineKeyboardButton("← В меню", callback_data="menu_back")],
    ])


def _help_club_switch_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("← Фан клубы", callback_data="help_fanclubs")],
        [InlineKeyboardButton("← В меню", callback_data="menu_back")],
    ])


def _patch_notes_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("← В меню", callback_data="menu_back")],
    ])


def _format_patch_notes() -> str:
    """Format PATCH_NOTES list into MarkdownV2 text."""
    lines: list[str] = ["📋 *Патчноуты Transfer Guesser*\n"]
    for i, entry in enumerate(PATCH_NOTES):
        is_latest = i == 0
        prefix = "🆕 " if is_latest else ""
        version = _esc(entry["version"])
        title = _esc(entry["title"])
        emoji = entry["emoji"]
        lines.append(f"{prefix}{emoji} *{version} — {title}*")
        for change in entry["changes"]:
            lines.append(f"  • {_esc(change)}")
        if i < len(PATCH_NOTES) - 1:
            lines.append("")
    return "\n".join(lines)


HELP_RULES_TEXT = (
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
    "*ELO:* первые 10 игр — калибровка\\. Рейтинг начисляется после\\.\n\n"
    "⚡ *Особый раунд \\(5% шанс\\):*\n"
    "Иногда вместо суммы нужно угадать нацию, возраст или клуб игрока — сумма трансфера при этом известна\\!"
)

HELP_FANCLUBS_TEXT = (
    "*🏟 Фан клубы*\n\n"
    "Угадывай трансферы — прокачивай преданность любимому клубу\\!\n\n"
    "*Как работает:*\n"
    "Каждое угаданное задание с трансфером любого клуба добавляет \\+1 к его счётчику\\. "
    "Угадай 5 трансферов одного клуба — он разблокируется в *Зале болельщика*\\.\n\n"
    "*Как выбрать фан\\-клуб:*\n"
    "Профиль → 🏟 Зал болельщика → выбери клуб из разблокированных\\.\n\n"
    "*Уровни преданности:*\n\n"
    "💚 *Болельщик* — от 5 угаданных\n"
    "└ \\+15 монет за каждый угаданный трансфер клуба\n\n"
    "⭐ *Фанат* — от 15 угаданных\n"
    "└ \\+20 монет за каждый угаданный трансфер клуба\n\n"
    "🔥 *Ультрас* — от 30 угаданных\n"
    "└ \\+30 монет за каждый угаданный трансфер клуба\n"
    "└ 🔥 *Способность:* один раз за игру — если тебе загадали трансфер твоего клуба, "
    "можешь узнать диапазон цены \\(±25%\\) перед угадыванием\n\n"
    "🏆 *Легенда* — от 50 угаданных\n"
    "└ \\+50 монет за каждый угаданный трансфер клуба\n"
    "└ 🔥 *Диапазон цены* \\(как у Ультраса\\)\n"
    "└ 🎯 *Второй шанс:* если не угадал — можешь попробовать ещё раз\\. "
    "Правильная цена при этом скрыта, засчитывается лучший из двух ответов\n\n"
    "_Способности работают только для трансферов своего фан\\-клуба, один раз за игру_"
)

HELP_DERBY_TEXT = (
    "*⚔️ Дерби*\n\n"
    "Когда два игрока с разными фан\\-клубами встречаются в игре — автоматически определяется уровень дерби\\!\n\n"
    "*🏆 Классическое дерби* \\(исторические противостояния\\):\n"
    "Эль Класико, Манчестерское, Московское и другие известные дерби\\.\n"
    "• 8 раундов \\(по 4 каждому\\)\n"
    "• Каждый выбирает только из трансферов своего клуба\n"
    "• Без подсказок\n"
    "• Очки ×2\n"
    "• Последние раунды особые \\(слепой или обмен\\)\n\n"
    "*🏟 Лиговое дерби* \\(клубы из одной лиги\\):\n"
    "• Обычные 6 раундов\n"
    "• Очки ×1\\.5\n\n"
    "*⚡ Особые раунды \\(классическое дерби\\):*\n\n"
    "🕵️ *Слепой раунд* — имя игрока скрыто, угадываешь только по клубу и сезону\n\n"
    "🔄 *Раунд обмена* — система выбирает трансфер автоматически\\. Оба игрока угадывают по очереди \\(пикер не видит цену\\)\\. "
    "Тот, кто угадал точнее, получает бонус \\+5 очков"
)


HELP_CLUB_SWITCH_TEXT = (
    "*🔄 Смена клуба*\n\n"
    "Сменить фан\\-клуб можно в Зале болельщика\\. Но это не бесплатно\\.\n\n"
    "*💰 Стоимость смены:*\n"
    "Зависит от уровня лояльности — чем выше уровень, тем дороже уйти\\.\n\n"
    "*📉 Потеря лояльности:*\n"
    "При каждой измене текущая лояльность делится на 2\\. "
    "Легенда становится Ультрасом, Ультрас — Фанатом и т\\.д\\.\n\n"
    "*⏳ Клеймо перебежчика \\(7 дней\\):*\n"
    "Если переходишь к историческому сопернику \\(Реал↔Барса, МЮ↔МС и др\\.\\) "
    "— получаешь клеймо на 7 дней видимое всем\\. "
    "Повторная измена обновляет таймер\\.\n\n"
    "*🐍 Титулы за повторные измены во время искупления:*\n"
    "🐍 *Иуда* — первая повторная измена \\(×2 трансферов для искупления\\)\n"
    "🐀 *Крыса* — вторая повторная измена \\(×2 снова\\)\n"
    "☠️ *Анафема* — третья и далее\n\n"
    "*🔄 Путь искупления \\(вернулся в свой клуб\\):*\n"
    "Угадывай трансферы родного клуба — метка постепенно снимается\\:\n"
    "😔 *Блудный сын* → 🤍 *Кающийся* → 🕊️ *Прощённый* → ✨ чисто\n\n"
    "_История переходов сохраняется в профиле даже после искупления_"
)


async def _send_help(msg: Message) -> None:
    await msg.reply_text(
        HELP_RULES_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_help_rules_kb(),
    )


# ── Menu callbacks ────────────────────────────────────────────────────────────

async def cb_menu_play(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Как хочешь играть?", reply_markup=play_menu_kb())


async def cb_menu_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    user = db.get_user(uid)
    if not user:
        await q.edit_message_text("Сначала зарегистрируйся через /start")
        return
    allegiance_id = str(user.get("club_allegiance") or "")
    club_count = db.get_club_guess_count(uid, allegiance_id) if allegiance_id else 0
    profile_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏅 Достижения", callback_data="achievements"),
         InlineKeyboardButton("🎨 Косметика", callback_data="cosmetics_menu")],
        [InlineKeyboardButton("🏟 Зал болельщика", callback_data="fan_hall")],
        [InlineKeyboardButton("← В меню", callback_data="menu_back")],
    ])
    await q.edit_message_text(
        profile_text(user, club_count),
        parse_mode=ParseMode.HTML,
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
        ("🏟 Преданность клубу", ["club_fan_25"]),
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


async def cb_fan_hall(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Зал болельщика — показывает прогресс разблокировки клубов."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    user = db.get_user(uid)
    counts = db.get_club_guess_counts(uid)  # {club_id: count}
    allegiance_id = str(user.get("club_allegiance") or "") if user else ""

    # Подтянуть имена клубов одним запросом
    name_map: dict[str, str] = {}
    if counts:
        try:
            club_ids = list(counts.keys())
            res = db.get_client().table("clubs").select("club_id, club_name").in_("club_id", club_ids).execute()
            name_map = {str(r["club_id"]): r["club_name"] for r in (res.data or [])}
        except Exception:
            pass

    unlocked = [(cid, cnt) for cid, cnt in counts.items() if cnt >= 5]
    in_progress = [(cid, cnt) for cid, cnt in counts.items() if cnt < 5]
    # Сортировка: разблокированные по count desc, прогресс по count desc
    unlocked.sort(key=lambda x: -x[1])
    in_progress.sort(key=lambda x: -x[1])

    lines: list[str] = ["<b>🏟 Зал болельщика</b>\n"]

    if allegiance_id:
        cname = name_map.get(allegiance_id, allegiance_id)
        emblem = club_emblem_html(allegiance_id)
        al_cnt = counts.get(allegiance_id, 0)
        lv_label, lv_emoji, fan_bonus, next_th = _club_loyalty(al_cnt)
        badge = f" {lv_emoji} <b>{lv_label}</b>" if lv_label else ""
        bonus_str = f" · +{fan_bonus} монет за угадывание" if fan_bonus else ""
        lines.append(f"<b>Твой клуб:</b> {emblem} <b>{_hesc(cname)}</b>{badge}{bonus_str}\n")
        if next_th is not None:
            left = next_th - al_cnt
            lines.append(f"<i>До следующего уровня: ещё {left} угаданных</i>\n")
    else:
        lines.append("<i>Клуб-фан не выбран</i>\n")

    if unlocked:
        lines.append(f"<b>✅ Разблокировано ({len(unlocked)}):</b>")
        for cid, cnt in unlocked:
            cname = name_map.get(cid, cid)
            emblem = club_emblem_html(cid)
            lv_label, lv_emoji, fan_bonus, next_th = _club_loyalty(cnt)
            badge = f" {lv_emoji} {lv_label}" if lv_label else ""
            is_active = cid == allegiance_id
            active_mark = " ⭐" if is_active else ""
            if next_th is not None:
                bar_len = 10
                cur_th = next((t for t, *_ in CLUB_LOYALTY_LEVELS if cnt >= t), CLUB_LOYALTY_LEVELS[-1][0])
                denom = next_th - cur_th
                filled = min(bar_len, round((cnt - cur_th) / denom * bar_len)) if denom > 0 else bar_len
                bar = "█" * filled + "░" * (bar_len - filled)
                next_lv_label = next((l for t, l, *_ in CLUB_LOYALTY_LEVELS if t == next_th), "")
                next_lv_emoji = next((e for t, l, e, *_ in CLUB_LOYALTY_LEVELS if t == next_th), "")
                progress_str = f" [{bar}] {cnt}/{next_th} → {next_lv_emoji} {next_lv_label}"
            else:
                progress_str = f" · {cnt} угаданных 🏆"
            lines.append(f"  {emblem} <b>{_hesc(cname)}</b>{badge}{active_mark}{progress_str}")
        lines.append("")

    if in_progress:
        lines.append(f"<b>🔓 В процессе ({len(in_progress)}):</b>")
        for cid, cnt in in_progress[:10]:
            cname = name_map.get(cid, cid)
            emblem = club_emblem_html(cid)
            bar_filled = "█" * cnt + "░" * (5 - cnt)
            lines.append(f"  {emblem} {_hesc(cname)} — {bar_filled} {cnt}/5")
        if len(in_progress) > 10:
            lines.append(f"  <i>…и ещё {len(in_progress) - 10}</i>")
        lines.append("")

    if not unlocked and not in_progress:
        lines.append("<i>Ты ещё не угадал ни одного трансфера. Сыграй игру!</i>")

    lines.append(
        "<i>💡 Уровни: 💚 Болельщик (5) → ⭐ Фанат (15) → 🔥 Ультрас (30) → 🏆 Легенда (50)</i>"
    )

    rows = []
    if unlocked:
        rows.append([InlineKeyboardButton("🏟 Выбрать клуб-фан", callback_data="club_allegiance")])
    rows.append([InlineKeyboardButton("← Профиль", callback_data="menu_profile")])

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_cosmetics_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Main cosmetics menu: shows titles, phrases and club allegiance."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    owned_titles = db.get_user_cosmetics(uid, "title")
    owned_phrases = db.get_user_cosmetics(uid, "phrase")
    active_title = db.get_active_title(uid)
    unlocked_clubs = db.get_unlocked_clubs(uid)
    user_data = db.get_user(uid)
    allegiance_id = str(user_data.get("club_allegiance") or "") if user_data else ""

    lines = ["🎨 *КОСМЕТИКА*\n"]

    if owned_titles:
        lines.append("*🏷 Титулы:*")
        for tid in owned_titles:
            t = _get_title(tid)
            active_mark = " ✅" if tid == active_title else ""
            lines.append(f"  {t.get('emoji','')} {_esc(t.get('label','?'))}{active_mark}")
    else:
        lines.append("_Нет титулов — зарабатывай достижения\\!_")

    if owned_phrases:
        lines.append("\n*💬 Фразы:*")
        for pid_p in owned_phrases:
            p = _get_phrase(pid_p)
            lines.append(f"  _{_esc(p.get('text', ''))}_")
        lines.append("\n_💡 Фразы можно использовать в конце матча — кнопка «💬 Дразнить соперника»_")

    # Club allegiance section
    lines.append("\n*🏟 Клубная эмблема:*")
    if unlocked_clubs:
        if allegiance_id:
            try:
                clubs_res = db.get_client().table("clubs").select("club_name").eq("club_id", allegiance_id).execute()
                cname = clubs_res.data[0]["club_name"] if clubs_res.data else allegiance_id
            except Exception:
                cname = allegiance_id
            lines.append(f"  Активный клуб: *{_esc(cname)}* ✅")
        else:
            lines.append("  _Клуб не выбран_")
        lines.append(f"  _Разблокировано клубов: {len(unlocked_clubs)}_")
    else:
        lines.append("  _Угадай 5 трансферов из одного клуба, чтобы разблокировать его эмблему\\._")

    rows = []
    if owned_titles:
        rows.append([InlineKeyboardButton("🏷 Выбрать титул", callback_data="cosmetics_titles")])
    if unlocked_clubs:
        rows.append([InlineKeyboardButton("🏟 Клубная эмблема", callback_data="club_allegiance")])
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
        t = _get_title(tid)
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


async def cb_club_allegiance(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show unlocked clubs list; player picks their fan-club allegiance."""
    q = update.callback_query
    uid = q.from_user.id

    # q may already be answered if called from cb_set/clear_allegiance — ignore errors
    try:
        await q.answer()
    except TelegramError:
        pass

    unlocked = db.get_unlocked_clubs(uid)
    if not unlocked:
        try:
            await q.answer("У тебя ещё нет разблокированных клубов!", show_alert=True)
        except TelegramError:
            pass
        return

    user_data = db.get_user(uid)
    current = str(user_data.get("club_allegiance") or "") if user_data else ""

    # Fetch club names for all unlocked clubs in one call
    try:
        clubs_res = db.get_client().table("clubs").select("club_id, club_name").in_("club_id", unlocked).execute()
        name_map = {str(r["club_id"]): r["club_name"] for r in (clubs_res.data or [])}
    except Exception:
        name_map = {}

    # Build HTML message (needed for tg-emoji custom emblems)
    lines = ["<b>🏟 Клубная эмблема</b>\n", "Выбери свой клуб-фан:\n"]
    if current:
        cname = name_map.get(current, current)
        emblem = club_emblem_html(current)
        lines.append(f"Сейчас: {emblem} <b>{cname}</b> ✅")

    rows = []
    for cid in unlocked:
        cname = name_map.get(cid, cid)
        label = f"✅ {cname}" if cid == current else cname
        rows.append([InlineKeyboardButton(label, callback_data=f"allegiance_set_{cid}")])

    if current:
        rows.append([InlineKeyboardButton("❌ Убрать клуб", callback_data="allegiance_clear")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="cosmetics_menu")])

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_set_allegiance(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """allegiance_set_<club_id> — set club allegiance."""
    q = update.callback_query
    uid = q.from_user.id
    club_id = q.data[len("allegiance_set_"):]

    # Verify ownership
    unlocked = db.get_unlocked_clubs(uid)
    if club_id not in unlocked:
        await q.answer("Этот клуб ещё не разблокирован!", show_alert=True)
        return

    db.set_club_allegiance(uid, club_id)

    try:
        clubs_res = db.get_client().table("clubs").select("club_name").eq("club_id", club_id).execute()
        cname = clubs_res.data[0]["club_name"] if clubs_res.data else club_id
    except Exception:
        cname = club_id

    await q.answer(f"Клуб установлен: {cname}!", show_alert=False)

    # Refresh the allegiance screen
    await cb_club_allegiance(update, ctx)


async def cb_clear_allegiance(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """allegiance_clear — remove club allegiance."""
    q = update.callback_query
    uid = q.from_user.id
    db.set_club_allegiance(uid, None)
    await q.answer("Клуб-фан убран", show_alert=False)
    await cb_club_allegiance(update, ctx)


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
        p = _get_phrase(pid_p)
        txt = p.get("text", "")
        short = txt[:35] + "…" if len(txt) > 35 else txt
        rows.append([InlineKeyboardButton(short, callback_data=f"taunt_send_{pid_p}_{opp_id}")])
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data=f"taunt_cancel_{opp_id}")])

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

    phrase = _get_phrase(phrase_id)
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
            InlineKeyboardButton("🔄 Реванш", callback_data=f"result_rematch_{opp_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu_back"),
        ]])
    )


async def cb_taunt_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """taunt_cancel_{opp_id}"""
    q = update.callback_query
    await q.answer()
    opp_id = int(q.data.split("_")[-1])
    await q.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Реванш", callback_data=f"result_rematch_{opp_id}"),
            InlineKeyboardButton("🏠 Меню", callback_data="menu_back"),
        ]])
    )


# ── In-game taunts ────────────────────────────────────────────────────────────

def _taunt_game_kb(opp_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown while waiting / guessing: just the taunt button."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 Тизер", callback_data=f"taunt_game_{opp_id}"),
    ]])


async def cb_taunt_game_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """taunt_game_{opp_id} — phrase selection during a live game."""
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
        p = _get_phrase(pid_p)
        txt = p.get("text", "")
        short = txt[:35] + "…" if len(txt) > 35 else txt
        rows.append([InlineKeyboardButton(short, callback_data=f"taunt_gsend_{pid_p}_{opp_id}")])
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data=f"taunt_gcancel_{opp_id}")])
    await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))


async def cb_taunt_game_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """taunt_gsend_{phrase_id}_{opp_id} — send taunt during game.
    phrase_id may contain underscores (p_sniper), opp_id is always numeric last segment.
    """
    q = update.callback_query
    uid = q.from_user.id
    # Strip prefix, then split off last segment (opp_id) from right
    suffix = q.data[len("taunt_gsend_"):]          # "p_sniper_123456"
    phrase_id, opp_str = suffix.rsplit("_", 1)      # "p_sniper", "123456"
    opp_id = int(opp_str)

    owned_phrases = db.get_user_cosmetics(uid, "phrase")
    if phrase_id not in owned_phrases:
        await q.answer("Фраза не найдена.", show_alert=True)
        return

    phrase = _get_phrase(phrase_id)
    sender = db.get_user(uid)
    sender_name = _display_name(sender) if sender else "Соперник"
    phrase_text = phrase.get("text", "")

    msg = f"💬 *{_esc(sender_name)}:*\n_{_esc(phrase_text)}_"
    try:
        await ctx.bot.send_message(opp_id, msg, parse_mode=ParseMode.MARKDOWN_V2)
        await q.answer("💬 Отправлено!", show_alert=False)
    except TelegramError:
        await q.answer("Не удалось отправить.", show_alert=True)

    # Restore taunt button so they can taunt again
    await q.edit_message_reply_markup(reply_markup=_taunt_game_kb(opp_id))


async def cb_taunt_game_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """taunt_gcancel_{opp_id} — cancel phrase selection, restore taunt button."""
    q = update.callback_query
    await q.answer()
    opp_id = int(q.data.split("_")[-1])
    await q.edit_message_reply_markup(reply_markup=_taunt_game_kb(opp_id))


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
    await q.edit_message_text(
        HELP_RULES_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_help_rules_kb(),
    )


async def cb_help_fanclubs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        HELP_FANCLUBS_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_help_fanclubs_kb(),
    )


async def cb_help_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        HELP_RULES_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_help_rules_kb(),
    )


async def cb_help_derby(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        HELP_DERBY_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_help_derby_kb(),
    )


async def cb_help_club_switch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        HELP_CLUB_SWITCH_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_help_club_switch_kb(),
    )


async def cb_patch_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        _format_patch_notes(),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_patch_notes_kb(),
    )


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
            f"⚔️ <b>{_display_name_html(user)}</b> вызывает тебя!\n\n"
            f"🏅 Рейтинг: {_hesc(rating_display(user))}\n"
            f"🎮 Игр: {gp_c} | ✅ Побед: {wins_c} | ❌ Поражений: {losses_c}\n"
            f"📊 Винрейт: {_hesc(wr_c)}",
            parse_mode=ParseMode.HTML,
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

    # Remove accept/decline buttons so opponent can't decline after accept
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass

    await clear_state(challenger_id)
    await clear_state(q.from_user.id)
    await _start_game(ctx, challenger, challenged, q.message)


async def cb_challenge_decline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    parts = q.data.split("_")  # challenge_decline_{id}_{challenger_id}
    challenge_id = int(parts[2])
    challenger_id = int(parts[3])

    # Guard: only decline if still pending
    challenge = db.get_challenge(challenge_id)
    if not challenge or challenge["status"] != "pending":
        await q.answer("Этот вызов уже неактуален.", show_alert=True)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass
        return

    await q.answer("Вызов отклонён", show_alert=True)
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

    # ── Derby detection ───────────────────────────────────────────────────────
    a_club = str(player_a.get("club_allegiance") or "")
    b_club = str(player_b.get("club_allegiance") or "")
    derby_level = 0
    derby_name = ""
    derby_total_rounds = TOTAL_ROUNDS
    derby_specials: dict = {}

    if a_club and b_club:
        result = _detect_derby(a_club, b_club)
        if result:
            derby_level, derby_name = result
            if derby_level == 1:
                derby_total_rounds = 8
                derby_specials = {
                    "7": random.choice(["blind", "exchange"]),
                    "8": random.choice(["blind", "exchange"]),
                }
            else:
                derby_total_rounds = TOTAL_ROUNDS

    # each player's own club for derby
    first_derby_club = str(first_player.get("club_allegiance") or "")
    second_derby_club = str(second_player.get("club_allegiance") or "")

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
        f"✅ Первым ходит <b>{_display_name_html(first_player)}</b>!"
    )
    for msg in [coin_msg_a, coin_msg_b]:
        try:
            await msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        except TelegramError:
            pass

    await asyncio.sleep(1.0)

    # Send derby announcement
    if derby_level == 1:
        derby_ann = (
            f"🏆 <b>{derby_name}!</b>\n\n"
            f"Особые правила:\n"
            f"• 8 раундов\n"
            f"• Каждый выбирает трансферы только своего клуба\n"
            f"• Без подсказок\n"
            f"• Очки ×2\n"
            f"• Последние раунды — особые правила"
        )
        for pid in [first_id, second_id]:
            try:
                await ctx.bot.send_message(pid, derby_ann, parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
    elif derby_level == 2:
        derby_ann = f"🏟 <b>Лиговое дерби!</b>\nОчки ×1.5"
        for pid in [first_id, second_id]:
            try:
                await ctx.bot.send_message(pid, derby_ann, parse_mode=ParseMode.HTML)
            except TelegramError:
                pass

    # Create first round
    db.create_round(game_id, 1, first_id, second_id)

    # Common derby fields for state
    derby_fields_first = {
        "derby_level": derby_level,
        "derby_name": derby_name,
        "derby_total_rounds": derby_total_rounds,
        "derby_my_club": first_derby_club,
        "derby_opp_club": second_derby_club,
        "derby_specials": derby_specials,
    }
    derby_fields_second = {
        "derby_level": derby_level,
        "derby_name": derby_name,
        "derby_total_rounds": derby_total_rounds,
        "derby_my_club": second_derby_club,
        "derby_opp_club": first_derby_club,
        "derby_specials": derby_specials,
    }

    if derby_level == 1 and first_derby_club:
        # Level 1 derby: picker goes straight to their club's transfers
        transfers = db.get_transfers_by_club(first_derby_club)
        await set_state(first_id, "picking_transfer", {
            "game_id": game_id,
            "round_num": 1,
            "opponent_id": second_id,
            "club_id": first_derby_club,
            "transfer_ids": [t["id"] for t in transfers],
            "ultras_range_used": False,
            "legend_sc_used": False,
            **derby_fields_first,
        })
        await set_state(second_id, "waiting_for_pick", {
            "game_id": game_id,
            "round_num": 1,
            "picker_id": first_id,
            "opponent_id": first_id,
            "ultras_range_used": False,
            "legend_sc_used": False,
            **derby_fields_second,
        })

        await ctx.bot.send_message(
            first_id,
            f"⚔️ {derby_name} — Раунд <b>1/{derby_total_rounds}</b>\nВыбери трансфер из своего клуба:",
            parse_mode=ParseMode.HTML,
            reply_markup=transfers_kb(transfers, game_id=game_id),
        )
        await ctx.bot.send_message(
            second_id,
            f"⚔️ Раунд <b>1/{derby_total_rounds}</b> — соперник выбирает трансфер своего клуба...",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")]]),
        )
    else:
        # Normal start (or level 2 derby uses normal flow)
        await set_state(first_id, "picking_league", {
            "game_id": game_id,
            "round_num": 1,
            "opponent_id": second_id,
            "ultras_range_used": False,
            "legend_sc_used": False,
            **derby_fields_first,
        })
        await set_state(second_id, "waiting_for_pick", {
            "game_id": game_id,
            "round_num": 1,
            "picker_id": first_id,
            "opponent_id": first_id,
            "ultras_range_used": False,
            "legend_sc_used": False,
            **derby_fields_second,
        })

        # Notify picker
        await ctx.bot.send_message(
            first_id,
            f"⚔️ Игра против <b>{_display_name_html(second_player)}</b>!\n\n"
            f"Раунд <b>1/{derby_total_rounds}</b> — твой ход. Выбери лигу:",
            parse_mode=ParseMode.HTML,
            reply_markup=leagues_kb(game_id=game_id),
        )

        # Notify guesser
        await ctx.bot.send_message(
            second_id,
            f"⚔️ Игра против <b>{_display_name_html(first_player)}</b>!\n\n"
            f"Раунд <b>1/{derby_total_rounds}</b> — соперник выбирает трансфер...",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")]]),
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
        reply_markup=clubs_kb(league_id, game_id=data.get("game_id")),
    )


async def cb_clubs_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    # gcp_{league_id}_{page}
    parts = q.data[4:].rsplit("_", 1)
    league_id, page = parts[0], int(parts[1])
    _, data = await get_state(q.from_user.id)
    await q.edit_message_reply_markup(reply_markup=clubs_kb(league_id, page, game_id=data.get("game_id")))


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
        reply_markup=transfers_kb(transfers, game_id=data.get("game_id")),
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
    # In derby level 1, picker must stay within their club — no going back to leagues
    if data.get("derby_level") == 1:
        await q.answer("⚔️ В дерби ты выбираешь только из своего клуба!", show_alert=True)
        return
    await set_state(user_id, "picking_league", data)
    await q.edit_message_text("Выбери лигу:", reply_markup=leagues_kb(game_id=data.get("game_id")))


def _build_reverse_round(transfer: dict) -> dict | None:
    """Try to build reverse round data. Returns extra state fields or None if impossible."""
    available = []
    if transfer.get("nationality"):
        available.append("nationality")
    if transfer.get("from_club"):
        available.append("from_club")
    if transfer.get("age"):
        available.append("age")
    if not available:
        return None

    attr = random.choice(available)
    correct = str(transfer[attr])

    if REVERSE_ATTRS[attr]["text_input"]:
        # Age — no distractors needed
        return {"is_reverse": True, "reverse_attr": attr, "reverse_correct": correct}

    pool = db.get_distractor_values(attr, correct)
    pool = [x for x in pool if x and x != correct]
    if len(pool) < 3:
        return None  # Not enough distractors — fall back to normal round

    distractors = random.sample(pool, 3)
    options = distractors + [correct]
    random.shuffle(options)
    return {
        "is_reverse": True,
        "reverse_attr": attr,
        "reverse_correct": correct,
        "reverse_options": options,
        "reverse_correct_idx": options.index(correct),
    }


async def _send_reverse_prompt(
    ctx: ContextTypes.DEFAULT_TYPE,
    guesser_id: int,
    transfer: dict,
    round_num: int,
    picker_name: str,
    attr: str,
    options: list[str] | None = None,
) -> None:
    attr_label = REVERSE_ATTRS[attr]["label"]
    fee_str = format_fee(transfer["transfer_fee"])
    player_name = transfer["player_name"]

    text = (
        f"⚡ *ОСОБЫЙ РАУНД\\!*\n\n"
        f"⚽ Раунд *{round_num}/{TOTAL_ROUNDS}*\n"
        f"Трансфер от *{_esc(picker_name)}*\n\n"
        f"👤 Игрок: *{_esc(player_name)}*\n"
        f"💰 Сумма трансфера: *{_esc(fee_str)}*\n\n"
        f"❓ Угадай — {_esc(attr_label)}\\:\n"
    )

    if REVERSE_ATTRS[attr]["text_input"]:
        text += "_Введи возраст числом:_"
        await ctx.bot.send_message(guesser_id, text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        text += "_Выбери правильный ответ:_"
        opts = options or []
        buttons = [
            [InlineKeyboardButton(opts[0], callback_data="rev_ans_0"),
             InlineKeyboardButton(opts[1], callback_data="rev_ans_1")],
            [InlineKeyboardButton(opts[2], callback_data="rev_ans_2"),
             InlineKeyboardButton(opts[3], callback_data="rev_ans_3")],
        ]
        await ctx.bot.send_message(
            guesser_id, text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


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

    # Derby fields from picker's state
    derby_level = data.get("derby_level", 0)
    derby_name = data.get("derby_name", "")
    derby_total_rounds = data.get("derby_total_rounds", TOTAL_ROUNDS)
    derby_specials = data.get("derby_specials", {})
    derby_my_club = data.get("derby_my_club", "")
    derby_opp_club = data.get("derby_opp_club", "")
    derby_special_type = data.get("derby_special_type", "")

    # Check if this is an exchange round
    is_exchange = derby_special_type == "exchange"

    # Switch picker to waiting (carry their ability flags from picking state)
    picker_wait_state: dict = {
        "game_id": game_id,
        "round_num": round_num,
        "opponent_id": opponent_id,
        "ultras_range_used": data.get("ultras_range_used", False),
        "legend_sc_used": data.get("legend_sc_used", False),
        "derby_level": derby_level,
        "derby_name": derby_name,
        "derby_total_rounds": derby_total_rounds,
        "derby_my_club": derby_my_club,
        "derby_opp_club": derby_opp_club,
        "derby_specials": derby_specials,
    }

    # Carry guesser's ability flags from their waiting_for_pick state
    _, guesser_wait_data = await get_state(opponent_id)
    guesser_ultras_used = (guesser_wait_data or {}).get("ultras_range_used", False)
    guesser_sc_used = (guesser_wait_data or {}).get("legend_sc_used", False)
    guesser_derby_my_club = (guesser_wait_data or {}).get("derby_my_club", "")
    guesser_derby_opp_club = (guesser_wait_data or {}).get("derby_opp_club", "")

    # ── 5% chance of a reverse round (only for non-derby or level 2) ──────────
    reverse_extra: dict = {}
    if derby_level == 0 and random.random() < 0.05:
        result = _build_reverse_round(transfer)
        if result:
            reverse_extra = result

    picker = db.get_user(user_id)
    picker_name = picker["display_name"] if picker else "Соперник"
    picker_phrases = db.get_user_cosmetics(user_id, "phrase")
    picker_kb_rows = []
    if picker_phrases:
        picker_kb_rows.append([InlineKeyboardButton("💬 Тизер", callback_data=f"taunt_game_{opponent_id}")])
    picker_kb_rows.append([InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")])
    picker_wait_kb = InlineKeyboardMarkup(picker_kb_rows)

    game = db.get_game(game_id)
    p1_score = game["player1_score"]
    p2_score = game["player2_score"]

    if is_exchange:
        # Exchange round: picker chose transfer but doesn't see the price
        # Store transfer data in picker's state for later comparison
        picker_wait_state["exchange_transfer_id"] = transfer_id
        picker_wait_state["exchange_transfer_fee"] = transfer["transfer_fee"]
        picker_wait_state["exchange_player_name"] = transfer["player_name"]
        await set_state(user_id, "exchange_waiting", picker_wait_state)

        # Guesser gets normal prompt (no hint for derby level 1)
        guesser_state_ex: dict = {
            "game_id": game_id,
            "round_num": round_num,
            "transfer_id": transfer_id,
            "player_name": transfer["player_name"],
            "actual_fee": transfer["transfer_fee"],
            "hints_used": 0,
            "used_hint_types": [],
            "picker_id": user_id,
            "transfer_club_id": str(transfer.get("club_id", "") or ""),
            "ultras_range_used": guesser_ultras_used,
            "legend_sc_used": guesser_sc_used,
            "derby_level": derby_level,
            "derby_name": derby_name,
            "derby_total_rounds": derby_total_rounds,
            "derby_my_club": guesser_derby_my_club,
            "derby_opp_club": guesser_derby_opp_club,
            "derby_specials": derby_specials,
            "derby_special_type": "exchange",
            "is_exchange_guesser": True,
        }
        await set_state(opponent_id, "guessing", guesser_state_ex)

        # Picker sees transfer chosen but NOT the price
        await q.edit_message_text(
            f"⚔️ Раунд обмена!\n\n"
            f"👤 Игрок: <b>{_hesc(transfer['player_name'])}</b>\n"
            f"💰 Цена скрыта — ты тоже будешь угадывать!\n\n"
            f"Ждём ответа соперника...",
            parse_mode=ParseMode.HTML,
            reply_markup=picker_wait_kb,
        )

        # Guesser gets guess prompt
        guesser_user_obj = db.get_user(opponent_id)
        await _send_guess_prompt(
            ctx, opponent_id, transfer, round_num, 0, [], p1_score, p2_score, picker_name,
            picker_id=user_id, game_id=game_id,
            transfer_club_id=str(transfer.get("club_id", "") or ""),
            guesser_user=guesser_user_obj,
            ultras_range_used=guesser_ultras_used,
            derby_level=derby_level,
            is_exchange_round=True,
        )
        return

    # Build guesser state
    guesser_state: dict = {
        "game_id": game_id,
        "round_num": round_num,
        "transfer_id": transfer_id,
        "player_name": transfer["player_name"],
        "actual_fee": transfer["transfer_fee"],
        "hints_used": 0,
        "used_hint_types": [],
        "picker_id": user_id,
        "transfer_club_id": str(transfer.get("club_id", "") or ""),
        "ultras_range_used": guesser_ultras_used,
        "legend_sc_used": guesser_sc_used,
        "derby_level": derby_level,
        "derby_name": derby_name,
        "derby_total_rounds": derby_total_rounds,
        "derby_my_club": guesser_derby_my_club,
        "derby_opp_club": guesser_derby_opp_club,
        "derby_specials": derby_specials,
        "derby_special_type": derby_special_type,
    }
    if reverse_extra:
        guesser_state.update(reverse_extra)

    await set_state(opponent_id, "guessing", guesser_state)
    await set_state(user_id, "waiting_for_guess", picker_wait_state)

    if reverse_extra:
        attr = reverse_extra["reverse_attr"]
        attr_label = REVERSE_ATTRS[attr]["label"]
        await q.edit_message_text(
            f"⚡ *Особый раунд\\!*\n\n"
            f"👤 Игрок: *{_esc(transfer['player_name'])}*\n"
            f"💰 Настоящая цена: *{_esc(format_fee(transfer['transfer_fee']))}*\n\n"
            f"❓ Соперник угадывает: *{_esc(attr_label)}*\n\n"
            f"Ждём ответа соперника\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=picker_wait_kb,
        )
        await _send_reverse_prompt(
            ctx, opponent_id, transfer, round_num, picker_name,
            attr=attr,
            options=reverse_extra.get("reverse_options"),
        )
    else:
        is_blind = derby_special_type == "blind"
        if derby_level == 1 and not is_blind:
            await q.edit_message_text(
                f"✅ Трансфер выбран!\n\n"
                f"👤 Игрок: <b>{_hesc(transfer['player_name'])}</b>\n"
                f"💰 Настоящая цена: <b>{_hesc(format_fee(transfer['transfer_fee']))}</b>\n\n"
                f"Ждём ответа соперника...",
                parse_mode=ParseMode.HTML,
                reply_markup=picker_wait_kb,
            )
        else:
            await q.edit_message_text(
                f"✅ Трансфер выбран\\!\n\n"
                f"👤 Игрок: *{_esc(transfer['player_name'])}*\n"
                f"💰 Настоящая цена: *{_esc(format_fee(transfer['transfer_fee']))}*\n\n"
                f"Ждём ответа соперника\\.\\.\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=picker_wait_kb,
            )
        guesser_user_obj = db.get_user(opponent_id)
        await _send_guess_prompt(
            ctx, opponent_id, transfer, round_num, 0, [], p1_score, p2_score, picker_name,
            picker_id=user_id, game_id=game_id,
            transfer_club_id=str(transfer.get("club_id", "") or ""),
            guesser_user=guesser_user_obj,
            ultras_range_used=guesser_ultras_used,
            derby_level=derby_level,
            is_blind_round=is_blind,
        )


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
    picker_id: int | None = None,
    game_id: int | None = None,
    transfer_club_id: str = "",
    guesser_user: dict | None = None,
    ultras_range_used: bool = False,
    derby_level: int = 0,
    is_blind_round: bool = False,
    is_exchange_round: bool = False,
) -> None:
    # Derby level 1: no hints allowed
    if derby_level == 1:
        can_hint = False
    else:
        can_hint = hints_used < MAX_HINTS

    # Determine the total rounds to display
    # (We'll just use TOTAL_ROUNDS as a default display; derby changes come from state)
    # The round_num is always correct from state
    hint_lines = _build_hint_lines(transfer, used_hint_types)

    # Blind round: hide player name
    display_name = "????" if is_blind_round else transfer["player_name"]

    if is_blind_round:
        text = (
            f"⚽ Раунд *{round_num}* ⚡ *СЛЕПОЙ РАУНД\\!*\n"
            f"Трансфер от *{_esc(picker_name)}*\n\n"
            f"👤 Игрок: *????*\n"
        )
    elif is_exchange_round:
        text = (
            f"⚔️ *РАУНД ОБМЕНА\\!*\n\n"
            f"⚽ Раунд *{round_num}*\n"
            f"👤 Игрок: *{_esc(transfer['player_name'])}*\n"
        )
    else:
        text = (
            f"⚽ Раунд *{round_num}*\n"
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

    # Ультрас ability: show range button if eligible (not for derby level 1)
    if (
        derby_level != 1
        and not ultras_range_used
        and transfer_club_id
        and guesser_user
        and str(guesser_user.get("club_allegiance") or "") == transfer_club_id
    ):
        fan_count = db.get_club_guess_count(guesser_id, transfer_club_id)
        lv_label, _, _, _ = _club_loyalty(fan_count)
        if lv_label in ("Ультрас", "Легенда"):
            kb_rows.append([InlineKeyboardButton("🔥 Диапазон цены", callback_data="ultras_range")])

    if can_hint:
        available = [h for h in HINT_TYPES if h not in used_hint_types]
        for h in available:
            kb_rows.append([InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"gh_{h}")])

    # Add taunt button if guesser has phrases and we know who the picker is
    if picker_id:
        guesser_phrases = db.get_user_cosmetics(guesser_id, "phrase")
        if guesser_phrases:
            kb_rows.append([InlineKeyboardButton("💬 Тизер", callback_data=f"taunt_game_{picker_id}")])

    # Surrender button
    if game_id:
        kb_rows.append([InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")])

    kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None
    # For blind round we don't show the player photo (would reveal identity)
    photo_url = None if is_blind_round else transfer.get("photo_url")
    await _send_photo_message(ctx, guesser_id, photo_url, text, kb)


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


# ── Ultras range ability callback ─────────────────────────────────────────────

async def cb_ultras_range(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user_id = q.from_user.id
    action, data = await get_state(user_id)

    if action != "guessing":
        await q.answer("Сейчас не твоя очередь угадывать.", show_alert=True)
        return

    if data.get("ultras_range_used"):
        await q.answer("Способность уже использована в этой игре.", show_alert=True)
        return

    transfer_club_id = data.get("transfer_club_id", "")
    guesser_user = db.get_user(user_id)
    if not (
        transfer_club_id
        and guesser_user
        and str(guesser_user.get("club_allegiance") or "") == transfer_club_id
    ):
        await q.answer("Эта способность доступна только для трансферов твоего клуба.", show_alert=True)
        return

    fan_count = db.get_club_guess_count(user_id, transfer_club_id)
    lv_label, _, _, _ = _club_loyalty(fan_count)
    if lv_label not in ("Ультрас", "Легенда"):
        await q.answer("Недостаточный уровень преданности.", show_alert=True)
        return

    actual_fee = data["actual_fee"]
    lo = int(actual_fee * 0.75)
    hi = int(actual_fee * 1.25)

    data["ultras_range_used"] = True
    await set_state(user_id, "guessing", data)

    await q.answer()
    await ctx.bot.send_message(
        user_id,
        f"🔥 <b>Инсайд Ультраса</b>\n\n"
        f"Трансфер в диапазоне: <b>{format_fee(lo)} — {format_fee(hi)}</b>",
        parse_mode=ParseMode.HTML,
    )


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

    # Update keyboard — remove used hint, keep remaining + preserve taunt/surrender buttons
    remaining = [h for h in HINT_TYPES if h not in used]
    kb_rows = [[InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"gh_{h}")] for h in remaining]
    picker_id = data.get("picker_id")
    if picker_id:
        guesser_phrases = db.get_user_cosmetics(user_id, "phrase")
        if guesser_phrases:
            kb_rows.append([InlineKeyboardButton("💬 Тизер", callback_data=f"taunt_game_{picker_id}")])
    game_id_h = data.get("game_id")
    if game_id_h:
        kb_rows.append([InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id_h}")])
    try:
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None)
    except TelegramError:
        pass


# ── Text input router ─────────────────────────────────────────────────────────

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    action, data = await get_state(user_id)

    # One-time update notification (skip during registration to avoid interrupting flow)
    if action != "registering":
        await _maybe_notify_update(user_id, ctx)

    if action == "registering":
        await _handle_registration(update, text)
    elif action == "guessing":
        await _handle_guess(update, ctx, text, data)
    elif action == "exchange_guessing_picker":
        await _handle_exchange_picker_guess(update, ctx, text, data)
    elif action == "training_guessing":
        await _handle_training_guess(update, ctx, text, data)
    elif action in ("dbg_set_coins", "dbg_set_rating") or (
        action.startswith(("dbg_editt_", "dbg_editp_")) and _is_superadmin(user_id)
    ):
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

async def _advance_round(
    ctx: ContextTypes.DEFAULT_TYPE,
    *,
    game_id: int,
    round_num: int,
    new_picker_id: int,
    new_guesser_id: int,
    p1_id: int,
    p2_id: int,
    p1_score: int,
    p2_score: int,
    guesser_id: int,
    picker_id: int,
    guesser_data: dict,
    picker_action: str,
    picker_data: dict,
) -> None:
    """Advance to next round or finish game. Called after a round is fully resolved."""
    next_round = round_num + 1

    # Use derby_total_rounds from guesser_data if present
    derby_total_rounds = guesser_data.get("derby_total_rounds", TOTAL_ROUNDS)
    derby_level = guesser_data.get("derby_level", 0)
    derby_name = guesser_data.get("derby_name", "")
    derby_specials = guesser_data.get("derby_specials", {})

    if next_round > derby_total_rounds:
        await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
        return

    db.create_round(game_id, next_round, new_picker_id, new_guesser_id)
    db.update_game(game_id, current_round=next_round)

    # Carry ability flags:
    # new_picker (was guesser) — use their guessing data flags
    new_picker_ultras_used = guesser_data.get("ultras_range_used", False)
    new_picker_sc_used = guesser_data.get("legend_sc_used", False)

    # new_guesser (was picker) — use their picking_league data flags
    new_guesser_ultras_used = picker_data.get("ultras_range_used", False)
    new_guesser_sc_used = picker_data.get("legend_sc_used", False)

    # Derby fields: each player carries their own club
    # new_picker was the guesser — use guesser_data for their club
    new_picker_derby_club = guesser_data.get("derby_my_club", "")
    new_picker_opp_club = guesser_data.get("derby_opp_club", "")
    # new_guesser was the picker — use picker_data for their club
    new_guesser_derby_club = picker_data.get("derby_my_club", "")
    new_guesser_opp_club = picker_data.get("derby_opp_club", "")

    derby_fields_picker = {
        "derby_level": derby_level,
        "derby_name": derby_name,
        "derby_total_rounds": derby_total_rounds,
        "derby_my_club": new_picker_derby_club,
        "derby_opp_club": new_picker_opp_club,
        "derby_specials": derby_specials,
    }
    derby_fields_guesser = {
        "derby_level": derby_level,
        "derby_name": derby_name,
        "derby_total_rounds": derby_total_rounds,
        "derby_my_club": new_guesser_derby_club,
        "derby_opp_club": new_guesser_opp_club,
        "derby_specials": derby_specials,
    }

    my_score_picker = p1_score if new_picker_id == p1_id else p2_score
    opp_score_picker = p2_score if new_picker_id == p1_id else p1_score
    my_score_guesser = p1_score if new_guesser_id == p1_id else p2_score
    opp_score_guesser = p2_score if new_guesser_id == p1_id else p1_score

    # Check if the upcoming round is a special derby round
    special_type = derby_specials.get(str(next_round), "") if derby_level == 1 else ""

    if derby_level == 1 and new_picker_derby_club:
        # Level 1 derby: picker goes straight to their club's transfers
        picker_state: dict = {
            "game_id": game_id,
            "round_num": next_round,
            "opponent_id": new_guesser_id,
            "ultras_range_used": new_picker_ultras_used,
            "legend_sc_used": new_picker_sc_used,
            "club_id": new_picker_derby_club,
            **derby_fields_picker,
        }
        if special_type:
            picker_state["derby_special_type"] = special_type

        guesser_state: dict = {
            "game_id": game_id,
            "round_num": next_round,
            "picker_id": new_picker_id,
            "opponent_id": new_picker_id,
            "ultras_range_used": new_guesser_ultras_used,
            "legend_sc_used": new_guesser_sc_used,
            **derby_fields_guesser,
        }
        if special_type:
            guesser_state["derby_special_type"] = special_type

        transfers = db.get_transfers_by_club(new_picker_derby_club)
        picker_state["transfer_ids"] = [t["id"] for t in transfers]

        await set_state(new_picker_id, "picking_transfer", picker_state)
        await set_state(new_guesser_id, "waiting_for_pick", guesser_state)

        await ctx.bot.send_message(
            new_picker_id,
            f"📊 Счёт: {my_score_picker} — {opp_score_picker}\n\n"
            f"⚔️ {derby_name} — Раунд <b>{next_round}/{derby_total_rounds}</b>\n"
            f"Выбери трансфер из своего клуба:",
            parse_mode=ParseMode.HTML,
            reply_markup=transfers_kb(transfers, game_id=game_id),
        )
        await ctx.bot.send_message(
            new_guesser_id,
            f"📊 Счёт: {my_score_guesser} — {opp_score_guesser}\n\n"
            f"⚔️ Раунд <b>{next_round}/{derby_total_rounds}</b> — соперник выбирает трансфер своего клуба...",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")]]),
        )
    else:
        await set_state(new_picker_id, "picking_league", {
            "game_id": game_id,
            "round_num": next_round,
            "opponent_id": new_guesser_id,
            "ultras_range_used": new_picker_ultras_used,
            "legend_sc_used": new_picker_sc_used,
            **derby_fields_picker,
        })
        await set_state(new_guesser_id, "waiting_for_pick", {
            "game_id": game_id,
            "round_num": next_round,
            "picker_id": new_picker_id,
            "opponent_id": new_picker_id,
            "ultras_range_used": new_guesser_ultras_used,
            "legend_sc_used": new_guesser_sc_used,
            **derby_fields_guesser,
        })

        round_label = f"{next_round}/{derby_total_rounds}"
        await ctx.bot.send_message(
            new_picker_id,
            f"📊 Счёт: *{my_score_picker}* — *{opp_score_picker}*\n\n"
            f"Раунд *{round_label}* — твой ход\\. Выбери лигу:",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=leagues_kb(game_id=game_id),
        )

        await ctx.bot.send_message(
            new_guesser_id,
            f"📊 Счёт: *{my_score_guesser}* — *{opp_score_guesser}*\n\n"
            f"Раунд *{round_label}* — соперник выбирает трансфер\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏳 Сдаться", callback_data=f"game_surrender_{game_id}")]]),
        )


async def _handle_reverse_age(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    guessed_age: int,
    data: dict,
) -> None:
    """Handle text input for a reverse round where attr=age."""
    user_id = update.effective_user.id
    correct_age = int(data["reverse_correct"])
    diff = abs(guessed_age - correct_age)

    if diff == 0:
        points, tier_msg = 5, "🎯 Точно\\!"
    elif diff == 1:
        points, tier_msg = 3, "🔥 Рядом\\!"
    elif diff <= 2:
        points, tier_msg = 1, "😅 Почти\\!"
    else:
        points, tier_msg = 0, "❌ Мимо\\!"

    # Derby multiplier
    derby_level_ra = data.get("derby_level", 0)
    if derby_level_ra == 1:
        points = points * 2
    elif derby_level_ra == 2:
        points = int(points * 1.5)

    game_id    = data["game_id"]
    round_num  = data["round_num"]
    picker_id  = data["picker_id"]
    player_name = data["player_name"]
    actual_fee  = data["actual_fee"]

    round_row = db.get_round(game_id, round_num)
    if round_row:
        db.update_round(
            round_row["id"],
            guess_amount=guessed_age,
            accuracy_tier="exact" if diff == 0 else ("close" if diff <= 2 else "miss"),
            points_earned=points,
            hints_used=0,
            hint_types=[],
            completed=True,
        )

    game   = db.get_game(game_id)
    p1_id  = game["player1_id"]
    p2_id  = game["player2_id"]
    p1_score = game["player1_score"]
    p2_score = game["player2_score"]
    if user_id == p1_id:
        p1_score += points
    else:
        p2_score += points
    db.update_game(game_id, player1_score=p1_score, player2_score=p2_score)

    card = (
        f"{tier_msg}\n\n"
        f"👤 *{_esc(player_name)}*\n"
        f"💰 Сумма: *{_esc(format_fee(actual_fee))}*\n"
        f"🎂 Возраст: *{correct_age}*\n"
        f"🎯 Твой ответ: *{guessed_age}*\n"
        f"📊 Очки: *\\+{points}*"
    )
    await update.message.reply_text(card, parse_mode=ParseMode.MARKDOWN_V2)
    try:
        await ctx.bot.send_message(
            picker_id,
            f"{tier_msg}\n\n"
            f"👤 *{_esc(player_name)}*\n"
            f"💰 Сумма: *{_esc(format_fee(actual_fee))}*\n"
            f"🎂 Возраст соперника: *{correct_age}*\n"
            f"🎯 Ответ соперника: *{guessed_age}*\n"
            f"📊 Очки: *\\+{points}*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except TelegramError:
        pass

    picker_action_now, picker_data_now = await get_state(picker_id)
    await clear_state(user_id)

    next_round = round_num + 1
    derby_total_rounds_ra = data.get("derby_total_rounds", TOTAL_ROUNDS)
    if next_round > derby_total_rounds_ra:
        await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
    else:
        await _advance_round(
            ctx,
            game_id=game_id,
            round_num=round_num,
            new_picker_id=user_id,
            new_guesser_id=picker_id,
            p1_id=p1_id,
            p2_id=p2_id,
            p1_score=p1_score,
            p2_score=p2_score,
            guesser_id=user_id,
            picker_id=picker_id,
            guesser_data=data,
            picker_action=picker_action_now or "",
            picker_data=picker_data_now or {},
        )


async def _handle_guess(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    text: str,
    data: dict,
) -> None:
    user_id = update.effective_user.id

    # ── Reverse round intercept ───────────────────────────────────────────────
    if data.get("is_reverse"):
        attr = data.get("reverse_attr", "")
        if attr == "age":
            try:
                guessed_age = int(text.strip())
                if not (10 <= guessed_age <= 50):
                    raise ValueError
            except ValueError:
                await update.message.reply_text(
                    "Введи возраст числом, например: *27*",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return
            await _handle_reverse_age(update, ctx, guessed_age, data)
        else:
            await update.message.reply_text(
                "⬆️ Выбери ответ кнопкой выше",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        return

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

    # ── Second-chance (Легенда) second guess path ────────────────────────────
    if data.get("sc_pending"):
        tier2, points2 = calculate_points(guess, actual_fee, hints_used)
        _derby_lvl_sc = data.get("derby_level", 0)
        if _derby_lvl_sc == 1:
            points2 = points2 * 2
        elif _derby_lvl_sc == 2:
            points2 = int(points2 * 1.5)
        sc_first = data.get("sc_first_data", {})
        points1 = sc_first.get("points", 0)  # already multiplied when stored
        tier1 = sc_first.get("tier", "miss")

        # Use the better result
        if points2 >= points1:
            tier, points = tier2, points2
            winning_guess = guess
        else:
            tier, points = tier1, points1
            winning_guess = sc_first.get("guess", guess)

        effect = tier_effect(tier, points)
        await update.message.reply_text(
            f"{effect}\n\n"
            f"👤 *{_esc(player_name)}*\n"
            f"✅ Правильная цена: *{_esc(format_fee(actual_fee))}*\n"
            f"🎯 Лучший ответ: *{_esc(format_fee(winning_guess))}*\n"
            f"_Второй шанс использован_",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        # Mark sc used, clear sc_pending
        data["sc_pending"] = False
        data["legend_sc_used"] = True

        # Update round in DB
        round_row = db.get_round(game_id, round_num)
        if round_row:
            dev = abs(winning_guess - actual_fee) / actual_fee * 100 if actual_fee else 0
            db.update_round(
                round_row["id"],
                guess_amount=winning_guess,
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

        # Notify picker of result
        try:
            await ctx.bot.send_message(
                picker_id,
                f"{effect}\n\n"
                f"👤 *{_esc(player_name)}*\n"
                f"✅ Правильная цена: *{_esc(format_fee(actual_fee))}*\n"
                f"🎯 Ответ соперника: *{_esc(format_fee(winning_guess))}*\n"
                f"_Соперник использовал Второй шанс_",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except TelegramError:
            pass

        # Get picker's state data for flag carry
        picker_action_now, picker_data_now = await get_state(picker_id)

        await clear_state(user_id)

        next_round = round_num + 1
        _derby_total_sc = data.get("derby_total_rounds", TOTAL_ROUNDS)
        if next_round > _derby_total_sc:
            await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
        else:
            await _advance_round(
                ctx,
                game_id=game_id,
                round_num=round_num,
                new_picker_id=user_id,
                new_guesser_id=picker_id,
                p1_id=p1_id,
                p2_id=p2_id,
                p1_score=p1_score,
                p2_score=p2_score,
                guesser_id=user_id,
                picker_id=picker_id,
                guesser_data=data,
                picker_action=picker_action_now or "",
                picker_data=picker_data_now or {},
            )
        return

    tier, points = calculate_points(guess, actual_fee, hints_used)

    # ── Derby points multiplier ───────────────────────────────────────────────
    derby_level = data.get("derby_level", 0)
    if derby_level == 1:
        points = points * 2
    elif derby_level == 2:
        points = int(points * 1.5)

    # ── Exchange round: guesser answered first ────────────────────────────────
    if data.get("is_exchange_guesser"):
        # Guard: if guesser already answered, ignore duplicate messages
        if data.get("exchange_answered"):
            await update.message.reply_text(
                "⏳ Ответ уже принят\\. Ждём соперника\\.\\.\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        # Save guesser result into picker's exchange_waiting state
        picker_id_ex = data["picker_id"]
        _, picker_ex_data = await get_state(picker_id_ex)
        if picker_ex_data:
            picker_ex_data["exchange_guesser_tier"] = tier
            picker_ex_data["exchange_guesser_points"] = points
            picker_ex_data["exchange_guesser_guess"] = guess
            await set_state(picker_id_ex, "exchange_waiting", picker_ex_data)

        # Tell guesser to wait
        await update.message.reply_text(
            "🎯 Ответ принят\\! Ждём пока соперник тоже угадает\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        # Move picker to exchange_guessing_picker
        actual_fee_ex = data["actual_fee"]
        player_name_ex = data["player_name"]

        # Update guesser state: mark that they answered
        data["exchange_answered"] = True
        await set_state(user_id, "guessing", data)

        # Build picker guess state
        picker_ex_state: dict = dict(picker_ex_data or {})
        picker_ex_state["action_type"] = "exchange_guessing_picker"
        picker_ex_state["transfer_id"] = data["transfer_id"]
        picker_ex_state["actual_fee"] = actual_fee_ex
        picker_ex_state["player_name"] = player_name_ex
        picker_ex_state["guesser_id_ref"] = user_id
        picker_ex_state["hints_used"] = 0
        picker_ex_state["used_hint_types"] = []
        await set_state(picker_id_ex, "exchange_guessing_picker", picker_ex_state)

        transfer_ex = db.get_transfer(data["transfer_id"])
        await ctx.bot.send_message(
            picker_id_ex,
            f"⚔️ Твоя очередь\\! Угадай цену:\n"
            f"👤 *{_esc(player_name_ex)}*\n\n"
            f"💰 Назови сумму трансфера \\(в евро\\)\\:\n"
            f"_Например: 45M, 45000000, 500K_",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # ── Club allegiance: track correct guesses & apply fan bonus ─────────────
    fan_bonus_coins = 0
    fan_bonus_club_name: str | None = None
    if tier != "miss":
        transfer_row = db.get_transfer(transfer_id)
        t_club_id = str(transfer_row.get("club_id", "")) if transfer_row else ""
        if t_club_id:
            new_count = db.increment_club_guess(user_id, t_club_id)

            # Notify on unlock milestones
            clubs_res = db.get_client().table("clubs").select("club_name").eq("club_id", t_club_id).execute()
            _cname_club = clubs_res.data[0]["club_name"] if clubs_res.data else t_club_id
            emblem = club_emblem_html(t_club_id) if has_emblem(t_club_id) else "🏟"
            _, lv_emoji, _, _ = _club_loyalty(new_count)

            if new_count == 5:
                try:
                    await ctx.bot.send_message(
                        user_id,
                        f"🔓 <b>Клуб разблокирован!</b>\n\n"
                        f"{emblem} <b>{_hesc(_cname_club)}</b>\n\n"
                        f"Ты угадал 5 трансферов этого клуба — теперь можешь стать его фанатом!\n"
                        f"<i>Профиль → Зал болельщика → Выбрать клуб-фан</i>",
                        parse_mode="HTML",
                    )
                except TelegramError:
                    pass

            elif new_count in (15, 30, 50):
                lv_label, lv_emoji2, new_bonus, _ = _club_loyalty(new_count)
                try:
                    await ctx.bot.send_message(
                        user_id,
                        f"{lv_emoji2} <b>Новый уровень преданности!</b>\n\n"
                        f"{emblem} <b>{_hesc(_cname_club)}</b>\n"
                        f"Уровень: {lv_emoji2} <b>{_hesc(lv_label)}</b>\n\n"
                        f"Бонус за угадывание из этого клуба: <b>+{new_bonus} монет</b>",
                        parse_mode="HTML",
                    )
                except TelegramError:
                    pass

            # Achievement: Преданный фанат (25 угаданных из одного клуба)
            if new_count == 25:
                if "club_fan_25" not in db.get_user_achievements(user_id):
                    db.add_user_achievement(user_id, "club_fan_25")
                    ach = ACHIEVEMENTS["club_fan_25"]
                    if ach.get("reward"):
                        db.add_coins(user_id, ach["reward"])
                    try:
                        await ctx.bot.send_message(
                            user_id,
                            f"🏆 <b>Достижение разблокировано!</b>\n\n"
                            f"{ach['emoji']} <b>{_hesc(ach['name'])}</b>\n"
                            f"<i>{_hesc(ach['desc'])}</i>\n\n"
                            f"💰 +{ach['reward']:,} монет!",
                            parse_mode="HTML",
                        )
                    except TelegramError:
                        pass

            # Fan bonus: динамический на основе уровня преданности
            guesser_user = db.get_user(user_id)
            if guesser_user and str(guesser_user.get("club_allegiance") or "") == t_club_id:
                _, _, fan_bonus_coins, _ = _club_loyalty(new_count)
                fan_bonus_club_name = _cname_club

    # ── Легенда second-chance check (before writing round to DB) ─────────────
    transfer_club_id = data.get("transfer_club_id", "")
    legend_sc_used = data.get("legend_sc_used", False)
    sc_eligible = False
    if not legend_sc_used and tier != "exact" and transfer_club_id:
        guesser_user_sc = db.get_user(user_id)
        if guesser_user_sc and str(guesser_user_sc.get("club_allegiance") or "") == transfer_club_id:
            fan_count_sc = db.get_club_guess_count(user_id, transfer_club_id)
            lv_label_sc, _, _, _ = _club_loyalty(fan_count_sc)
            if lv_label_sc == "Легенда":
                sc_eligible = True

    if sc_eligible:
        # Send picker normal result (with price)
        effect = tier_effect(tier, points)
        dev_pct = abs(guess - actual_fee) / actual_fee * 100 if actual_fee else 0
        try:
            await ctx.bot.send_message(
                picker_id,
                f"{effect}\n\n"
                f"👤 *{_esc(player_name)}*\n"
                f"✅ Правильная цена: *{_esc(format_fee(actual_fee))}*\n"
                f"🎯 Ответ соперника: *{_esc(format_fee(guess))}*\n"
                f"_Соперник запросил Второй шанс_",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except TelegramError:
            pass

        # Save sc_pending state (don't clear, don't write round to DB yet)
        data["sc_pending"] = True
        data["sc_first_data"] = {
            "tier": tier,
            "points": points,
            "guess": guess,
            "hints_used": hints_used,
            "used_hint_types": used_hint_types,
        }
        await set_state(user_id, "guessing", data)

        # Send guesser a blind result + choice buttons
        sc_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Второй шанс", callback_data="sc_use")],
            [InlineKeyboardButton("👁 Показать ответ", callback_data="sc_skip")],
        ])
        await update.message.reply_text(
            f"{effect}\n\n"
            f"👤 *{_esc(player_name)}*\n"
            f"🎯 Твой ответ: *{_esc(format_fee(guess))}*\n"
            f"❌ Ошибка: ~{dev_pct:.0f}%\n"
            f"💰 Правильная цена: _скрыта_\n\n"
            f"🏆 *Легенда* — у тебя есть второй шанс\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=sc_kb,
        )
        return  # Round advancement happens after second chance is resolved

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

    # Credit fan bonus coins now so result card reflects it
    if fan_bonus_coins > 0:
        db.add_coins(user_id, fan_bonus_coins)

    # Result card shown to both players
    def _result_card(is_guesser: bool) -> str:
        card = (
            f"{effect}\n\n"
            f"👤 *{_esc(player_name)}*\n"
            f"✅ Правильная цена: *{_esc(format_fee(actual_fee))}*\n"
            f"🎯 {'Твой ответ' if is_guesser else 'Ответ соперника'}: *{_esc(format_fee(guess))}*"
        )
        if hints_used:
            card += f"\n💡 Подсказок использовано: {hints_used} \\(\\-{hints_used} к очкам\\)"
        if is_guesser and fan_bonus_coins > 0 and fan_bonus_club_name:
            card += f"\n⭐ Бонус фаната *{_esc(fan_bonus_club_name)}*\\: \\+{fan_bonus_coins} монет"
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

    # Get picker's state data for flag carry
    picker_action_now, picker_data_now = await get_state(picker_id)

    await clear_state(user_id)

    # Advance to next round or finish
    next_round = round_num + 1
    _derby_total_hg2 = data.get("derby_total_rounds", TOTAL_ROUNDS)
    if next_round > _derby_total_hg2:
        await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
    else:
        await _advance_round(
            ctx,
            game_id=game_id,
            round_num=round_num,
            new_picker_id=user_id,
            new_guesser_id=picker_id,
            p1_id=p1_id,
            p2_id=p2_id,
            p1_score=p1_score,
            p2_score=p2_score,
            guesser_id=user_id,
            picker_id=picker_id,
            guesser_data=data,
            picker_action=picker_action_now or "",
            picker_data=picker_data_now or {},
        )


# ── Second-chance callbacks (Легенда ability) ─────────────────────────────────

async def cb_sc_use(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Guesser chose to use the second chance — prompt for new guess."""
    q = update.callback_query
    user_id = q.from_user.id
    action, data = await get_state(user_id)

    if action != "guessing" or not data.get("sc_pending"):
        await q.answer("Второй шанс недоступен.", show_alert=True)
        return

    await q.answer()
    await q.edit_message_reply_markup(reply_markup=None)
    await ctx.bot.send_message(
        user_id,
        "🎯 Введи новую сумму трансфера \\(в евро\\)\\:\n_Например: 45M, 45000000, 500K_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cb_sc_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Guesser chose to skip second chance — reveal price and advance round."""
    q = update.callback_query
    user_id = q.from_user.id
    action, data = await get_state(user_id)

    if action != "guessing" or not data.get("sc_pending"):
        await q.answer("Второй шанс недоступен.", show_alert=True)
        return

    await q.answer()
    await q.edit_message_reply_markup(reply_markup=None)

    actual_fee = data["actual_fee"]
    hints_used = data.get("hints_used", 0)
    used_hint_types = data.get("used_hint_types", [])
    game_id = data["game_id"]
    round_num = data["round_num"]
    picker_id = data["picker_id"]
    player_name = data["player_name"]

    sc_first = data.get("sc_first_data", {})
    tier = sc_first.get("tier", "miss")
    points = sc_first.get("points", 0)
    guess = sc_first.get("guess", 0)
    effect = tier_effect(tier, points)

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

    # Reveal price to guesser
    await ctx.bot.send_message(
        user_id,
        f"{effect}\n\n"
        f"👤 *{_esc(player_name)}*\n"
        f"✅ Правильная цена: *{_esc(format_fee(actual_fee))}*\n"
        f"🎯 Твой ответ: *{_esc(format_fee(guess))}*",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # Get picker's state data for flag carry
    picker_action_now, picker_data_now = await get_state(picker_id)

    await clear_state(user_id)

    # Advance to next round or finish
    next_round = round_num + 1
    _derby_total_sc2 = data.get("derby_total_rounds", TOTAL_ROUNDS)
    if next_round > _derby_total_sc2:
        await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
    else:
        await _advance_round(
            ctx,
            game_id=game_id,
            round_num=round_num,
            new_picker_id=user_id,
            new_guesser_id=picker_id,
            p1_id=p1_id,
            p2_id=p2_id,
            p1_score=p1_score,
            p2_score=p2_score,
            guesser_id=user_id,
            picker_id=picker_id,
            guesser_data=data,
            picker_action=picker_action_now or "",
            picker_data=picker_data_now or {},
        )


# ── Exchange round picker-guess handler ───────────────────────────────────────

async def _handle_exchange_picker_guess(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    text: str,
    data: dict,
) -> None:
    """Handle picker's guess in an exchange round."""
    user_id = update.effective_user.id

    guess = parse_fee_input(text)
    if guess is None:
        await update.message.reply_text(
            "Не могу распознать сумму\\. Примеры: `45M`, `45000000`, `500K`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    actual_fee = data["actual_fee"]
    player_name = data["player_name"]
    game_id = data["game_id"]
    round_num = data["round_num"]
    guesser_id_ref = data.get("guesser_id_ref")
    derby_level = data.get("derby_level", 1)

    # Calculate picker's result
    tier_p, points_p = calculate_points(guess, actual_fee, 0)
    if derby_level == 1:
        points_p = points_p * 2
    elif derby_level == 2:
        points_p = int(points_p * 1.5)

    # Get guesser's stored result
    guesser_guess = data.get("exchange_guesser_guess", 0)
    guesser_points = data.get("exchange_guesser_points", 0)
    guesser_tier = data.get("exchange_guesser_tier", "miss")

    # Compare accuracy
    picker_err = abs(guess - actual_fee) / actual_fee if actual_fee else float("inf")
    guesser_err = abs(guesser_guess - actual_fee) / actual_fee if actual_fee else float("inf")

    bonus_picker = 0
    bonus_guesser = 0
    if picker_err < guesser_err:
        bonus_picker = 5
        outcome_picker = "🏆 Ты точнее! +5 бонус"
        outcome_guesser = "❌ Соперник точнее"
    elif guesser_err < picker_err:
        bonus_guesser = 5
        outcome_picker = "❌ Соперник точнее"
        outcome_guesser = "🏆 Ты точнее! +5 бонус"
    else:
        bonus_picker = 2
        bonus_guesser = 2
        outcome_picker = "🤝 Ничья! +2 бонус"
        outcome_guesser = "🤝 Ничья! +2 бонус"

    points_p += bonus_picker
    final_guesser_points = guesser_points + bonus_guesser

    # Update game scores
    game = db.get_game(game_id)
    p1_id = game["player1_id"]
    p2_id = game["player2_id"]
    p1_score = game["player1_score"]
    p2_score = game["player2_score"]

    # guesser_id_ref is the guesser
    if guesser_id_ref == p1_id:
        p1_score += final_guesser_points
        p2_score += points_p
    else:
        p1_score += points_p
        p2_score += final_guesser_points
    db.update_game(game_id, player1_score=p1_score, player2_score=p2_score)

    # Write round to DB (using picker's total points)
    round_row = db.get_round(game_id, round_num)
    if round_row:
        dev = abs(guesser_guess - actual_fee) / actual_fee * 100 if actual_fee else 0
        db.update_round(
            round_row["id"],
            guess_amount=guesser_guess,
            accuracy_percent=round(dev, 2),
            accuracy_tier=guesser_tier,
            points_earned=final_guesser_points,
            hints_used=0,
            hint_types=[],
            completed=True,
        )

    # Send results to both players
    msg_picker = (
        f"⚔️ *Раунд обмена — итог*\n\n"
        f"👤 *{_esc(player_name)}*\n"
        f"✅ Цена: *{_esc(format_fee(actual_fee))}*\n\n"
        f"Твой ответ: *{_esc(format_fee(guess))}* → *\\+{points_p}* очков\n"
        f"Соперник: *{_esc(format_fee(guesser_guess))}* → *\\+{final_guesser_points}* очков\n"
        f"{_esc(outcome_picker)}"
    )
    msg_guesser = (
        f"⚔️ *Раунд обмена — итог*\n\n"
        f"👤 *{_esc(player_name)}*\n"
        f"✅ Цена: *{_esc(format_fee(actual_fee))}*\n\n"
        f"Твой ответ: *{_esc(format_fee(guesser_guess))}* → *\\+{final_guesser_points}* очков\n"
        f"Соперник: *{_esc(format_fee(guess))}* → *\\+{points_p}* очков\n"
        f"{_esc(outcome_guesser)}"
    )

    await update.message.reply_text(msg_picker, parse_mode=ParseMode.MARKDOWN_V2)
    if guesser_id_ref:
        try:
            await ctx.bot.send_message(guesser_id_ref, msg_guesser, parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramError:
            pass

    # Advance round: picker was the "picker" in the original round
    # After exchange, the new picker is the guesser (roles swap)
    picker_action_now, picker_data_now = await get_state(user_id)
    await clear_state(user_id)
    if guesser_id_ref:
        await clear_state(guesser_id_ref)

    next_round = round_num + 1
    _derby_total_ex = data.get("derby_total_rounds", TOTAL_ROUNDS)
    if next_round > _derby_total_ex:
        await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
    else:
        # After exchange: the guesser (who answered first) becomes new picker
        # The picker (who just answered) becomes new guesser
        # We need to reconstruct guesser_data from what we have in data
        guesser_data_adv = {
            "derby_level": data.get("derby_level", 1),
            "derby_name": data.get("derby_name", ""),
            "derby_total_rounds": data.get("derby_total_rounds", TOTAL_ROUNDS),
            "derby_my_club": data.get("derby_opp_club", ""),   # guesser's club (stored as opp in picker data)
            "derby_opp_club": data.get("derby_my_club", ""),
            "derby_specials": data.get("derby_specials", {}),
            "ultras_range_used": False,
            "legend_sc_used": False,
        }
        await _advance_round(
            ctx,
            game_id=game_id,
            round_num=round_num,
            new_picker_id=guesser_id_ref or user_id,
            new_guesser_id=user_id,
            p1_id=p1_id,
            p2_id=p2_id,
            p1_score=p1_score,
            p2_score=p2_score,
            guesser_id=guesser_id_ref or user_id,
            picker_id=user_id,
            guesser_data=guesser_data_adv,
            picker_action=picker_action_now or "",
            picker_data=picker_data_now or {},
        )


# ── Reverse round answer callback ─────────────────────────────────────────────

async def cb_reverse_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """rev_ans_<0-3> — guesser picked one of the 4 MC options in a reverse round."""
    q = update.callback_query
    user_id = q.from_user.id
    action, data = await get_state(user_id)

    if action != "guessing" or not data.get("is_reverse"):
        await q.answer("Сейчас не твоя очередь.", show_alert=True)
        return

    attr = data.get("reverse_attr", "")
    if REVERSE_ATTRS.get(attr, {}).get("text_input"):
        await q.answer("Введи ответ числом в чат.", show_alert=True)
        return

    idx = int(q.data[len("rev_ans_"):])
    options = data.get("reverse_options", [])
    correct_idx = data.get("reverse_correct_idx", -1)
    correct = data["reverse_correct"]

    if idx >= len(options):
        await q.answer()
        return

    chosen = options[idx]
    is_correct = (idx == correct_idx)
    points = REVERSE_ATTRS[attr]["points"] if is_correct else 0
    attr_label = REVERSE_ATTRS[attr]["label"]
    effect = "🎯 Точно\\!" if is_correct else "❌ Мимо\\!"

    await q.answer("✅ Правильно!" if is_correct else "❌ Мимо!")
    await q.edit_message_reply_markup(reply_markup=None)

    game_id    = data["game_id"]
    round_num  = data["round_num"]
    picker_id  = data["picker_id"]
    player_name = data["player_name"]
    actual_fee  = data["actual_fee"]

    # Write round to DB
    round_row = db.get_round(game_id, round_num)
    if round_row:
        db.update_round(
            round_row["id"],
            guess_amount=0,
            accuracy_tier="exact" if is_correct else "miss",
            points_earned=points,
            hints_used=0,
            hint_types=[],
            completed=True,
        )

    # Update scores
    game   = db.get_game(game_id)
    p1_id  = game["player1_id"]
    p2_id  = game["player2_id"]
    p1_score = game["player1_score"]
    p2_score = game["player2_score"]
    if user_id == p1_id:
        p1_score += points
    else:
        p2_score += points
    db.update_game(game_id, player1_score=p1_score, player2_score=p2_score)

    # Result cards
    def _rev_card(is_guesser: bool) -> str:
        whose = "Твой ответ" if is_guesser else "Ответ соперника"
        return (
            f"{effect}\n\n"
            f"👤 *{_esc(player_name)}*\n"
            f"💰 Сумма: *{_esc(format_fee(actual_fee))}*\n"
            f"{_esc(attr_label)}: *{_esc(correct)}*\n"
            f"🎯 {whose}: *{_esc(chosen)}*\n"
            f"📊 Очки: *\\+{points}*"
        )

    await q.message.reply_text(_rev_card(is_guesser=True), parse_mode=ParseMode.MARKDOWN_V2)
    try:
        await ctx.bot.send_message(picker_id, _rev_card(is_guesser=False), parse_mode=ParseMode.MARKDOWN_V2)
    except TelegramError:
        pass

    picker_action_now, picker_data_now = await get_state(picker_id)
    await clear_state(user_id)

    next_round = round_num + 1
    _derby_total_rev = data.get("derby_total_rounds", TOTAL_ROUNDS)
    if next_round > _derby_total_rev:
        await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)
    else:
        await _advance_round(
            ctx,
            game_id=game_id,
            round_num=round_num,
            new_picker_id=user_id,
            new_guesser_id=picker_id,
            p1_id=p1_id,
            p2_id=p2_id,
            p1_score=p1_score,
            p2_score=p2_score,
            guesser_id=user_id,
            picker_id=picker_id,
            guesser_data=data,
            picker_action=picker_action_now or "",
            picker_data=picker_data_now or {},
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
        diff_str = f"\\+{diff}" if diff >= 0 else f"\\-{abs(diff)}"
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
            delta_str = f"\\+{delta}" if delta >= 0 else f"\\-{abs(delta)}"

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
        opp_id = p2_id if pid == p1_id else p1_id
        res_rows = [
            [InlineKeyboardButton("🔄 Реванш", callback_data=f"result_rematch_{opp_id}"),
             InlineKeyboardButton("🏠 Меню", callback_data="menu_back")],
        ]
        my_phrases = db.get_user_cosmetics(pid, "phrase")
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
    """result_rematch_{opp_id} — send a rematch challenge to the last opponent."""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    opp_id = int(q.data.split("_", 2)[2])  # result_rematch_{opp_id}

    user = db.get_user(user_id)
    target = db.get_user(opp_id)
    if not user or not target:
        await q.edit_message_text("Игрок не найден.", reply_markup=main_menu_kb())
        return

    # Don't allow double-challenging if already waiting
    cur_action, _ = await get_state(user_id)
    if cur_action == "waiting_for_opponent":
        await q.answer("Ты уже ждёшь ответа на вызов.", show_alert=True)
        return

    challenge = db.create_challenge(user_id, opp_id)
    challenge_id = challenge["id"]

    await set_state(user_id, "waiting_for_opponent", {
        "challenge_id": challenge_id,
        "challenged_id": opp_id,
    })
    await set_state(opp_id, "challenge_received", {
        "challenge_id": challenge_id,
        "challenger_id": user_id,
    })

    await q.edit_message_text(
        f"🔄 Запрос на реванш отправлен *{_esc(target['display_name'])}*\\.\n\nЖдём ответа\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="menu_back")]]),
    )

    try:
        await ctx.bot.send_message(
            opp_id,
            f"🔄 *{_esc(_display_name(user))}* хочет реванш\\!\n\n"
            f"🏅 Рейтинг: {_esc(rating_display(user))}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Принять", callback_data=f"challenge_accept_{challenge_id}_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"challenge_decline_{challenge_id}_{user_id}"),
            ]]),
        )
    except TelegramError as e:
        logger.warning("Could not DM rematch target %s: %s", opp_id, e)
        await q.edit_message_text(
            "⚠️ Не удалось отправить запрос сопернику\\. Возможно, они не запустили бота\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_menu_kb(),
        )
        await clear_state(user_id)


# ── Game cancel ───────────────────────────────────────────────────────────────

async def cb_game_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await clear_state(q.from_user.id)
    await q.edit_message_text("Действие отменено.", reply_markup=main_menu_kb())


async def cb_game_surrender(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """game_surrender_{game_id} — player forfeits the current game."""
    q = update.callback_query
    user_id = q.from_user.id

    action, data = await get_state(user_id)
    valid_states = (
        "guessing", "waiting_for_guess", "waiting_for_pick",
        "picking_league", "picking_club", "picking_transfer",
        "exchange_waiting", "exchange_guessing_picker",
    )
    if action not in valid_states:
        await q.answer("У тебя нет активной игры.", show_alert=True)
        return

    game_id = data.get("game_id")
    if not game_id:
        await q.answer("Не могу найти игру.", show_alert=True)
        return

    game = db.get_game(game_id)
    if not game:
        await q.answer("Игра не найдена.", show_alert=True)
        return

    p1_id = game["player1_id"]
    p2_id = game["player2_id"]
    opponent_id = p2_id if user_id == p1_id else p1_id

    p1_score = game["player1_score"]
    p2_score = game["player2_score"]

    # Force surrenderer to lose: ensure opponent's score is higher
    if user_id == p1_id:
        if p1_score >= p2_score:
            p2_score = p1_score + 1
    else:
        if p2_score >= p1_score:
            p1_score = p2_score + 1

    await q.answer("🏳 Ты сдался", show_alert=True)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass

    surrenderer = db.get_user(user_id)
    sname = _esc(surrenderer["display_name"]) if surrenderer else "Соперник"

    try:
        await ctx.bot.send_message(
            opponent_id,
            f"🏳 *{sname}* сдался\\! Ты побеждаешь\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except TelegramError:
        pass

    await _finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)


# ══════════════════════════════════════════════════════════════════════════════
# ── Debug panel (superadmin only) ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _is_superadmin(user_id: int) -> bool:
    from config import SUPERADMIN_IDS
    return user_id in SUPERADMIN_IDS


def debug_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Выбрать игрока",      callback_data="dbg_lookup")],
        [InlineKeyboardButton("✏️ Редактор косметики",  callback_data="dbg_editcosm")],
        [InlineKeyboardButton("← Меню",                 callback_data="menu_back")],
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
        [InlineKeyboardButton("💰 Монеты",        callback_data=f"dbg_coins_{uid}"),
         InlineKeyboardButton("🏅 Рейтинг",       callback_data=f"dbg_rating_{uid}")],
        [InlineKeyboardButton("🏆 Достижения",    callback_data=f"dbg_achs_{uid}"),
         InlineKeyboardButton("🎨 Косметика",     callback_data=f"dbg_cosm_{uid}")],
        [InlineKeyboardButton("🏟 Клубы",         callback_data=f"dbg_clubs_{uid}")],
        [InlineKeyboardButton("🔄 Сбросить кал.", callback_data=f"dbg_resetcal_{uid}"),
         InlineKeyboardButton("🗑 Состояние",     callback_data=f"dbg_clearstate_{uid}")],
        [InlineKeyboardButton("← Назад",          callback_data="dbg_back")],
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


async def cmd_sendpack(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/sendpack @user1 @user2 ... — superadmin: send 2 beta packs to each listed user."""
    if not _is_superadmin(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text(
            "Использование: `/sendpack @username1 @username2`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    pack_text = (
        "🎉 *Спасибо за бета\\-тест Transfer Guesser\\!*\n\n"
        "Вы одни из первых, кто помог протестировать игру\\.\n"
        "За это — специальный бета\\-пак 🎁\n\n"
        "_Нажми чтобы открыть\\!_"
    )

    lines: list[str] = []
    for raw in ctx.args:
        username = raw.lstrip("@")
        target = db.get_user_by_username(username)
        if not target:
            lines.append(f"❌ @{username} — не найден в базе")
            continue

        target_id = target["user_id"]
        sent = 0
        for _ in range(2):
            amount = random.randrange(1_000, 10_001, 500)  # 1000, 1500, …, 10000
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🎁 Открыть бета-пак",
                    callback_data=f"betapack_{amount}_{target_id}",
                )
            ]])
            try:
                await ctx.bot.send_message(
                    target_id, pack_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=kb,
                )
                sent += 1
            except TelegramError as e:
                logger.warning("sendpack: failed to DM %s: %s", username, e)

        status = f"✅ @{username} — {sent}/2 пака отправлено"
        lines.append(status)

    await update.message.reply_text("\n".join(lines))


async def cb_betapack_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """betapack_<amount>_<owner_id> — open a beta pack (one-time, owner only)."""
    q = update.callback_query
    user_id = q.from_user.id

    parts = q.data.split("_")          # ['betapack', '<amount>', '<owner_id>']
    try:
        amount   = int(parts[1])
        owner_id = int(parts[2])
    except (IndexError, ValueError):
        await q.answer("Ошибка пака.", show_alert=True)
        return

    if user_id != owner_id:
        await q.answer("Это не твой пак! 👀", show_alert=True)
        return

    db.add_coins(user_id, amount)
    await q.answer(f"🎉 +{amount:,} монет!".replace(",", " "), show_alert=False)
    await q.edit_message_text(
        f"🎉 *Спасибо за бета\\-тест Transfer Guesser\\!*\n\n"
        f"💰 Бета\\-пак открыт\\!\n"
        f"Ты получил: *{amount:,} монет* 🪙".replace(",", " "),
        parse_mode=ParseMode.MARKDOWN_V2,
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
    uid = user["user_id"]
    achs = db.get_user_achievements(uid)
    titles = db.get_user_cosmetics(uid, "title")
    phrases = db.get_user_cosmetics(uid, "phrase")
    active = user.get("active_title")
    if active:
        _t = _get_title(active)
        active_label = f"{_t.get('emoji','')} {_t.get('label', active)}"
    else:
        active_label = "—"
    return (
        f"👤 *{_esc(user['display_name'])}* \\(@{_esc(user.get('username') or '—')}\\)\n"
        f"🆔 ID: `{user['user_id']}`\n"
        f"🏅 Рейтинг: *{user['rating']}*\n"
        f"🪙 Монеты: *{user.get('coins', 0)}*\n"
        f"🎮 Игр: {user.get('games_played',0)} \\| ✅ {user.get('wins',0)} \\| ❌ {user.get('losses',0)}\n"
        f"🔄 Калибровка: {user.get('calibration_games',0)}/10 "
        f"\\({'✅' if user.get('is_calibrated') else '⏳'}\\)\n"
        f"🏆 Достижений: *{len(achs)}*\n"
        f"🎨 Косметика: *{len(titles)}* тит\\. / *{len(phrases)}* фраз\n"
        f"🏷 Активный титул: *{_esc(active_label)}*"
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
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    uid = int(q.data.split("_")[2])
    db.clear_pending_action(uid)
    await q.answer("✅ Состояние очищено", show_alert=True)


# ── Debug: club allegiance management ─────────────────────────────────────────

# Топ-клубов для быстрой разблокировки в debug-панели
_DBG_QUICK_CLUBS = [
    ("281",   "Manchester City"),
    ("418",   "Real Madrid"),
    ("131",   "FC Barcelona"),
    ("27",    "Bayern Munich"),
    ("46",    "Inter Milan"),
    ("583",   "Paris Saint-Germain"),
    ("964",   "Zenit"),
]


def _dbg_clubs_kb(uid: int) -> InlineKeyboardMarkup:
    unlocked = set(db.get_unlocked_clubs(uid))
    rows = []
    for cid, cname in _DBG_QUICK_CLUBS:
        mark = "✅ " if cid in unlocked else ""
        rows.append([InlineKeyboardButton(
            f"{mark}{cname}",
            callback_data=f"dbg_unlock_{uid}_{cid}",
        )])
    rows.append([InlineKeyboardButton("🗑 Сбросить все клубы", callback_data=f"dbg_clubs_reset_{uid}")])
    rows.append([InlineKeyboardButton("← Назад", callback_data=f"dbg_su_{uid}")])
    return InlineKeyboardMarkup(rows)


async def cb_dbg_clubs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_clubs_{uid} — show quick club unlock menu."""
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    target = db.get_user(uid)
    if not target:
        await q.answer("Игрок не найден.", show_alert=True)
        return
    counts = db.get_club_guess_counts(uid)
    allegiance = target.get("club_allegiance") or "—"
    text = (
        f"🏟 *Клубы игрока* `{uid}`\n\n"
        f"Активный клуб\\-фан: `{_esc(str(allegiance))}`\n"
        f"Разблокировано: {len(db.get_unlocked_clubs(uid))}\n"
        f"Всего отметок: {sum(counts.values())}\n\n"
        f"_Тапни клуб — установит счётчик в 5 \\(разблокирует\\)_"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=_dbg_clubs_kb(uid))


async def cb_dbg_unlock_club(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_unlock_{uid}_{club_id} — set club guess count to 5."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    parts = q.data.split("_")
    uid = int(parts[2])
    club_id = parts[3]
    # Топорно: добавляем угадывания пока не достигнем 5
    current = db.get_club_guess_count(uid, club_id)
    while current < 5:
        current = db.increment_club_guess(uid, club_id)
    await q.answer(f"✅ Клуб {club_id} разблокирован", show_alert=False)
    # Перерисовка меню
    q.data = f"dbg_clubs_{uid}"
    await cb_dbg_clubs(update, ctx)


async def cb_dbg_clubs_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_clubs_reset_{uid} — wipe all club_guess_counts for user."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    uid = int(q.data.split("_")[3])
    db.get_client().table("club_guess_counts").delete().eq("user_id", uid).execute()
    db.set_club_allegiance(uid, None)
    await q.answer("🗑 Все клубы сброшены", show_alert=True)
    q.data = f"dbg_clubs_{uid}"
    await cb_dbg_clubs(update, ctx)


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

    elif action.startswith("dbg_editt_") or action.startswith("dbg_editp_"):
        await _handle_dbg_editcosm_input(update, action, data)


# ── Debug: Achievements management ───────────────────────────────────────────

def _dbg_achs_kb(uid: int) -> InlineKeyboardMarkup:
    earned = set(db.get_user_achievements(uid))
    rows = []
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id in earned:
            label = f"✅ {ach['emoji']} {ach['name']}"
            rows.append([InlineKeyboardButton(label, callback_data=f"dbg_rach_{uid}_{ach_id}")])
        else:
            label = f"⬜ {ach['emoji']} {ach['name']}"
            rows.append([InlineKeyboardButton(label, callback_data=f"dbg_gach_{uid}_{ach_id}")])
    rows.append([InlineKeyboardButton("🗑 Сбросить все", callback_data=f"dbg_rach_all_{uid}")])
    rows.append([InlineKeyboardButton("← Назад", callback_data=f"dbg_su_{uid}")])
    return InlineKeyboardMarkup(rows)


async def cb_dbg_achs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_achs_{uid} — achievement management panel."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    # Build everything BEFORE answering so errors can still be surfaced via show_alert
    try:
        uid = int(q.data.split("_")[2])
        target = db.get_user(uid)
        earned = db.get_user_achievements(uid)
        kb = _dbg_achs_kb(uid)
        text = (
            f"🏆 *Достижения — {_esc(target['display_name'])}*\n"
            f"Заработано: *{len(earned)}/{len(ACHIEVEMENTS)}*\n\n"
            f"✅ \\= уже есть \\(нажми чтобы отозвать\\)\n"
            f"⬜ \\= нет \\(нажми чтобы выдать\\)"
        )
    except Exception as e:
        logger.exception("cb_dbg_achs error: %s", e)
        await q.answer(f"Ошибка: {str(e)[:100]}", show_alert=True)
        return
    await q.answer()
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb)
    except Exception as e:
        logger.exception("cb_dbg_achs edit error: %s", e)
        await ctx.bot.send_message(q.from_user.id, f"❌ Ошибка отображения: {e}")


async def cb_dbg_give_ach(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_gach_{uid}_{ach_id} — grant achievement + cosmetics."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    parts = q.data.split("_", 3)  # dbg_gach_{uid}_{ach_id}
    uid = int(parts[2])
    ach_id = parts[3]
    db.award_achievement(uid, ach_id)
    for c_type, c_id in ACH_COSMETICS.get(ach_id, []):
        db.award_cosmetic(uid, c_type, c_id)
    ach = ACHIEVEMENTS.get(ach_id, {})
    # Build KB before answering so errors can be surfaced
    target = db.get_user(uid)
    earned = db.get_user_achievements(uid)
    kb = _dbg_achs_kb(uid)
    await q.answer(f"✅ Выдано: {ach.get('name', ach_id)}", show_alert=False)
    await q.edit_message_text(
        f"🏆 *Достижения — {_esc(target['display_name'])}*\n"
        f"Заработано: *{len(earned)}/{len(ACHIEVEMENTS)}*\n\n"
        f"✅ \\= уже есть \\(нажми чтобы отозвать\\)\n"
        f"⬜ \\= нет \\(нажми чтобы выдать\\)",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=kb,
    )


async def cb_dbg_revoke_ach(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_rach_{uid}_{ach_id} — revoke achievement. dbg_rach_all_{uid} — revoke all."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    parts = q.data.split("_", 3)  # dbg_rach_{uid}_{ach_id} OR dbg_rach_all_{uid}
    if parts[2] == "all":
        uid = int(parts[3])
        db.revoke_all_achievements(uid)
        alert = "🗑 Все достижения удалены"
    else:
        uid = int(parts[2])
        ach_id = parts[3]
        db.revoke_achievement(uid, ach_id)
        ach = ACHIEVEMENTS.get(ach_id, {})
        alert = f"🗑 Отозвано: {ach.get('name', ach_id)}"
    # Build KB before answering
    target = db.get_user(uid)
    earned = db.get_user_achievements(uid)
    kb = _dbg_achs_kb(uid)
    await q.answer(alert, show_alert=False)
    await q.edit_message_text(
        f"🏆 *Достижения — {_esc(target['display_name'])}*\n"
        f"Заработано: *{len(earned)}/{len(ACHIEVEMENTS)}*\n\n"
        f"✅ \\= уже есть \\(нажми чтобы отозвать\\)\n"
        f"⬜ \\= нет \\(нажми чтобы выдать\\)",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=kb,
    )


# ── Debug: Cosmetics management ───────────────────────────────────────────────

def _dbg_cosm_text(uid: int, user: dict) -> str:
    owned_titles = db.get_user_cosmetics(uid, "title")
    owned_phrases = db.get_user_cosmetics(uid, "phrase")
    active = user.get("active_title")
    if active:
        t_cur = _get_title(active)
        active_label = f"{t_cur.get('emoji','')} {t_cur.get('label', active)}"
    else:
        active_label = "—"

    lines = [f"🎨 *Косметика — {_esc(user['display_name'])}*\n"]
    lines.append(f"🏷 Активный титул: *{_esc(active_label)}*\n")

    lines.append("*Титулы:*")
    for tid in TITLES:
        cur = _get_title(tid)
        mark = "✅" if tid in owned_titles else "⬜"
        lines.append(f"  {mark} {cur.get('emoji','')} {_esc(cur.get('label',''))}")

    lines.append("\n*Фразы:*")
    for pid_p in PHRASES:
        cur = _get_phrase(pid_p)
        mark = "✅" if pid_p in owned_phrases else "⬜"
        txt = cur.get("text", "")
        lines.append(f"  {mark} _{_esc(txt[:40])}…_")

    return "\n".join(lines)


def _dbg_cosm_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷 Управление титулами",  callback_data=f"dbg_ctitles_{uid}")],
        [InlineKeyboardButton("💬 Управление фразами",   callback_data=f"dbg_cphrases_{uid}")],
        [InlineKeyboardButton("🗑 Сбросить всю косметику", callback_data=f"dbg_cosm_reset_{uid}")],
        [InlineKeyboardButton("← Назад",                 callback_data=f"dbg_su_{uid}")],
    ])


async def cb_dbg_cosm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_cosm_{uid} — cosmetics overview panel."""
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    target = db.get_user(uid)
    await q.edit_message_text(
        _dbg_cosm_text(uid, target),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_cosm_kb(uid),
    )


async def cb_dbg_cosm_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_cosm_reset_{uid} — wipe all cosmetics."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    uid = int(q.data.split("_")[3])
    db.revoke_all_cosmetics(uid)
    target = db.get_user(uid)
    text = _dbg_cosm_text(uid, target)
    kb = _dbg_cosm_kb(uid)
    await q.answer("🗑 Вся косметика удалена", show_alert=True)
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb)


def _dbg_ctitles_kb(uid: int) -> InlineKeyboardMarkup:
    owned = set(db.get_user_cosmetics(uid, "title"))
    active = db.get_active_title(uid)
    rows = []
    for tid in TITLES:
        cur = _get_title(tid)
        has = tid in owned
        is_active = tid == active
        if has and is_active:
            # owned + active: one button to deactivate, one to revoke
            rows.append([
                InlineKeyboardButton(f"✅🏷 {cur.get('emoji','')} {cur.get('label','')}", callback_data=f"dbg_ccleart_{uid}"),
                InlineKeyboardButton("🗑", callback_data=f"dbg_ctoggle_{uid}_{tid}"),
            ])
        elif has:
            # owned but not active: activate or revoke
            rows.append([
                InlineKeyboardButton(f"✅ {cur.get('emoji','')} {cur.get('label','')}", callback_data=f"dbg_ctactivate_{uid}_{tid}"),
                InlineKeyboardButton("🗑", callback_data=f"dbg_ctoggle_{uid}_{tid}"),
            ])
        else:
            # not owned: give it
            rows.append([
                InlineKeyboardButton(f"⬜ {cur.get('emoji','')} {cur.get('label','')}", callback_data=f"dbg_ctoggle_{uid}_{tid}"),
            ])
    rows.append([InlineKeyboardButton("← Косметика", callback_data=f"dbg_cosm_{uid}")])
    return InlineKeyboardMarkup(rows)


async def cb_dbg_ctitles(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_ctitles_{uid} — title management."""
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    await q.edit_message_text(
        "🏷 *Управление титулами*\n"
        "✅🏷 \\= активен \\(нажми — снять\\)\n"
        "✅ \\= выдан \\(нажми — активировать\\) \\| 🗑 \\= отозвать\n"
        "⬜ \\= не выдан \\(нажми — выдать\\)",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_ctitles_kb(uid),
    )


async def cb_dbg_ctoggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_ctoggle_{uid}_{title_id} — toggle title ownership."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    parts = q.data.split("_", 3)  # dbg_ctoggle_{uid}_{title_id}
    uid = int(parts[2])
    title_id = parts[3]
    owned = set(db.get_user_cosmetics(uid, "title"))
    cur = _get_title(title_id)
    if title_id in owned:
        db.revoke_cosmetic(uid, "title", title_id)
        if db.get_active_title(uid) == title_id:
            db.set_active_title(uid, None)
        msg = f"🗑 Отозван: {cur.get('label','')}"
    else:
        db.award_cosmetic(uid, "title", title_id)
        msg = f"✅ Выдан: {cur.get('label','')}"
    kb = _dbg_ctitles_kb(uid)
    await q.answer(msg, show_alert=False)
    await q.edit_message_reply_markup(reply_markup=kb)


async def cb_dbg_ctactivate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_ctactivate_{uid}_{title_id} — set title as active for player."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    parts = q.data.split("_", 3)  # dbg_ctactivate_{uid}_{title_id}
    uid = int(parts[2])
    title_id = parts[3]
    owned = db.get_user_cosmetics(uid, "title")
    if title_id not in owned:
        db.award_cosmetic(uid, "title", title_id)  # give if not owned
    db.set_active_title(uid, title_id)
    cur = _get_title(title_id)
    kb = _dbg_ctitles_kb(uid)
    await q.answer(f"✅🏷 Активен: {cur.get('emoji','')} {cur.get('label','')}", show_alert=False)
    await q.edit_message_reply_markup(reply_markup=kb)


async def cb_dbg_ccleart(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_ccleart_{uid} — clear active title."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    uid = int(q.data.split("_")[2])
    db.set_active_title(uid, None)
    kb = _dbg_ctitles_kb(uid)
    await q.answer("❌ Активный титул снят", show_alert=False)
    await q.edit_message_reply_markup(reply_markup=kb)


def _dbg_cphrases_kb(uid: int) -> InlineKeyboardMarkup:
    owned = set(db.get_user_cosmetics(uid, "phrase"))
    rows = []
    for pid_p in PHRASES:
        cur = _get_phrase(pid_p)   # applies DB overrides
        has = pid_p in owned
        mark = "✅" if has else "⬜"
        txt = cur.get("text", "")
        short = txt[:32] + "…" if len(txt) > 32 else txt
        label = f"{mark} {short}"
        rows.append([InlineKeyboardButton(label, callback_data=f"dbg_cptoggle_{uid}_{pid_p}")])
    rows.append([InlineKeyboardButton("← Косметика", callback_data=f"dbg_cosm_{uid}")])
    return InlineKeyboardMarkup(rows)


async def cb_dbg_cphrases(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_cphrases_{uid} — phrase management."""
    q = update.callback_query
    await q.answer()
    if not _is_superadmin(q.from_user.id):
        return
    uid = int(q.data.split("_")[2])
    await q.edit_message_text(
        "💬 *Управление фразами*\n_Нажми чтобы выдать/отозвать_",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_cphrases_kb(uid),
    )


async def cb_dbg_cptoggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_cptoggle_{uid}_{phrase_id} — toggle phrase ownership."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    parts = q.data.split("_", 3)  # dbg_cptoggle_{uid}_{phrase_id}
    uid = int(parts[2])
    phrase_id = parts[3]
    owned = set(db.get_user_cosmetics(uid, "phrase"))
    if phrase_id in owned:
        db.revoke_cosmetic(uid, "phrase", phrase_id)
        msg = "🗑 Фраза отозвана"
    else:
        db.award_cosmetic(uid, "phrase", phrase_id)
        msg = "✅ Фраза выдана"
    kb = _dbg_cphrases_kb(uid)
    await q.answer(msg, show_alert=False)
    await q.edit_message_reply_markup(reply_markup=kb)


# ── Debug: Edit cosmetic definitions ─────────────────────────────────────────

def _dbg_editcosm_kb() -> InlineKeyboardMarkup:
    """Main menu: choose title or phrase to edit."""
    rows = []
    rows.append([InlineKeyboardButton("🏷 Редактировать титулы", callback_data="dbg_editcosm_titles")])
    rows.append([InlineKeyboardButton("💬 Редактировать фразы",  callback_data="dbg_editcosm_phrases")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="dbg_back")])
    return InlineKeyboardMarkup(rows)


def _dbg_editcosm_titles_kb() -> InlineKeyboardMarkup:
    rows = []
    for tid, t in TITLES.items():
        cur = _get_title(tid)
        label = f"{cur.get('emoji','?')} {cur.get('label','?')}"
        rows.append([InlineKeyboardButton(label, callback_data=f"dbg_editt_{tid}")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="dbg_editcosm")])
    return InlineKeyboardMarkup(rows)


def _dbg_editcosm_phrases_kb() -> InlineKeyboardMarkup:
    rows = []
    for pid_p, p in PHRASES.items():
        cur = _get_phrase(pid_p)
        short = cur.get("text", "")[:30] + "…"
        rows.append([InlineKeyboardButton(short, callback_data=f"dbg_editp_{pid_p}")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="dbg_editcosm")])
    return InlineKeyboardMarkup(rows)


def _dbg_editt_kb(tid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Эмодзи",   callback_data=f"dbg_editt_emoji_{tid}")],
        [InlineKeyboardButton("✏️ Название",  callback_data=f"dbg_editt_label_{tid}")],
        [InlineKeyboardButton("🔄 Сбросить",  callback_data=f"dbg_editt_reset_{tid}")],
        [InlineKeyboardButton("← Назад",      callback_data="dbg_editcosm_titles")],
    ])


def _dbg_editp_kb(pid_p: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Текст фразы", callback_data=f"dbg_editp_body_{pid_p}")],
        [InlineKeyboardButton("🔄 Сбросить",    callback_data=f"dbg_editp_reset_{pid_p}")],
        [InlineKeyboardButton("← Назад",        callback_data="dbg_editcosm_phrases")],
    ])


async def cb_dbg_editcosm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_editcosm — main cosmetic definitions editor."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    await q.answer()
    await q.edit_message_text(
        "✏️ *Редактор косметики*\n_Изменения сохраняются в БД и действуют сразу\\._",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_editcosm_kb(),
    )


async def cb_dbg_editcosm_titles(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    _reload_cosm_overrides()
    await q.answer()
    await q.edit_message_text(
        "🏷 *Выбери титул для редактирования:*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_editcosm_titles_kb(),
    )


async def cb_dbg_editcosm_phrases(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    _reload_cosm_overrides()
    await q.answer()
    await q.edit_message_text(
        "💬 *Выбери фразу для редактирования:*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_editcosm_phrases_kb(),
    )


async def cb_dbg_editt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_editt_{tid} — show title edit menu."""
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    # data: dbg_editt_{tid}  OR  dbg_editt_{field}_{tid}
    parts = q.data.split("_", 3)
    # parts[0]=dbg, parts[1]=editt, parts[2]=tid OR field, parts[3]=tid (optional)
    if len(parts) == 4:
        field = parts[2]  # emoji or label or reset
        tid   = parts[3]
        if field == "reset":
            db.reset_cosmetic_def(tid, "title")
            _reload_cosm_overrides()
            await q.answer("🔄 Сброшено до дефолта", show_alert=False)
        else:
            state_key = f"dbg_editt_{field}"
            await set_state(q.from_user.id, state_key, {"cosmetic_id": tid, "cosmetic_type": "title"})
            hint = "эмодзи (один символ, напр. 🔥)" if field == "emoji" else "новое название (напр. Мастер)"
            await q.answer()
            await q.edit_message_text(
                f"✏️ Введи {hint}:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Отмена", callback_data="dbg_editcosm_titles"),
                ]]),
            )
            return
    else:
        tid = parts[2]

    cur = _get_title(tid)
    ov  = _cosm_overrides_cache.get(tid, {})
    default = TITLES.get(tid, {})
    lines = [
        f"🏷 *{_esc(cur.get('emoji',''))} {_esc(cur.get('label',''))}*\n",
        f"Эмодзи: `{_esc(cur.get('emoji','—'))}` {'\\(изменено\\)' if ov.get('emoji') else '\\(дефолт\\)'}",
        f"Название: `{_esc(cur.get('label','—'))}` {'\\(изменено\\)' if ov.get('label') else '\\(дефолт\\)'}",
        f"\nДефолт: {_esc(default.get('emoji',''))} {_esc(default.get('label',''))}",
    ]
    await q.answer()
    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_editt_kb(tid),
    )


async def cb_dbg_editp(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """dbg_editp_{pid} — show phrase edit menu. dbg_editp_{field}_{pid} — action.
    NOTE: phrase IDs contain underscores (e.g. p_sniper), so we split on action keywords.
    """
    q = update.callback_query
    if not _is_superadmin(q.from_user.id):
        await q.answer()
        return
    # Strip prefix "dbg_editp_" and check what follows
    suffix = q.data[len("dbg_editp_"):]   # e.g. "body_p_sniper" / "reset_p_sniper" / "p_sniper"
    if suffix.startswith("body_"):
        field = "body"
        pid_p = suffix[len("body_"):]      # e.g. "p_sniper"
    elif suffix.startswith("reset_"):
        field = "reset"
        pid_p = suffix[len("reset_"):]
    else:
        field = None
        pid_p = suffix                     # just the phrase ID, e.g. "p_sniper"

    if field == "reset":
        db.reset_cosmetic_def(pid_p, "phrase")
        _reload_cosm_overrides()
        await q.answer("🔄 Сброшено до дефолта", show_alert=False)
    elif field == "body":
        await set_state(q.from_user.id, "dbg_editp_body",
                        {"cosmetic_id": pid_p, "cosmetic_type": "phrase"})
        await q.answer()
        await q.edit_message_text(
            "✏️ Введи новый текст фразы:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="dbg_editcosm_phrases"),
            ]]),
        )
        return

    cur = _get_phrase(pid_p)
    ov  = _cosm_overrides_cache.get(pid_p, {})
    default = PHRASES.get(pid_p, {})
    lines = [
        f"💬 *Фраза:* _{_esc(cur.get('text',''))}_\n",
        f"{'\\(изменено\\)' if ov.get('body') else '\\(дефолт\\)'}",
        f"\nДефолт: _{_esc(default.get('text',''))}_",
    ]
    await q.answer()
    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_dbg_editp_kb(pid_p),
    )


async def _handle_dbg_editcosm_input(
    update, action: str, data: dict
) -> None:
    """Handle text input for cosmetic definition edits."""
    text = update.message.text.strip()
    admin_id = update.effective_user.id
    cosm_id   = data.get("cosmetic_id", "")
    cosm_type = data.get("cosmetic_type", "")

    try:
        if action == "dbg_editt_emoji":
            db.upsert_cosmetic_def(cosm_id, cosm_type, emoji=text)
            _reload_cosm_overrides()
            await set_state(admin_id, "dbg_main", {})
            cur = _get_title(cosm_id)
            await update.message.reply_text(
                f"✅ Эмодзи обновлено: {text} {cur.get('label','')}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← Назад к редактору", callback_data="dbg_editcosm_titles"),
                ]]),
            )

        elif action == "dbg_editt_label":
            db.upsert_cosmetic_def(cosm_id, cosm_type, label=text)
            _reload_cosm_overrides()
            await set_state(admin_id, "dbg_main", {})
            cur = _get_title(cosm_id)
            await update.message.reply_text(
                f"✅ Название обновлено: {cur.get('emoji','')} {text}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← Назад к редактору", callback_data="dbg_editcosm_titles"),
                ]]),
            )

        elif action == "dbg_editp_body":
            db.upsert_cosmetic_def(cosm_id, cosm_type, body=text)
            _reload_cosm_overrides()
            await set_state(admin_id, "dbg_main", {})
            await update.message.reply_text(
                f"✅ Текст фразы обновлён для [{cosm_id}]:\n{text}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← Назад к редактору", callback_data="dbg_editcosm_phrases"),
                ]]),
            )

        else:
            logger.warning("_handle_dbg_editcosm_input: unknown action %r", action)

    except Exception as e:
        logger.exception("_handle_dbg_editcosm_input error: %s", e)
        await update.message.reply_text(f"❌ Ошибка сохранения: {e}")


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

    rows = []
    for diff_key, diff in DIFFICULTY.items():
        rows.append([InlineKeyboardButton(
            f"{diff['emoji']} {diff['name']} — {diff['desc']}",
            callback_data=f"training_diff_{diff_key}",
        )])
    rows.append([InlineKeyboardButton("← Назад", callback_data="menu_play")])

    await q.edit_message_text(
        "🤖 *Режим тренировки*\n\n"
        "6 раундов против бота\\. Рейтинг не меняется\\.\n\n"
        "Выбери уровень сложности:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_training_difficulty(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """training_diff_{easy|medium|hard} — difficulty selected, start game."""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    diff_key = q.data.split("_")[-1]   # easy / medium / hard
    if diff_key not in DIFFICULTY:
        diff_key = "medium"

    diff = DIFFICULTY[diff_key]
    state = {
        "round_num": 1,
        "player_score": 0,
        "bot_score": 0,
        "rounds_data": [],
        "is_player_guessing": True,
        "difficulty": diff_key,
    }
    await set_state(user_id, "training_game", state)
    await q.edit_message_text(
        f"{diff['emoji']} *{diff['name']}* — тренировка начинается\\!",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await _training_next_round(ctx, user_id, state)


async def cb_training_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Restart with same difficulty (from 'Ещё раз' button)."""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    # Try to keep last difficulty from context; default medium
    action, prev_state = await get_state(user_id)
    diff_key = prev_state.get("difficulty", "medium") if prev_state else "medium"

    state = {
        "round_num": 1,
        "player_score": 0,
        "bot_score": 0,
        "rounds_data": [],
        "is_player_guessing": True,
        "difficulty": diff_key,
    }
    diff = DIFFICULTY.get(diff_key, DIFFICULTY["medium"])
    await set_state(user_id, "training_game", state)
    await q.edit_message_text(
        f"{diff['emoji']} *{diff['name']}* — тренировка начинается\\!",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await _training_next_round(ctx, user_id, state)


async def _training_next_round(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    state: dict,
) -> None:
    round_num = state["round_num"]
    is_player_guessing = state["is_player_guessing"]
    difficulty = state.get("difficulty", "medium")
    diff = DIFFICULTY.get(difficulty, DIFFICULTY["medium"])
    diff_badge = f"{diff['emoji']} {diff['name']} \\| "

    if is_player_guessing:
        # Bot picks a random transfer → player guesses
        transfer = _bot_pick_transfer(difficulty)
        if not transfer:
            await ctx.bot.send_message(
                user_id,
                "⚠️ Нет данных для тренировки\\. Дождись окончания загрузки трансферов\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            await clear_state(user_id)
            return

        state["current_transfer_id"] = transfer["id"]
        state["current_actual_fee"] = transfer["transfer_fee"]
        state["hints_used"] = 0
        state["used_hint_types"] = []

        # Auto-hint for easy mode
        auto_hint_text = ""
        if diff.get("auto_hint"):
            hint_type = diff["auto_hint"]
            mapping = {
                "nationality": ("🌍 Национальность", transfer.get("nationality")),
                "position":    ("🎽 Позиция",         transfer.get("position")),
                "age":         ("🎂 Возраст",         str(transfer.get("age", "?")) + " лет"),
            }
            label, val = mapping.get(hint_type, ("?", None))
            if val:
                state["used_hint_types"] = [hint_type]
                state["hints_used"] = 0   # auto hint doesn't count against limit
                auto_hint_text = f"\n💡 {label}: *{_esc(str(val))}*"

        await set_state(user_id, "training_guessing", state)

        max_hints = diff["max_hints"]
        remaining = [h for h in HINT_TYPES if h not in state["used_hint_types"]]
        if max_hints > 0:
            kb_rows = [[InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"tgh_{h}")] for h in remaining]
        else:
            kb_rows = []
        kb_rows.append([InlineKeyboardButton("❌ Завершить тренировку", callback_data="training_abort")])

        caption = (
            f"{diff_badge}Раунд *{round_num}/{TOTAL_ROUNDS}* — Бот выбрал трансфер:\n\n"
            f"👤 Игрок: *{_esc(transfer['player_name'])}*"
            f"{auto_hint_text}\n\n"
            f"💰 Назови сумму трансфера:\n_Например: 45M, 45000000, 500K_"
        )
        await _send_photo_message(ctx, user_id, transfer.get("photo_url"), caption, InlineKeyboardMarkup(kb_rows))
    else:
        # Player picks → show league selector
        state_copy = dict(state)
        await set_state(user_id, "training_picking_league", state_copy)
        await ctx.bot.send_message(
            user_id,
            f"{diff_badge}Раунд *{round_num}/{TOTAL_ROUNDS}* — Твой ход\\! Выбери лигу:",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=training_leagues_kb(),
        )


def _bot_pick_transfer(difficulty: str = "medium") -> dict | None:
    """Pick a random transfer filtered by difficulty fee range."""
    import random as _random
    diff = DIFFICULTY.get(difficulty, DIFFICULTY["medium"])
    min_fee = diff.get("min_fee")
    max_fee = diff.get("max_fee")

    leagues = db.get_leagues()
    _random.shuffle(leagues)
    attempts = 0
    for league in leagues * 3:   # up to 3 passes through league list
        if attempts > 30:
            break
        attempts += 1
        clubs = db.get_clubs_by_league(league["league_id"])
        if not clubs:
            continue
        club = _random.choice(clubs)
        transfers = db.get_transfers_by_club(club["club_id"], limit=50)
        if min_fee:
            transfers = [t for t in transfers if (t.get("transfer_fee") or 0) >= min_fee]
        if max_fee:
            transfers = [t for t in transfers if (t.get("transfer_fee") or 0) <= max_fee]
        if transfers:
            return _random.choice(transfers)
    # Fallback: no filter
    return _bot_pick_transfer_any()


def _bot_pick_transfer_any() -> dict | None:
    """Fallback: pick any random transfer regardless of fee."""
    import random as _random
    leagues = db.get_leagues()
    _random.shuffle(leagues)
    for league in leagues:
        clubs = db.get_clubs_by_league(league["league_id"])
        if not clubs:
            continue
        transfers = db.get_transfers_by_club(_random.choice(clubs)["club_id"], limit=20)
        if transfers:
            return _random.choice(transfers)
    return None


def _bot_guess(actual_fee: int, difficulty: str = "medium") -> int:
    """Simulate bot guess accuracy based on difficulty."""
    import random as _random
    roll = _random.random()
    if difficulty == "easy":
        # Weak bot: makes bigger mistakes
        if roll < 0.04:
            return actual_fee
        elif roll < 0.14:
            error = _random.uniform(-0.10, 0.10)
        elif roll < 0.35:
            error = _random.uniform(-0.30, 0.30)
        else:
            error = _random.uniform(-0.60, 0.60)
    elif difficulty == "hard":
        # Strong bot: more accurate
        if roll < 0.18:
            return actual_fee
        elif roll < 0.40:
            error = _random.uniform(-0.05, 0.05)
        elif roll < 0.70:
            error = _random.uniform(-0.12, 0.12)
        else:
            error = _random.uniform(-0.22, 0.22)
    else:  # medium — unchanged from original
        if roll < 0.08:
            return actual_fee
        elif roll < 0.20:
            error = _random.uniform(-0.05, 0.05)
        elif roll < 0.45:
            error = _random.uniform(-0.15, 0.15)
        else:
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
    bot_guess = _bot_guess(actual_fee, state.get("difficulty", "medium"))
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

    diff_key = data.get("difficulty", "medium")
    diff = DIFFICULTY.get(diff_key, DIFFICULTY["medium"])
    max_hints = diff["max_hints"]

    if max_hints == 0:
        await q.answer("Подсказки недоступны на этом уровне сложности!", show_alert=True)
        return
    if hints_used >= max_hints:
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
    # Only show hint buttons if there are still hints available
    new_hints_used = data["hints_used"]
    if new_hints_used < max_hints and remaining:
        kb_rows = [[InlineKeyboardButton(f"💡 {HINT_LABELS[h]}", callback_data=f"tgh_{h}")] for h in remaining]
    else:
        kb_rows = []
    kb_rows.append([InlineKeyboardButton("❌ Завершить тренировку", callback_data="training_abort")])
    try:
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb_rows))
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

    difficulty = state.get("difficulty", "medium")
    diff = DIFFICULTY.get(difficulty, DIFFICULTY["medium"])
    coin_mult = diff["coin_mult"]
    coins_earned = max(1, int(player_score * coin_mult))
    db.add_coins(user_id, coins_earned)

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

    mult_str = f"×{coin_mult:.1f}".rstrip("0").rstrip(".")
    coins_line = f"\n\n{diff['emoji']} *{_esc(diff['name'])}* — монеты: *\\+{coins_earned}* \\({_esc(mult_str)} к очкам\\)"

    text = (
        f"{header}\n\n"
        f"{score_block}\n\n"
        f"*Твои угадывания:*\n{rounds_block}"
        f"{coins_line}\n\n"
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
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("cancel",   cmd_cancel))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("debug",    cmd_debug))
    app.add_handler(CommandHandler("sendpack", cmd_sendpack))

    # Callback queries — specific patterns before general ones
    handlers = [
        # Menu
        ("^menu_play$",           cb_menu_play),
        ("^menu_profile$",        cb_menu_profile),
        ("^achievements$",        cb_achievements),
        ("^fan_hall$",            cb_fan_hall),
        ("^cosmetics_menu$",      cb_cosmetics_menu),
        ("^cosmetics_titles$",    cb_cosmetics_titles),
        ("^set_title_",           cb_set_title),
        ("^club_allegiance$",     cb_club_allegiance),
        ("^allegiance_set_",      cb_set_allegiance),
        ("^allegiance_clear$",    cb_clear_allegiance),
        ("^taunt_menu_",          cb_taunt_menu),
        ("^taunt_send_",          cb_taunt_send),
        ("^taunt_cancel_",         cb_taunt_cancel),
        ("^taunt_gsend_",         cb_taunt_game_send),
        ("^taunt_game_",          cb_taunt_game_menu),
        ("^taunt_gcancel_",       cb_taunt_game_cancel),
        ("^menu_leaderboard$",    cb_menu_leaderboard),
        ("^menu_help$",           cb_menu_help),
        ("^help_fanclubs$",       cb_help_fanclubs),
        ("^help_derby$",          cb_help_derby),
        ("^help_rules$",          cb_help_rules),
        ("^help_club_switch$",    cb_help_club_switch),
        ("^patch_notes$",         cb_patch_notes),
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
        ("^result_rematch_",      cb_result_rematch),
        ("^result_menu$",         cb_menu_back),
        # Game
        ("^game_cancel$",         cb_game_cancel),
        ("^game_surrender_",      cb_game_surrender),
        ("^game_pick_league$",    cb_pick_league_back),
        ("^gl_",                  cb_pick_league),
        ("^gcp_",                 cb_clubs_page),
        ("^gc_",                  cb_pick_club),
        ("^gt_",                  cb_pick_transfer),
        ("^gh_",                  cb_hint),
        ("^ultras_range$",        cb_ultras_range),
        ("^sc_use$",              cb_sc_use),
        ("^sc_skip$",             cb_sc_skip),
        ("^rev_ans_\\d$",         cb_reverse_answer),
        ("^betapack_",            cb_betapack_open),
        # Training
        ("^training_diff_",       cb_training_difficulty),
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
        ("^dbg_clubs_reset_",     cb_dbg_clubs_reset),
        ("^dbg_clubs_",           cb_dbg_clubs),
        ("^dbg_unlock_",          cb_dbg_unlock_club),
        ("^dbg_achs_",            cb_dbg_achs),
        ("^dbg_gach_",            cb_dbg_give_ach),
        ("^dbg_rach_",            cb_dbg_revoke_ach),
        ("^dbg_cosm_reset_",      cb_dbg_cosm_reset),
        ("^dbg_cosm_",            cb_dbg_cosm),
        ("^dbg_ctitles_",         cb_dbg_ctitles),
        ("^dbg_ctactivate_",      cb_dbg_ctactivate),
        ("^dbg_ctoggle_",         cb_dbg_ctoggle),
        ("^dbg_ccleart_",         cb_dbg_ccleart),
        ("^dbg_cphrases_",        cb_dbg_cphrases),
        ("^dbg_cptoggle_",        cb_dbg_cptoggle),
        # Cosmetic definitions editor
        ("^dbg_editcosm_titles$", cb_dbg_editcosm_titles),
        ("^dbg_editcosm_phrases$",cb_dbg_editcosm_phrases),
        ("^dbg_editcosm$",        cb_dbg_editcosm),
        ("^dbg_editt_",           cb_dbg_editt),
        ("^dbg_editp_",           cb_dbg_editp),
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


def _start_health_server() -> None:
    """Minimal HTTP server so Render / other PaaS hosts see a live port."""
    import os
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):  # silence access logs
            pass

    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Health-check server listening on port %d", port)


def main() -> None:
    _start_health_server()
    app = create_application()
    _reload_cosm_overrides()   # load DB overrides into cache on startup
    logger.info("Bot started. Polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
