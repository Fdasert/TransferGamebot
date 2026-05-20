"""Rewrite club_emblems.py with corrected emoji_id mappings based on visual verification of the pack."""
import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

with open(r"C:\Users\fdasert\Documents\pack_full.json", encoding="utf-8") as f:
    pack = json.load(f)

# index → custom_emoji_id
idx_to_id = {item["index"]: item["custom_emoji_id"] for item in pack}

# Verified mapping: (club_id, position_in_pack, club_name)
# Verified visually from pack thumbnails
CLUBS = [
    # ── England (030-049): trophy at 029, clubs start at 030 ──────────────
    ("281",   30, "Manchester City"),
    ("31",    31, "Liverpool FC"),
    ("11",    32, "Arsenal FC"),
    ("985",   33, "Manchester United"),
    ("631",   34, "Chelsea FC"),
    ("148",   35, "Tottenham Hotspur"),
    ("762",   36, "Newcastle United"),
    ("405",   37, "Aston Villa"),
    ("379",   38, "West Ham United"),
    ("1237",  39, "Brighton & Hove Albion"),
    ("29",    40, "Everton FC"),
    ("1003",  41, "Leicester City"),
    ("873",   42, "Crystal Palace"),
    ("1148",  43, "Brentford FC"),
    ("931",   44, "Fulham FC"),
    ("703",   45, "Nottingham Forest"),
    ("989",   46, "AFC Bournemouth"),
    ("543",   47, "Wolverhampton Wanderers"),
    ("677",   48, "Ipswich Town"),  # placeholder — verify
    ("180",   49, "Southampton FC"),  # placeholder — verify
    # Luton Town dropped (no slot in pack)

    # ── Spain (055-074): trophies at 050-054, clubs start at 055 ──────────
    # VERIFIED visually — Sociedad/Betis order, Osasuna at 069, Las Palmas at 071
    ("418",   55, "Real Madrid"),
    ("131",   56, "FC Barcelona"),
    ("13",    57, "Atlético de Madrid"),
    ("368",   58, "Sevilla FC"),
    ("681",   59, "Real Sociedad"),
    ("150",   60, "Real Betis"),
    ("12321", 61, "Girona FC"),
    ("621",   62, "Athletic Bilbao"),
    ("1050",  63, "Villarreal CF"),
    ("3709",  64, "Getafe CF"),
    ("1049",  65, "Valencia CF"),
    ("940",   66, "Celta de Vigo"),
    ("367",   67, "Rayo Vallecano"),
    ("237",   68, "RCD Mallorca"),
    ("331",   69, "CA Osasuna"),
    ("714",   70, "RCD Espanyol"),
    ("472",   71, "UD Las Palmas"),
    ("1108",  72, "Deportivo Alavés"),
    ("366",   73, "Real Valladolid CF"),
    ("1244",  74, "CD Leganés"),
    # Real Zaragoza dropped (not in pack)

    # ── Germany (080-097): trophies at 075-079, clubs start at 080 ────────
    ("27",    80, "Bayern Munich"),
    ("16",    81, "Borussia Dortmund"),
    ("15",    82, "Bayer 04 Leverkusen"),
    ("23826", 83, "RB Leipzig"),
    ("24",    84, "Eintracht Frankfurt"),
    ("79",    85, "VfB Stuttgart"),
    ("89",    86, "1.FC Union Berlin"),
    ("82",    87, "VfL Wolfsburg"),
    ("60",    88, "SC Freiburg"),
    ("39",    89, "1.FSV Mainz 05"),
    ("18",    90, "Borussia M'gladbach"),
    ("533",   91, "TSG 1899 Hoffenheim"),
    ("167",   92, "FC Augsburg"),
    ("80",    93, "VfL Bochum"),
    ("86",    94, "SV Werder Bremen"),
    ("2036",  95, "1.FC Heidenheim 1846"),
    ("35",    96, "FC St. Pauli"),
    ("269",   97, "Holstein Kiel"),

    # ── Italy (103-122): trophies at 098-102, clubs start at 103 ──────────
    # VERIFIED visually — Genoa is at 117 (not 122 as previously thought)
    ("46",    103, "Inter Milan"),
    ("5",     104, "AC Milan"),
    ("506",   105, "Juventus FC"),
    ("6195",  106, "SSC Napoli"),
    ("12",    107, "AS Roma"),
    ("398",   108, "SS Lazio"),
    ("800",   109, "Atalanta BC"),
    ("430",   110, "ACF Fiorentina"),
    ("1025",  111, "Bologna FC 1909"),
    ("1047",  112, "Como 1907"),
    ("130",   113, "Parma Calcio 1913"),
    ("410",   114, "Udinese Calcio"),
    ("416",   115, "Torino FC"),
    ("276",   116, "Hellas Verona"),
    ("252",   117, "Genoa CFC"),
    ("2919",  118, "AC Monza"),
    ("1390",  119, "Cagliari Calcio"),
    ("749",   120, "FC Empoli"),
    ("1005",  121, "US Lecce"),
    ("607",   122, "Venezia FC"),

    # ── France (128-145): trophies at 123-127, clubs start at 128 ─────────
    ("583",   128, "Paris Saint-Germain"),
    ("162",   129, "AS Monaco"),
    ("244",   130, "Olympique Marseille"),
    ("1082",  131, "LOSC Lille"),
    ("1041",  132, "Olympique Lyon"),
    ("417",   133, "OGC Nice"),
    ("3911",  134, "Stade Brestois 29"),
    ("273",   135, "Stade Rennais FC"),
    ("995",   136, "FC Nantes"),
    ("969",   137, "Montpellier HSC"),
    ("826",   138, "RC Lens"),
    ("667",   139, "RC Strasbourg Alsace"),
    ("415",   140, "FC Toulouse"),
    ("738",   141, "Le Havre AC"),
    ("618",   142, "AS Saint-Étienne"),
    ("1420",  143, "Angers SCO"),
    ("290",   144, "AJ Auxerre"),
    ("1421",  145, "Stade de Reims"),

    # ── Russia (168-175): RPL logo at 167, clubs start at 168 ─────────────
    ("964",   168, "Zenit St. Petersburg"),
    ("2410",  169, "CSKA Moscow"),
    ("232",   170, "Spartak Moscow"),
    ("932",   171, "Lokomotiv Moscow"),
    ("121",   172, "Dynamo Moscow"),
    ("16704", 173, "FC Krasnodar"),
    ("3725",  174, "Akhmat Grozny"),
    ("2696",  175, "Krylya Sovetov"),  # last slot in Russia section
    # FC Rostov dropped (no slot)
]

print("Generating new CLUB_EMBLEMS...\n")
lines = []
for club_id, idx, name in CLUBS:
    emoji_id = idx_to_id.get(idx)
    if emoji_id is None:
        print(f"  WARNING: no emoji at idx {idx} for {name}")
        continue
    lines.append((club_id, idx, emoji_id, name))

# Output as Python dict ready to paste
print("CLUB_EMBLEMS: dict[str, str] = {")
prev_idx = -1
for club_id, idx, emoji_id, name in lines:
    if idx >= 30 and prev_idx < 30:
        print("    # ── England ──")
    elif idx >= 55 and prev_idx < 55:
        print("\n    # ── Spain ──")
    elif idx >= 80 and prev_idx < 80:
        print("\n    # ── Germany ──")
    elif idx >= 103 and prev_idx < 103:
        print("\n    # ── Italy ──")
    elif idx >= 128 and prev_idx < 128:
        print("\n    # ── France ──")
    elif idx >= 168 and prev_idx < 168:
        print("\n    # ── Russia ──")
    print(f'    "{club_id}":' + " " * max(1, 8 - len(club_id)) + f'"{emoji_id}",  # {idx:03} {name}')
    prev_idx = idx
print("}")
