"""
Скачивает FutBinCards19.csv с GitHub и импортирует игроков OVR 82-86
в fut_players.csv (дозапись), затем загружает в Supabase.

Запуск:
    python import_fifa19.py
"""
import csv
import io
import requests
from config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client

MIN_OVR = 82
MAX_OVR = 86
OUTPUT_FILE = "fut_players.csv"
BATCH = 100

CSV_FIELDS = [
    "futbin_id", "name", "club", "nation", "league",
    "rating", "version", "position",
    "pac", "sho", "pas", "dri", "def", "phy",
]

# Нормализация позиций
POS_MAP = {
    "GK": "GK",
    "CB": "CB", "LB": "LB", "RB": "RB",
    "LWB": "LWB", "RWB": "RWB",
    "CDM": "CDM", "CM": "CM", "CAM": "CAM",
    "LM": "LM", "RM": "RM",
    "LW": "LW", "RW": "RW",
    "CF": "CF", "ST": "ST",
    "LS": "ST", "RS": "ST", "SS": "ST",
}

# Принимаем только базовые версии (не спецкарты)
ALLOWED_REVISIONS = {
    "Gold", "Rare Gold", "Silver", "Rare Silver",
    "Bronze", "Rare Bronze", "Normal", "",
}

SOURCE_URL = "https://raw.githubusercontent.com/kafagy/fifa-FUT-Data/master/FutBinCards19.csv"


def load_existing_ids() -> set:
    ids = set()
    try:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("futbin_id"):
                    ids.add(row["futbin_id"])
    except FileNotFoundError:
        pass
    return ids


def main():
    print(f"Downloading FIFA 19 data from GitHub...")
    r = requests.get(SOURCE_URL, timeout=30)
    r.raise_for_status()
    print(f"  Downloaded {len(r.content):,} bytes")

    existing_ids = load_existing_ids()
    print(f"  Existing in CSV/DB: {len(existing_ids)} players")

    reader = csv.DictReader(io.StringIO(r.text))
    players = []
    skipped = 0

    for row in reader:
        try:
            rating = int(row["Rating"])
        except (ValueError, KeyError):
            continue

        if not (MIN_OVR <= rating <= MAX_OVR):
            continue

        revision = row.get("Revision", "").strip()
        if revision not in ALLOWED_REVISIONS:
            skipped += 1
            continue

        position = row.get("Position", "").strip().upper()
        position = POS_MAP.get(position, position)
        if not position:
            continue

        fut_id = f"f19_{row.get('ID', '').strip()}"
        if fut_id in existing_ids:
            continue

        name   = row.get("Name", "").strip()[:100]
        club   = row.get("Club", "").strip()[:100]
        nation = row.get("Country", "").strip()[:100]
        league = row.get("League", "").strip()[:100]

        if not name or not nation:
            continue

        try:
            pac = int(row.get("Pace", 0) or 0)
            sho = int(row.get("Shooting", 0) or 0)
            pas = int(row.get("Passing", 0) or 0)
            dri = int(row.get("Dribbling", 0) or 0)
            df  = int(row.get("Defending", 0) or 0)
            phy = int(row.get("Phyiscality", 0) or 0)
        except ValueError:
            continue

        # Базовая проверка: хотя бы часть статов > 0
        if pac + sho + pas + dri + df + phy == 0:
            continue

        # Версия для отображения
        version = "Gold" if rating >= 75 else ("Silver" if rating >= 65 else "Bronze")

        players.append({
            "futbin_id": fut_id[:20],
            "name":      name,
            "club":      club,
            "nation":    nation,
            "league":    league,
            "rating":    rating,
            "version":   version,
            "position":  position[:10],
            "pac":       pac,
            "sho":       sho,
            "pas":       pas,
            "dri":       dri,
            "def":       df,
            "phy":       phy,
        })
        existing_ids.add(fut_id)

    print(f"  Found {len(players)} new players OVR {MIN_OVR}-{MAX_OVR}")
    print(f"  Skipped {skipped} special cards")

    if not players:
        print("Nothing to add.")
        return

    # Rating distribution
    from collections import Counter
    dist = Counter(p["rating"] for p in players)
    for ovr in sorted(dist, reverse=True):
        print(f"    OVR {ovr}: {dist[ovr]}")

    # Дозапись в CSV
    file_exists = True
    try:
        open(OUTPUT_FILE, encoding="utf-8").read(1)
    except FileNotFoundError:
        file_exists = False

    with open(OUTPUT_FILE, "a" if file_exists else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(players)
    print(f"  Appended to {OUTPUT_FILE}")

    # Загрузка в Supabase
    print("\nUploading to Supabase...")
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    total = 0
    for i in range(0, len(players), BATCH):
        batch = players[i:i + BATCH]
        client.table("fut_players").insert(batch).execute()
        total += len(batch)
        print(f"  Uploaded {total}/{len(players)}...")

    print(f"\nDone! {total} players uploaded to Supabase.")


if __name__ == "__main__":
    main()
