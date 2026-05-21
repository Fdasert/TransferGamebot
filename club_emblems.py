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
    "281":     "5451634514600148959",  # 030 Manchester City
    "31":      "5235684044288580424",  # 031 Liverpool FC
    "11":      "5451784460498388286",  # 032 Arsenal FC
    "985":     "5454387549982180467",  # 033 Manchester United
    "631":     "5454116159588680749",  # 034 Chelsea FC
    "148":     "5348563520063553975",  # 035 Tottenham Hotspur
    "762":     "5452079937068483430",  # 036 Newcastle United
    "405":     "5449785428100008282",  # 037 Aston Villa
    "379":     "5454348349815668487",  # 038 West Ham United
    "1237":    "5454134580703412428",  # 039 Brighton & Hove Albion
    "29":      "5451782682381926727",  # 040 Everton FC
    "1003":    "5370812588823174288",  # 041 Leicester City
    "873":     "5452159312359079937",  # 042 Crystal Palace
    "1148":    "5451766945621754023",  # 043 Brentford FC
    "931":     "5452149592848088708",  # 044 Fulham FC
    "703":     "5453900255877676456",  # 045 Nottingham Forest
    "989":     "5454358112276334880",  # 046 AFC Bournemouth
    "543":     "5453892975908110920",  # 047 Wolverhampton Wanderers
    "180":     "5370584040728452749",  # 048 Southampton FC
    "677":     "5370824928264213927",  # 049 Ipswich Town

    # ── Spain ─────────────────────────────────────────────────────────────────
    "418":     "5452113480763064575",  # 055 Real Madrid
    "131":     "5453946242092515424",  # 056 FC Barcelona
    "13":      "5454144502077866411",  # 057 Atlético de Madrid
    "368":     "5451827685049254968",  # 058 Sevilla FC
    "681":     "5453982044939895376",  # 059 Real Sociedad
    "150":     "5454257747480560228",  # 060 Real Betis
    "12321":   "5454150416247833510",  # 061 Girona FC
    "621":     "5451847094006464615",  # 062 Athletic Bilbao
    "1050":    "5452169332517780725",  # 063 Villarreal CF
    "3709":    "5451651518375675121",  # 064 Getafe CF
    "1049":    "5451700837485134793",  # 065 Valencia CF
    "940":     "5451897744555785919",  # 066 Celta de Vigo
    "367":     "5454292107218928437",  # 067 Rayo Vallecano
    "237":     "5451671416959156776",  # 068 RCD Mallorca
    "331":     "5451613645354059475",  # 069 CA Osasuna
    "714":     "5188545240616689339",  # 070 RCD Espanyol
    "472":     "5451716033079428302",  # 071 UD Las Palmas
    "1108":    "5453863155950178997",  # 072 Deportivo Alavés
    "366":     "5188676928608950656",  # 073 Real Valladolid CF
    "1244":    "5190664605113801024",  # 074 CD Leganés

    # ── Germany ───────────────────────────────────────────────────────────────
    "27":      "5451946135952310496",  # 080 Bayern Munich
    "16":      "5452063500228641711",  # 081 Borussia Dortmund
    "15":      "5451652742441354742",  # 082 Bayer 04 Leverkusen
    "23826":   "5452062744314398188",  # 083 RB Leipzig
    "24":      "5451619812927095039",  # 084 Eintracht Frankfurt
    "79":      "5451704664300996377",  # 085 VfB Stuttgart
    "89":      "5451964827649981662",  # 086 1.FC Union Berlin
    "82":      "5452023346579390944",  # 087 VfL Wolfsburg
    "60":      "5451746282534092987",  # 088 SC Freiburg
    "39":      "5350831949990609606",  # 089 1.FSV Mainz 05
    "18":      "5451991817224472276",  # 090 Borussia M'gladbach
    "533":     "5454217864414249708",  # 091 TSG 1899 Hoffenheim
    "167":     "5451741330436800392",  # 092 FC Augsburg
    "80":      "5451845852760916404",  # 093 VfL Bochum
    "86":      "5451973688167516301",  # 094 SV Werder Bremen
    "2036":    "5454165139395723126",  # 095 1.FC Heidenheim 1846
    "35":      "5190586569853000255",  # 096 FC St. Pauli
    "269":     "5190765476715713529",  # 097 Holstein Kiel

    # ── Italy ─────────────────────────────────────────────────────────────────
    "46":      "5449681859258630925",  # 103 Inter Milan
    "5":       "5451997954732740052",  # 104 AC Milan
    "506":     "5451849031036715618",  # 105 Juventus FC
    "6195":    "5454253693031432207",  # 106 SSC Napoli
    "12":      "5452029501267526739",  # 107 AS Roma
    "398":     "5452093410380890605",  # 108 SS Lazio
    "800":     "5451674139968421562",  # 109 Atalanta BC
    "430":     "5451819039280086241",  # 110 ACF Fiorentina
    "1025":    "5454331053982368121",  # 111 Bologna FC 1909
    "1047":    "5190747858759864377",  # 112 Como 1907
    "130":     "5190467938561316824",  # 113 Parma Calcio 1913
    "410":     "5452015499674142972",  # 114 Udinese Calcio
    "416":     "5449677895003816339",  # 115 Torino FC
    "276":     "5449445898050355657",  # 116 Hellas Verona
    "252":     "5452095240036960063",  # 117 Genoa CFC
    "2919":    "5451664218593967645",  # 118 AC Monza
    "1390":    "5449884951082189710",  # 119 Cagliari Calcio
    "749":     "5454333729746992704",  # 120 FC Empoli
    "1005":    "5454401736259159115",  # 121 US Lecce
    "607":     "5190851900047644792",  # 122 Venezia FC

    # ── France ────────────────────────────────────────────────────────────────
    "583":     "5451717587857590452",  # 128 Paris Saint-Germain
    "162":     "5451674964602144256",  # 129 AS Monaco
    "244":     "5451786423298441711",  # 130 Olympique Marseille
    "1082":    "5449891556741891423",  # 131 LOSC Lille
    "1041":    "5451761800250933649",  # 132 Olympique Lyon
    "417":     "5452114502965280628",  # 133 OGC Nice
    "3911":    "5451979907280158687",  # 134 Stade Brestois 29
    "273":     "5449487305830056656",  # 135 Stade Rennais FC
    "995":     "5453931385800639211",  # 136 FC Nantes
    "969":     "5454067046637650830",  # 137 Montpellier HSC
    "826":     "5452109885875439468",  # 138 RC Lens
    "667":     "5454381652992082715",  # 139 RC Strasbourg Alsace
    "415":     "5449419518361224693",  # 140 FC Toulouse
    "738":     "5452113115690847100",  # 141 Le Havre AC
    "618":     "5454360796630893539",  # 142 AS Saint-Étienne
    "1420":    "5190731086912574416",  # 143 Angers SCO
    "290":     "5190469029483009188",  # 144 AJ Auxerre
    "1421":    "5190711647890594620",  # 145 Stade de Reims

    # ── Saudi Arabia ──────────────────────────────────────────────────────────
    # (club_ids TBD — add when Saudi clubs appear in transfers)

    # ── Portugal ──────────────────────────────────────────────────────────────
    # Benfica, Porto, Sporting CP, Braga — add club_ids when confirmed

    # ── Netherlands ───────────────────────────────────────────────────────────
    # Ajax=158, PSV=159, Feyenoord=160, AZ=161 — add club_ids when confirmed

    # ── Russia ────────────────────────────────────────────────────────────────
    "964":     "5355334694919486478",  # 168 Zenit St. Petersburg
    "2410":    "5354962793701327218",  # 169 CSKA Moscow
    "232":     "5355130602368550127",  # 170 Spartak Moscow
    "932":     "5452133091583739756",  # 171 Lokomotiv Moscow
    "121":     "5454010039536731441",  # 172 Dynamo Moscow
    "16704":   "5354840988428811752",  # 173 FC Krasnodar
    "3725":    "5357089305024019393",  # 174 Akhmat Grozny
    "1083":    "5354878938759840514",  # 175 FC Rostov

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
