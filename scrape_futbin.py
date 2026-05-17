"""
Futbin player scraper — рабочая версия для FIFA 26.
Собирает игроков с рейтингом >= MIN_RATING и сохраняет в CSV.

Запуск:
    python scrape_futbin.py
"""
import csv
import time
import requests
import bs4

MIN_RATING  = 82       # игроки ниже этого рейтинга не нужны
MAX_PAGES   = 160      # страховка — хватит до OVR 82 (~4800 игроков)
DELAY       = 1.2      # секунды между запросами (не DDoS)
OUTPUT_FILE = "fut_players.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

CSV_FIELDS = [
    "futbin_id", "name", "club", "nation", "league",
    "rating", "version", "position",
    "pac", "sho", "pas", "dri", "def", "phy",
]


def get_total_pages(soup: bs4.BeautifulSoup) -> int:
    pag = soup.find("div", class_="pagination-buttons-wrapper")
    if not pag:
        return 1
    # Все ссылки-кнопки пагинации
    links = pag.find_all("a", class_="pagination-button")
    numbers = []
    for a in links:
        txt = a.get_text(strip=True)
        if txt.isdigit():
            numbers.append(int(txt))
    return max(numbers) if numbers else 1


def parse_row(row: bs4.Tag) -> dict | None:
    tds = row.find_all("td")
    if len(tds) < 15:
        return None

    # Имя, версия из TD[0]: разделитель |  →  ['97', 'Имя', 'TOTY']
    td0_parts = tds[0].get_text(separator="|", strip=True).split("|")
    name    = td0_parts[1].strip() if len(td0_parts) >= 2 else ""
    version = td0_parts[2].strip() if len(td0_parts) >= 3 else ""

    # ID игрока из href
    link    = tds[0].find("a")
    href    = link.get("href", "") if link else ""
    fut_id  = ""
    if "/player/" in href:
        fut_id = href.split("/player/")[1].split("/")[0]

    # Рейтинг и позиция
    rating = tds[1].get_text(strip=True)
    try:
        rating_int = int(rating)
    except ValueError:
        return None

    pos_span = tds[2].find("span")
    position = pos_span.get_text(strip=True) if pos_span else tds[2].get_text(strip=True).split()[0]

    # Клуб, нация, лига — из alt/title тегов img
    club = nation = league = ""
    for img in row.find_all("img"):
        alt   = img.get("alt", "")
        title = img.get("title", "")
        if alt == "Nation"  and not nation:  nation  = title
        if alt == "League"  and not league:  league  = title
        if alt == "Club"    and not club:    club    = title

    # Атрибуты (PAC SHO PAS DRI DEF PHY)
    def stat(td):
        return td.get_text(strip=True)

    return {
        "futbin_id": fut_id,
        "name":      name,
        "club":      club,
        "nation":    nation,
        "league":    league,
        "rating":    rating_int,
        "version":   version,
        "position":  position,
        "pac":       stat(tds[9]),
        "sho":       stat(tds[10]),
        "pas":       stat(tds[11]),
        "dri":       stat(tds[12]),
        "def":       stat(tds[13]),
        "phy":       stat(tds[14]),
    }


def fetch_page(page: int) -> bs4.BeautifulSoup | None:
    url = f"https://www.futbin.com/players?page={page}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [!] Page {page}: HTTP {r.status_code}")
            return None
        return bs4.BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [!] Page {page}: {e}")
        return None


def main():
    print("Futbin scraper start")
    print(f"  Min rating: {MIN_RATING} | Max pages: {MAX_PAGES}")

    # Страница 1 — определяем кол-во страниц
    soup = fetch_page(1)
    if not soup:
        print("Failed to load page 1")
        return

    total_pages = get_total_pages(soup)
    pages_to_scan = min(total_pages, MAX_PAGES)
    print(f"  Total pages on Futbin: {total_pages} | Will scan: {pages_to_scan}")

    all_players: list[dict] = []
    stop = False

    for page in range(1, pages_to_scan + 1):
        if page > 1:
            time.sleep(DELAY)
            soup = fetch_page(page)
            if not soup:
                continue

        rows = soup.find_all("tr", class_="player-row")
        page_players = []

        for row in rows:
            player = parse_row(row)
            if player is None:
                continue
            if player["rating"] < MIN_RATING:
                print(f"  Rating {player['rating']} < {MIN_RATING} — stopping at page {page}")
                stop = True
                break
            page_players.append(player)

        all_players.extend(page_players)
        print(f"  Page {page}/{pages_to_scan}: +{len(page_players)} players (total {len(all_players)})")

        if stop:
            break

    # Сохраняем в CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_players)

    print(f"\nDone! {len(all_players)} players saved to {OUTPUT_FILE}")
    if all_players:
        p = all_players[0]
        print(f"Example: {p['name']} ({p['nation']}, {p['club']}) OVR={p['rating']} PAC={p['pac']} SHO={p['sho']} PAS={p['pas']} DRI={p['dri']} DEF={p['def']} PHY={p['phy']}")


if __name__ == "__main__":
    main()
