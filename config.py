import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8946919803:AAG-4VhO8o4oHN_S7a33Soj8U5efGs83Blc")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ghhscwncdrmrpobdyhqk.supabase.co")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdoaHNjd25jZHJtcnBvYmR5aHFrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODkzMjk0MCwiZXhwIjoyMDk0NTA4OTQwfQ.PUW0pibcZ9V2AwpqnHriKU9lkI8aavgO1VfkYRDpWJg",
)

# Cubeasses Supabase (кросс-бот обменник)
CUBE_SUPABASE_URL = os.getenv("CUBE_SUPABASE_URL", "https://rjfbkkfoomcxedoncvwv.supabase.co")
CUBE_SUPABASE_KEY = os.getenv(
    "CUBE_SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJqZmJra2Zvb21jeGVkb25jdnd2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIzNjQ2ODYsImV4cCI6MjA4Nzk0MDY4Nn0.VJn0eKVRM6qhnRZEwoZAHpf0GYDPJR8tduK8YS4-cGw",
)

SUPERADMIN_IDS: list[int] = [518544601]

TRANSFERMARKT_API_URL = os.getenv("TRANSFERMARKT_API_URL", "http://localhost:8000")

# ELO
ELO_K_CALIBRATION = 40   # more volatile during calibration
ELO_K_RATED       = 24   # rated games
CALIBRATION_GAMES = 10

# ELO skill bonuses (applied on top of performance score)
ELO_EXACT_BONUS   = 3    # per exact guess
ELO_CLOSE_BONUS   = 1    # per ±5% guess
ELO_HINT_PENALTY  = 1    # per hint used

# Game rules
TOTAL_ROUNDS = 6  # 3 picks each player
MAX_HINTS = 2
HINT_TYPES = ["position", "age", "nationality", "from_club", "season"]
HINT_LABELS = {
    "position": "Позиция",
    "age": "Возраст",
    "nationality": "Национальность",
    "from_club": "Откуда пришёл",
    "season": "Сезон",
}

# Accuracy tiers: (name, max_deviation_pct, base_points)
ACCURACY_TIERS = [
    ("exact", 0.0,  10),
    ("5pct",  5.0,   8),
    ("10pct", 10.0,  6),
    ("20pct", 20.0,  4),
]
# Outside 20% → 0 points

# Coin rewards
COINS_WIN_BONUS   = 20
COINS_DRAW_BONUS  = 10
COINS_EXACT_BONUS = 5   # per exact guess

TIER_LABELS = {
    "exact": "🎯 ТОЧНОЕ ПОПАДАНИЕ!",
    "5pct":  "🔥 Почти идеал!",
    "10pct": "👍 Неплохо!",
    "20pct": "😅 Близко...",
    "miss":  "❌ Мимо",
}
