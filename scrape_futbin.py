"""
Futbin player scraper — FIFA 26.
Собирает игроков с рейтингом >= MIN_RATING и сохраняет в CSV.

Запуск (первый прогон, страницы 1-60):
    python scrape_futbin.py

Второй прогон (страницы 61-120, дозапись):
    python scrape_futbin.py 61 120

Третий прогон (страницы 121-180, дозапись):
    python scrape_futbin.py 121 180

Каждый прогон — новая сессия с новыми cookies, что обходит Cloudflare лимит.
"""
import csv
import sys
import time
import random
import requests
import bs4

MIN_RATING  = 82       # игроки ниже этого рейтинга не нужны
DELAY_MIN   = 3.0      # минимальная задержка между запросами
DELAY_MAX   = 6.0      # максимальная задержка
LONG_PAUSE_EVERY = 20  # каждые N страниц делаем длинную паузу
LONG_PAUSE  = 30       # длинная пауза (секунды)
OUTPUT_FILE = "fut_players.csv"

# Читаем аргументы: start_page, end_page
START_PAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END_PAGE   = int(sys.argv[2]) if len(sys.argv) > 2 else 60
APPEND     = START_PAGE > 1   # дозапись если не с первой страницы

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.futbin.com/",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":  "document",
    "Sec-Fetch-Mode":  "navigate",
    "Sec-Fetch-Site":  "same-origin",
    "Cache-Control":   "max-age=0",
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

    td0_parts = tds[0].get_text(separator="|", strip=True).split("|")
    name    = td0_parts[1].strip() if len(td0_parts) >= 2 else ""
    version = td0_parts[2].strip() if len(td0_parts) >= 3 else ""

    link    = tds[0].find("a")
    href    = link.get("href", "") if link else ""
    fut_id  = ""
    if "/player/" in href:
        fut_id = href.split("/player/")[1].split("/")[0]

    rating = tds[1].get_text(strip=True)
    try:
        rating_int = int(rating)
    except ValueError:
        return None

    pos_span = tds[2].find("span")
    position = pos_span.get_text(strip=True) if pos_span else tds[2].get_text(strip=True).split()[0]

    club = nation = league = ""
    for img in row.find_all("img"):
        alt   = img.get("alt", "")
        title = img.get("title", "")
        if alt == "Nation"  and not nation:  nation  = title
        if alt == "League"  and not league:  league  = title
        if alt == "Club"    and not club:    club    = title

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


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_page(session: requests.Session, page: int) -> bs4.BeautifulSoup | None:
    url = f"https://www.futbin.com/players?page={page}"
    try:
        r = session.get(url, timeout=25)
        if r.status_code == 403:
            print(f"  [!] Page {page}: HTTP 403 — ждём 15 с и повторяем...")
            time.sleep(15)
            r = session.get(url, timeout=25)
        if r.status_code != 200:
            print(f"  [!] Page {page}: HTTP {r.status_code}")
            return None
        return bs4.BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [!] Page {page}: {e}")
        return None


def load_existing_ids() -> set:
    """Загружаем futbin_id уже записанных игроков, чтобы не дублировать."""
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
    print(f"Futbin scraper | pages {START_PAGE}–{END_PAGE} | append={APPEND}")
    print(f"  Min rating: {MIN_RATING} | Delay: {DELAY_MIN}–{DELAY_MAX}s")

    existing_ids = load_existing_ids() if APPEND else set()
    if APPEND:
        print(f"  Already in CSV: {len(existing_ids)} players")

    SESSION = make_session()

    # Прогрев сессии — получаем cookies
    print("  Warming up session (getting cookies)...")
    try:
        SESSION.get("https://www.futbin.com/", timeout=15)
        time.sleep(random.uniform(3, 5))
        # Второй прогрев — страница списка
        SESSION.get("https://www.futbin.com/players", timeout=15)
        time.sleep(random.uniform(2, 4))
    except Exception as e:
        print(f"  Warmup error: {e}")

    all_players: list[dict] = []
    stop = False
    consecutive_403 = 0

    for page in range(START_PAGE, END_PAGE + 1):
        if stop:
            break

        if page > START_PAGE:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            # Длинная пауза каждые LONG_PAUSE_EVERY страниц
            if (page - START_PAGE) % LONG_PAUSE_EVERY == 0:
                print(f"  [~] Long pause {LONG_PAUSE}s at page {page}...")
                time.sleep(LONG_PAUSE)
            else:
                time.sleep(delay)

        soup = fetch_page(SESSION, page)
        if not soup:
            consecutive_403 += 1
            if consecutive_403 >= 5:
                print(f"  [!] 5 consecutive failures — stopping.")
                break
            continue
        consecutive_403 = 0

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
            # Пропускаем дубликаты
            if player["futbin_id"] in existing_ids:
                continue
            existing_ids.add(player["futbin_id"])
            page_players.append(player)

        all_players.extend(page_players)
        print(f"  Page {page}/{END_PAGE}: +{len(page_players)} new players (total this run: {len(all_players)})")

    # Сохраняем
    mode = "a" if APPEND else "w"
    with open(OUTPUT_FILE, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not APPEND:
            writer.writeheader()
        writer.writerows(all_players)

    print(f"\nDone! +{len(all_players)} players saved to {OUTPUT_FILE}")
    if all_players:
        p = all_players[0]
        print(f"First new: {p['name']} ({p['nation']}, {p['club']}) OVR={p['rating']}")
    if all_players:
        p = all_players[-1]
        print(f"Last new:  {p['name']} ({p['nation']}, {p['club']}) OVR={p['rating']}")


if __name__ == "__main__":
    main()
