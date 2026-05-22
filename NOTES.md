# TransferGameBot — шпаргалка для Claude

> Актуально на: 2026-05-23  
> Деплой: Render (polling, не webhook). Пуш в git → Render автодеплоит.  
> Запуск локально: `.\.venv\Scripts\python.exe bot.py`

---

## Файлы проекта

| Файл | Роль |
|---|---|
| `bot.py` | Все Telegram-хендлеры, вся игровая логика (~3860 строк) |
| `database.py` | Supabase REST — все DB-вызовы только здесь |
| `scoring.py` | Чистый движок очков/ELO (без сайд-эффектов, standalone) |
| `config.py` | Токены, константы игры (TOTAL_ROUNDS=3, MAX_HINTS=3, и т.д.) |
| `club_emblems.py` | Маппинг club_id → custom_emoji_id (стикерпак Football_emoji_24) |
| `casino.py` | Казино-модуль (рулетка, блэкджек) |
| `fut.py` | FUT-рынок (листинги, трейды, турниры) |
| `check_emblems.py` | Скрипт проверки покрытия клубных эмблем |
| `NOTES.md` | Этот файл |

---

## Стек

- **python-telegram-bot v22** (async)
- **supabase-py v2**
- **Python 3.11+**
- Режим работы: **polling** (не webhook), бот сам ходит к api.telegram.org

---

## State machine (pending_actions в Supabase)

Бот stateless. Всё состояние — в таблице `pending_actions` (user_id → action + data jsonb).

| action | owner | смысл |
|---|---|---|
| `picking_league` | picker_id | выбирает лигу |
| `picking_club` | picker_id | выбирает клуб |
| `picking_transfer` | picker_id | выбирает трансфер |
| `waiting_for_pick` | guesser_id | ждёт пока picker выберет |
| `guessing` | guesser_id | угадывает сумму |
| `waiting_for_opponent` | challenger_id | ждёт ответа на вызов |
| `challenge_received` | challenged_id | получил вызов |
| `registering` | user_id | вводит имя при старте |
| `training_*` | user_id | тренировочный режим |

`get_state(uid)` / `set_state(uid, action, data)` / `clear_state(uid)` — обёртки в bot.py.

---

## Поток мультиплеерной игры

```
cb_play_challenge → cb_select_opponent → create_challenge → set_state "waiting_for_opponent"
    ↓ (opponent нажимает Accept)
cb_challenge_accept → clear_state оба → _start_game()
    ↓
_start_game() → db.create_game() → db.create_round() → set_state picker:"picking_league", guesser:"waiting_for_pick"
    ↓ (picker выбирает лигу → клуб → трансфер)
cb_pick_transfer() → set_state guesser:"guessing" → _send_guess_prompt()
    ↓ (guesser вводит число)
on_text → _handle_guess() → calculate_points() → club allegiance hook → update_round() → _result_card()
    ↓ (если раундов больше нет)
_finish_game() → apply_elo_result() → _check_achievements() → result keyboard с Реваншем
```

Роли picker/guesser меняются каждый раунд.

---

## Ключевые функции bot.py

### Клавиатуры
| Функция | Описание |
|---|---|
| `main_menu_kb()` | Главное меню |
| `leagues_kb(game_id=None)` | Список лиг + кнопка сдаться если game_id передан |
| `clubs_kb(league_id, page, game_id=None)` | Клубы с пагинацией |
| `transfers_kb(transfers, game_id=None)` | Список трансферов |
| `hints_kb(used)` | Подсказки (исключает уже использованные) |

### Игровая логика
| Функция | Описание |
|---|---|
| `_start_game(ctx, p1, p2, msg)` | Создаёт игру и первый раунд в DB |
| `_handle_guess(update, ctx, text, data)` | Парсит ответ гуессера, считает очки, club allegiance, отправляет карточку |
| `_finish_game(ctx, game_id, p1_id, p2_id, p1_score, p2_score)` | Финализирует игру, ELO, ачивки, victory screen |
| `_check_achievements(ctx, uid, ...)` | Проверяет и выдаёт ачивки после игры |
| `_result_card(is_guesser)` | Closure внутри `_handle_guess`; формирует MarkdownV2 карточку раунда |
| `tier_effect(tier, points)` | Эмодзи-заголовок по тиру (exact/close/miss) |
| `calculate_points(guess, actual, hints)` | Из scoring.py — возвращает (tier, points) |

### Профиль / косметика
| Функция | Описание |
|---|---|
| `profile_text(user)` | MarkdownV2 текст профиля (рейтинг, монеты, клуб-фан) |
| `_display_name(user)` | Имя с активным титулом |
| `_get_title(tid)` | Данные титула из TITLES dict (с override из DB) |
| `_get_phrase(pid)` | Данные фразы из PHRASES dict (с override из DB) |
| `_reload_cosm_overrides()` | Загружает кастомные описания косметики из Supabase |

### Club allegiance
| Функция | Описание |
|---|---|
| `cb_club_allegiance` | Показывает список разблокированных клубов (HTML parse mode) |
| `cb_set_allegiance` | allegiance_set_{club_id} → сохраняет выбор |
| `cb_clear_allegiance` | allegiance_clear → сбрасывает |
| `club_emblem_html(club_id, fallback)` | Из club_emblems.py → `<tg-emoji emoji-id="...">🏟</tg-emoji>` |
| `has_emblem(club_id)` | Есть ли кастомная эмблема для клуба |

---

## Callback data паттерны (порядок важен — first match wins!)

```
menu_play, menu_profile, menu_back, menu_leaderboard, menu_help
achievements
cosmetics_menu → cosmetics_titles → set_title_{id}
club_allegiance → allegiance_set_{club_id} → allegiance_clear
taunt_menu_{opp} → taunt_send_{phrase}_{opp} → taunt_cancel_{opp}
taunt_game_{picker} → taunt_gsend_{phrase}_{picker} → taunt_gcancel_{picker}
play_challenge → chpp_{page} → chp_{user_id}
play_random, play_training
challenge_accept_{id}_{challenger} → challenge_decline_{id}_{challenger}
result_rematch_{opp_id}, result_menu
game_cancel, game_surrender_{game_id}
game_pick_league (back)
gl_{league_id} → gcp_{page}_{league} → gc_{club_id} → gt_{transfer_id}
gh_{hint_type}
training_diff_{d} → training_start → training_abort
tgl_{league} → tgcp_{page}_{league} → tgc_{club} → tgt_{transfer} → tgh_{hint}
dbg_* (суперадмин)
```

**Правило**: специфичные префиксы ВЫШЕ общих в списке хендлеров!

---

## Supabase таблицы (актуальная схема)

| Таблица | Ключевые поля |
|---|---|
| `users` | `user_id`, `rating`, `games_played`, `wins`, `losses`, `coins`, `is_admin`, `is_calibrated`, `calibration_games`, `active_title`, `club_allegiance` (TEXT, новое) |
| `games` | `game_id`, `player1_id`, `player2_id`, `player1_score`, `player2_score`, `current_round`, `winner_id`, `finished` |
| `rounds` | `id`, `game_id`, `round_num`, `picker_id`, `guesser_id`, `transfer_id`, `guess_amount`, `accuracy_tier`, `points_earned`, `hints_used`, `completed` |
| `pending_actions` | `user_id`, `action`, `data` (jsonb) |
| `challenges` | `id`, `challenger_id`, `challenged_id`, `status` (pending/accepted/declined) |
| `user_achievements` | `user_id`, `achievement_id` (UNIQUE) |
| `user_cosmetics` | `user_id`, `cosmetic_type`, `cosmetic_id` |
| `club_guess_counts` | `user_id`, `club_id`, `correct_count` — PK(user_id, club_id) **(новое)** |
| `clubs` | `club_id` (int), `club_name`, `league_id` |
| `transfers` | `id`, `player_name`, `club_id`, `from_club`, `fee`, `season`, `position`, `age`, `nationality` |
| `cosmetic_defs` | переопределение текстов/эмодзи косметики через DB |
| `fut_market_listings` | FUT маркет |

---

## Монеты (coins)

```python
db.get_coins(user_id)               # текущий баланс
db.add_coins(user_id, amount) → int  # пополнить, вернуть новый баланс
db.spend_coins(user_id, amount) → (bool, int)  # списать, вернуть (ok, balance)
```

Монеты начисляются за: победу (`COINS_WIN_BONUS`), ничью (`COINS_DRAW_BONUS`), точное попадание (`COINS_EXACT_BONUS`), бонус фаната клуба (+15 за каждый угаданный трансфер своего клуба).

---

## Club Allegiance система

**Как разблокировать клуб**: угадать 5 трансферов из него (tier != "miss").  
**Уведомление**: при достижении 5 бот шлёт HTML-сообщение с `<tg-emoji>` эмблемой.  
**Фан-бонус**: +15 монет за каждый угаданный трансфер своего клуба-аллегенции.  
**Отображение**: в профиле `🏟 Клуб-фан: *Название*` (MarkdownV2), в косметике — с tg-emoji (HTML).

```python
db.increment_club_guess(uid, club_id) → int   # вернуть новый count
db.get_unlocked_clubs(uid, threshold=5)        # list[str] club_ids
db.set_club_allegiance(uid, club_id|None)      # сохранить выбор
```

**club_emblems.py**: 107 клубов из 14 лиг. Ключ — строка club_id (числовой).  
Тип emoji: HTML `<tg-emoji emoji-id="...">🏟</tg-emoji>` — работает без Premium у получателя.

---

## Parse modes — важно!

- Большинство сообщений: **MarkdownV2** — все спецсимволы `_*[]()~>#+-=|{}.!` нужно эскейпить через `_esc()`
- Сообщения с `<tg-emoji>`: **HTML** — нельзя смешивать с MarkdownV2
- Клуб-аллегенция UI (`cb_club_allegiance`): HTML parse mode
- Уведомление о разблокировке клуба: HTML parse mode
- Результатные карточки, профиль, косметика (без эмблем): MarkdownV2

**Частая ошибка**: отрицательные числа в MarkdownV2.  
✅ `f"\\-{abs(delta)}"` — правильно  
❌ `str(-5)` → `-5` → краш `BadRequest: Can't parse entities` (ловится TelegramError, молчит)

---

## Scoring (scoring.py)

```python
calculate_points(guess, actual_fee, hints_used) → (tier, points)
# tier: "exact" | "close" | "miss"

calculate_elo(winner_rating, loser_rating, k) → (new_winner, new_loser)
format_fee(amount_int) → "45M" | "500K" | "1.2B"
parse_fee_input(text) → int | None  # парсит "45M", "45000000", "500K"
```

---

## Ачивки и косметика

**ACHIEVEMENTS** dict в bot.py — каждая ачивка: `emoji, name, desc, reward, secret`.  
**ACH_COSMETICS** dict — ачивка → список `(cosmetic_type, cosmetic_id)` к выдаче.  
**TITLES** dict — `{id: {emoji, label}}` с возможным override из `_cosm_overrides_cache`.  
**PHRASES** dict — `{id: {text}}` аналогично.

`_check_achievements(ctx, uid, my_rounds, won, lost)` — вызывается в `_finish_game` после каждой игры.

---

## Debug панель (`/debug`)

Только для `SUPERADMIN_IDS` из config.py. Не в /help.  
Возможности: выдать/отозвать ачивки, управлять косметикой, задать монеты/рейтинг, сбросить состояние.  
Snapshot хранится в `context.user_data["debug_snapshot"]` — теряется при рестарте.

---

## Недавние изменения (май 2025)

1. **Victory screen bug**: `str(-5)` → неэскейпленный `-` → `BadRequest` → молчаливый сбой. Исправлено: `f"\\-{abs(delta)}"`.
2. **Кнопка Сдаться**: добавлена в `leagues_kb`, `clubs_kb`, `transfers_kb` через опциональный `game_id`.
3. **Реванш**: `result_rematch_{opp_id}` → реальный вызов с Accept/Decline, не просто "в меню".
4. **taunt_cancel**: несёт `opp_id` (`taunt_cancel_{opp_id}`) чтобы восстановить правильную клавиатуру результата.
5. **Club allegiance**: полная система — разблокировка, фан-бонус +15 монет, UI в косметике, отображение в профиле.
