"""Импорт fut_players.csv в Supabase таблицу fut_players."""
import csv
from config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client

BATCH = 100  # строк за один запрос

client = create_client(SUPABASE_URL, SUPABASE_KEY)


def load_csv(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "futbin_id": r["futbin_id"][:20],
                    "name":      r["name"][:100],
                    "club":      r["club"][:100],
                    "nation":    r["nation"][:100],
                    "league":    r["league"][:100],
                    "rating":    int(r["rating"]),
                    "version":   r["version"][:50],
                    "position":  r["position"][:10],
                    "pac":       int(r["pac"] or 0),
                    "sho":       int(r["sho"] or 0),
                    "pas":       int(r["pas"] or 0),
                    "dri":       int(r["dri"] or 0),
                    "def":       int(r["def"] or 0),
                    "phy":       int(r["phy"] or 0),
                })
            except (ValueError, KeyError) as e:
                print(f"  skip row ({e}): {r.get('name','?')}")
    return rows


def main():
    print("Loading CSV...")
    players = load_csv("fut_players.csv")
    print(f"  {len(players)} players ready")

    # Очищаем старые данные если есть
    client.table("fut_players").delete().neq("id", 0).execute()
    print("  Old data cleared")

    # Загружаем батчами
    total = 0
    for i in range(0, len(players), BATCH):
        batch = players[i:i + BATCH]
        client.table("fut_players").insert(batch).execute()
        total += len(batch)
        print(f"  Uploaded {total}/{len(players)}...")

    print(f"\nDone! {total} players imported into Supabase.")


if __name__ == "__main__":
    main()
