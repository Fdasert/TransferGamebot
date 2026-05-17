"""
SoFIFA player scraper — альтернатива Futbin.
Собирает игроков с OVR в диапазоне MIN_OVR–MAX_OVR и дозаписывает в CSV.

Запуск (OVR 82-86, дозапись к существующему fut_players.csv):
    python scrape_sofifa.py

Запуск с другим диапазоном:
    python scrape_sofifa.py 82 86
"""
import csv
import sys
import time
import random
import requests
import bs4

MIN_OVR     = int(sys.argv[1]) if len(sys.argv) > 1 else 82
MAX_OVR     = int(sys.argv[2]) if len(sys.argv) > 2 else 86
OUTPUT_FILE = "fut_players.csv"
DELAY_MIN   = 2.0
DELAY_MAX   = 4.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://sofifa.com/",
}

CSV_FIELDS = [
    "futbin_id", "name", "club", "nation", "league",
    "rating", "version", "position",
    "pac", "sho", "pas", "dri", "def", "phy",
]

# Соответствие позиций SoFIFA → стандарт
POS_MAP = {
    "GK": "GK",
    "CB": "CB", "LB": "LB", "RB": "RB", "LWB": "LWB", "RWB": "RWB",
    "CDM": "CDM", "CM": "CM", "CAM": "CAM",
    "LM": "LM", "RM": "RM", "LW": "LW", "RW": "RW",
    "CF": "CF", "ST": "ST", "LS": "ST", "RS": "ST",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


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


def fetch_page(offset: int) -> bs4.BeautifulSoup | None:
    url = (
        f"https://sofifa.com/players"
        f"?col=oa&sort=desc"
        f"&minOVR={MIN_OVR}&maxOVR={MAX_OVR}"
        f"&offset={offset}"
    )
    try:
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            print(f"  [!] offset {offset}: HTTP {r.status_code}")
            return None
        return bs4.BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [!] offset {offset}: {e}")
        return None


def parse_page(soup: bs4.BeautifulSoup, existing_ids: set) -> list[dict]:
    players = []
    table = soup.find("table")
    if not table:
        return players

    for tr in table.find_all("tr")[1:]:  # пропускаем заголовок
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue

        # TD0: аватар (пропускаем)
        # TD1: имя, позиции, возраст
        td_info = tds[1]
        name_a = td_info.find("a", {"data-tippy-content": True})
        if not name_a:
            # запасной вариант
            name_a = td_info.find("a")
        if not name_a:
            continue

        name = name_a.get_text(strip=True)

        # ID из href: /player/12345/...
        href = name_a.get("href", "")
        sofifa_id = ""
        parts = href.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "player":
            sofifa_id = f"sf_{parts[1]}"  # префикс чтобы не конфликтовать с futbin

        if sofifa_id in existing_ids:
            continue

        # Позиция (первый span с позицией)
        pos_spans = td_info.find_all("span", class_=lambda c: c and "pos" in c)
        position = ""
        for sp in pos_spans:
            txt = sp.get_text(strip=True).upper()
            if txt in POS_MAP:
                position = POS_MAP[txt]
                break
        if not position:
            continue

        # TD2: нация
        td_nation = tds[2]
        nation_img = td_nation.find("img")
        nation = nation_img.get("title", "").strip() if nation_img else ""

        # TD3: клуб
        td_club = tds[3]
        club_a = td_club.find("a")
        club = club_a.get_text(strip=True) if club_a else ""

        # TD4: лига (необязательно)
        td_league = tds[4] if len(tds) > 4 else None
        league = ""
        if td_league:
            league_a = td_league.find("a")
            league = league_a.get_text(strip=True) if league_a else ""

        # OVR — ищем td с классом "col-oa" или просто первое числовое
        rating = 0
        for td in tds:
            cls = " ".join(td.get("class", []))
            if "col-oa" in cls or "col-" not in cls:
                txt = td.get_text(strip=True)
                if txt.isdigit():
                    val = int(txt)
                    if MIN_OVR <= val <= MAX_OVR:
                        rating = val
                        break

        if not rating:
            # запасной — ищем числа в диапазоне
            for td in tds:
                txt = td.get_text(strip=True)
                if txt.isdigit() and MIN_OVR <= int(txt) <= MAX_OVR:
                    rating = int(txt)
                    break

        if not rating:
            continue

        # Атрибуты PAC SHO PAS DRI DEF PHY
        # В SoFIFA они идут в определённых колонках
        # Пробуем найти по классам col-pac, col-sh, col-pa, col-dr, col-de, col-ph
        stat_map = {}
        for td in tds:
            cls = " ".join(td.get("class", []))
            txt = td.get_text(strip=True)
            if not txt.isdigit():
                continue
            val = int(txt)
            if "col-pac" in cls or "col-sp" in cls:
                stat_map["pac"] = val
            elif "col-sho" in cls or "col-sh" in cls:
                stat_map["sho"] = val
            elif "col-pas" in cls or "col-pa" in cls:
                stat_map["pas"] = val
            elif "col-dri" in cls or "col-dr" in cls:
                stat_map["dri"] = val
            elif "col-def" in cls or "col-de" in cls:
                stat_map["def"] = val
            elif "col-phy" in cls or "col-ph" in cls:
                stat_map["phy"] = val

        # Если не нашли по классам — берём числа подряд из конца строки
        if len(stat_map) < 6:
            nums = []
            for td in tds:
                txt = td.get_text(strip=True)
                if txt.isdigit() and 1 <= int(txt) <= 99:
                    nums.append(int(txt))
            # Последние 6 чисел обычно PAC SHO PAS DRI DEF PHY
            if len(nums) >= 6:
                stat_map = {
                    "pac": nums[-6], "sho": nums[-5], "pas": nums[-4],
                    "dri": nums[-3], "def": nums[-2], "phy": nums[-1],
                }

        if len(stat_map) < 6:
            continue

        players.append({
            "futbin_id": sofifa_id,
            "name":      name,
            "club":      club,
            "nation":    nation,
            "league":    league,
            "rating":    rating,
            "version":   "Normal",
            "position":  position,
            "pac":       stat_map.get("pac", 0),
            "sho":       stat_map.get("sho", 0),
            "pas":       stat_map.get("pas", 0),
            "dri":       stat_map.get("dri", 0),
            "def":       stat_map.get("def", 0),
            "phy":       stat_map.get("phy", 0),
        })
        existing_ids.add(sofifa_id)

    return players


def get_total_count(soup: bs4.BeautifulSoup) -> int:
    """Пробуем найти общее число игроков."""
    for tag in soup.find_all(string=True):
        tag = str(tag).strip()
        if "players" in tag.lower() and tag[0].isdigit():
            try:
                return int(tag.split()[0].replace(",", ""))
            except Exception:
                pass
    return 0


def main():
    print(f"SoFIFA scraper | OVR {MIN_OVR}–{MAX_OVR}")
    print(f"  Output: {OUTPUT_FILE} (append mode)")

    existing_ids = load_existing_ids()
    print(f"  Existing in CSV: {len(existing_ids)} players")

    # Прогрев
    print("  Warming up...")
    try:
        SESSION.get("https://sofifa.com/", timeout=15)
        time.sleep(random.uniform(1.5, 3))
    except Exception:
        pass

    all_new: list[dict] = []
    offset = 0
    step = 60  # SoFIFA показывает по 60 игроков

    while True:
        soup = fetch_page(offset)
        if not soup:
            break

        page_players = parse_page(soup, existing_ids)

        if not page_players and offset > 0:
            print(f"  No new players at offset {offset} — done")
            break

        all_new.extend(page_players)
        print(f"  Offset {offset}: +{len(page_players)} players (total: {len(all_new)})")

        # Проверяем, есть ли следующая страница
        next_btn = soup.find("a", string=lambda t: t and "Next" in t)
        if not next_btn:
            break

        offset += step
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Дозапись в CSV
    file_exists = True
    try:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            f.read(1)
    except FileNotFoundError:
        file_exists = False

    with open(OUTPUT_FILE, "a" if file_exists else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(all_new)

    print(f"\nDone! +{len(all_new)} players appended to {OUTPUT_FILE}")
    if all_new:
        print(f"Example: {all_new[0]['name']} ({all_new[0]['nation']}, {all_new[0]['club']}) "
              f"OVR={all_new[0]['rating']} PAC={all_new[0]['pac']}")


if __name__ == "__main__":
    main()
