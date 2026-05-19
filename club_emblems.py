"""
Club custom emoji mapping — Football_emoji_24 pack.
key   = club_id (integer as string) from DB clubs table
value = custom_emoji_id from the Telegram sticker pack

Pack indices for reference:
  000-006  ⚽ generic awards
  007-021  🏆 trophies / competition logos
  022-049  🏴 England (28)
  050-074  🇪🇸 Spain   (25)
  075-097  🇩🇪 Germany (23)
  098-122  🇮🇹 Italy   (25)
  123-145  🇫🇷 France  (23)
  146-152  🇸🇦 Saudi   (7)
  153-157  🇵🇹 Portugal(5)
  158-162  🇳🇱 Netherlands(5)
  163-166  🇺🇸 USA     (4)
  167-175  🇷🇺 Russia  (9)
  176-179  🇹🇷 Turkey  (4)
  180-182  🇧🇷 Brazil  (3)
  183-184  🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland(2)
  185-186  🇨🇭 Swiss   (2)
  187      🇩🇰 Denmark (1)
  188      🇲🇽 Mexico  (1)
  189-190  🇧🇪 Belgium (2)
  191-192  🇺🇦 Ukraine (2)
  193-194  🇦🇷 Argentina(2)
  195      🇭🇷 Croatia (1)
  196      🇬🇷 Greece  (1)
  197      🇸🇰 Slovakia(1)
  198      🇨🇿 Czech   (1)
"""

CLUB_EMBLEMS: dict[str, str] = {

    # ── England ───────────────────────────────────────────────────────────────
    "281":   "5190489752700211730",  # 029 Manchester City
    "31":    "5451634514600148959",  # 030 Liverpool FC
    "11":    "5235684044288580424",  # 031 Arsenal FC
    "985":   "5451784460498388286",  # 032 Manchester United
    "631":   "5454387549982180467",  # 033 Chelsea FC
    "148":   "5454116159588680749",  # 034 Tottenham Hotspur
    "762":   "5348563520063553975",  # 035 Newcastle United
    "405":   "5452079937068483430",  # 036 Aston Villa
    "379":   "5449785428100008282",  # 037 West Ham United
    "1237":  "5454348349815668487",  # 038 Brighton & Hove Albion
    "29":    "5454134580703412428",  # 039 Everton FC
    "1003":  "5451782682381926727",  # 040 Leicester City
    "873":   "5370812588823174288",  # 041 Crystal Palace
    "1148":  "5452159312359079937",  # 042 Brentford FC
    "931":   "5451766945621754023",  # 043 Fulham FC
    "703":   "5452149592848088708",  # 044 Nottingham Forest
    "989":   "5453900255877676456",  # 045 AFC Bournemouth
    "543":   "5454358112276334880",  # 046 Wolverhampton Wanderers
    "677":   "5453892975908110920",  # 047 Ipswich Town
    "180":   "5370584040728452749",  # 048 Southampton FC
    "1031":  "5370824928264213927",  # 049 Luton Town

    # ── Spain ─────────────────────────────────────────────────────────────────
    "418":   "5352835363255633566",  # 054 Real Madrid
    "131":   "5452113480763064575",  # 055 FC Barcelona
    "13":    "5453946242092515424",  # 056 Atlético de Madrid
    "368":   "5454144502077866411",  # 057 Sevilla FC
    "150":   "5451827685049254968",  # 058 Real Betis
    "681":   "5453982044939895376",  # 059 Real Sociedad
    "12321": "5454257747480560228",  # 060 Girona FC
    "621":   "5454150416247833510",  # 061 Athletic Bilbao
    "1050":  "5451847094006464615",  # 062 Villarreal CF
    "331":   "5452169332517780725",  # 063 CA Osasuna
    "3709":  "5451651518375675121",  # 064 Getafe CF
    "1049":  "5451700837485134793",  # 065 Valencia CF
    "940":   "5451897744555785919",  # 066 Celta de Vigo
    "367":   "5454292107218928437",  # 067 Rayo Vallecano
    "237":   "5451671416959156776",  # 068 RCD Mallorca
    "714":   "5451613645354059475",  # 069 RCD Espanyol
    "1108":  "5188545240616689339",  # 070 Deportivo Alavés
    "366":   "5451716033079428302",  # 071 Real Valladolid CF
    "1244":  "5453863155950178997",  # 072 CD Leganés
    "472":   "5188676928608950656",  # 073 UD Las Palmas
    "142":   "5190664605113801024",  # 074 Real Zaragoza

    # ── Germany ───────────────────────────────────────────────────────────────
    "27":    "5451946135952310496",  # 080 Bayern Munich
    "16":    "5452063500228641711",  # 081 Borussia Dortmund
    "15":    "5451652742441354742",  # 082 Bayer 04 Leverkusen
    "23826": "5452062744314398188",  # 083 RB Leipzig
    "24":    "5451619812927095039",  # 084 Eintracht Frankfurt
    "79":    "5451704664300996377",  # 085 VfB Stuttgart
    "89":    "5451964827649981662",  # 086 1.FC Union Berlin
    "82":    "5452023346579390944",  # 087 VfL Wolfsburg
    "60":    "5451746282534092987",  # 088 SC Freiburg
    "39":    "5350831949990609606",  # 089 1.FSV Mainz 05
    "18":    "5451991817224472276",  # 090 Borussia M'gladbach
    "533":   "5454217864414249708",  # 091 TSG 1899 Hoffenheim
    "167":   "5451741330436800392",  # 092 FC Augsburg
    "80":    "5451845852760916404",  # 093 VfL Bochum
    "86":    "5451973688167516301",  # 094 SV Werder Bremen
    "2036":  "5454165139395723126",  # 095 1.FC Heidenheim 1846
    "35":    "5190586569853000255",  # 096 FC St. Pauli
    "269":   "5190765476715713529",  # 097 Holstein Kiel

    # ── Italy ─────────────────────────────────────────────────────────────────
    "46":    "5352993950628069119",  # 102 Inter Milan
    "5":     "5449681859258630925",  # 103 AC Milan
    "506":   "5451997954732740052",  # 104 Juventus FC
    "6195":  "5451849031036715618",  # 105 SSC Napoli
    "12":    "5454253693031432207",  # 106 AS Roma
    "398":   "5452029501267526739",  # 107 SS Lazio
    "800":   "5452093410380890605",  # 108 Atalanta BC
    "430":   "5451674139968421562",  # 109 ACF Fiorentina
    "1025":  "5451819039280086241",  # 110 Bologna FC 1909
    "416":   "5454331053982368121",  # 111 Torino FC
    "1047":  "5190747858759864377",  # 112 Como 1907
    "130":   "5190467938561316824",  # 113 Parma Calcio 1913
    "410":   "5452015499674142972",  # 114 Udinese Calcio
    "276":   "5449677895003816339",  # 115 (Hellas Verona — check vs 116)
    "2919":  "5452095240036960063",  # 116 AC Monza / 117?
    "1390":  "5451664218593967645",  # 117 Cagliari Calcio
    "749":   "5449884951082189710",  # 118 FC Empoli
    "1005":  "5454333729746992704",  # 119 US Lecce
    "607":   "5454401736259159115",  # 121 Venezia FC
    "252":   "5190851900047644792",  # 122 Genoa CFC

    # ── France ────────────────────────────────────────────────────────────────
    "583":   "5451717587857590452",  # 128 Paris Saint-Germain
    "162":   "5451674964602144256",  # 129 AS Monaco
    "244":   "5451786423298441711",  # 130 Olympique Marseille
    "1082":  "5449891556741891423",  # 131 LOSC Lille
    "1041":  "5451761800250933649",  # 132 Olympique Lyon
    "417":   "5452114502965280628",  # 133 OGC Nice
    "3911":  "5451979907280158687",  # 134 Stade Brestois 29
    "273":   "5449487305830056656",  # 135 Stade Rennais FC
    "995":   "5453931385800639211",  # 136 FC Nantes
    "969":   "5454067046637650830",  # 137 Montpellier HSC
    "826":   "5452109885875439468",  # 138 RC Lens
    "667":   "5454381652992082715",  # 139 RC Strasbourg Alsace
    "415":   "5449419518361224693",  # 140 FC Toulouse
    "738":   "5452113115690847100",  # 141 Le Havre AC
    "618":   "5454360796630893539",  # 142 AS Saint-Étienne
    "1420":  "5190731086912574416",  # 143 Angers SCO
    "290":   "5190469029483009188",  # 144 AJ Auxerre
    "1421":  "5190711647890594620",  # 145 Stade de Reims

    # ── Saudi Arabia ──────────────────────────────────────────────────────────
    # (club_ids TBD — add when Saudi clubs appear in transfers)

    # ── Portugal ──────────────────────────────────────────────────────────────
    # Benfica, Porto, Sporting CP, Braga — add club_ids when confirmed

    # ── Netherlands ───────────────────────────────────────────────────────────
    # Ajax=158, PSV=159, Feyenoord=160, AZ=161 — add club_ids when confirmed

    # ── Russia ────────────────────────────────────────────────────────────────
    "964":   "5399862884324884896",  # 167 Zenit St. Petersburg
    "2410":  "5355334694919486478",  # 168 CSKA Moscow
    "232":   "5354962793701327218",  # 169 Spartak Moscow
    "932":   "5355130602368550127",  # 170 Lokomotiv Moscow
    "121":   "5452133091583739756",  # 171 Dynamo Moscow
    "16704": "5454010039536731441",  # 172 FC Krasnodar
    "3725":  "5354840988428811752",  # 173 Akhmat Grozny
    "2696":  "5357089305024019393",  # 174 Krylya Sovetov
    "1083":  "5354878938759840514",  # 175 FC Rostov

    # ── Turkey ────────────────────────────────────────────────────────────────
    # Galatasaray, Fenerbahce, Trabzonspor, Besiktas — add club_ids when confirmed

    # ── Scotland ──────────────────────────────────────────────────────────────
    # Celtic=183, Rangers=184 — add club_ids when confirmed
}


def club_emblem_html(club_id: int | str, fallback: str = "🏟") -> str:
    """Return HTML <tg-emoji> tag for a club, or plain fallback if not mapped."""
    eid = CLUB_EMBLEMS.get(str(club_id))
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


def has_emblem(club_id: int | str) -> bool:
    return str(club_id) in CLUB_EMBLEMS
