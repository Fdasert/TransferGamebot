# Transfer Guesser Bot

Telegram-бот: угадывай стоимость футбольных трансферов в 1vs1.

## Быстрый старт

### 1. Установи зависимости

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 2. Загрузи данные о трансферах

Сначала нужно запустить локальный API Transfermarkt:

```powershell
# Клонируй репо API
git clone https://github.com/felipeall/transfermarkt-api
cd transfermarkt-api

# Запусти через Docker
docker compose up -d

# Или без Docker (нужен Python + uvicorn):
pip install -r requirements.txt
uvicorn app.main:app --reload
```

После запуска API (по умолчанию `http://localhost:8000`) загрузи данные:

```powershell
cd C:\Users\fdasert\Documents\TransferGamebot
.\.venv\Scripts\python data_fetcher.py
```

Это займёт несколько минут — скрипт загрузит клубы и трансферы топ-5 лиг в Supabase.

### 3. Запусти бота

```powershell
.\.venv\Scripts\python bot.py
```

## Архитектура

| Файл | Роль |
|---|---|
| `bot.py` | Все Telegram-хендлеры и игровая логика |
| `database.py` | Supabase REST layer — все DB-вызовы |
| `scoring.py` | Чистый движок подсчёта очков (тестируется отдельно) |
| `data_fetcher.py` | Скрипт загрузки трансферов в кеш |
| `config.py` | Токены и константы |

## Правила игры

- **Формат:** 1vs1, 6 раундов (по 3 на каждого)
- Выбирающий → выбирает лигу → клуб → трансфер
- Угадывающий видит имя игрока, называет сумму

**Очки за точность:**
- Точное попадание: 10 очков
- ±5%: 8 очков
- ±10%: 6 очков
- ±20%: 4 очка
- Мимо: 0 очков

**Подсказки (макс. 2):** каждая снижает результат на 1 очко.

**ELO:** первые 10 игр — калибровка, потом начисляется рейтинг.

## Обновление данных

Запускай `data_fetcher.py` раз в неделю для обновления трансферов:

```powershell
.\.venv\Scripts\python data_fetcher.py
```
