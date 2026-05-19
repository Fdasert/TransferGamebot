import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import database as db
from club_emblems import CLUB_EMBLEMS

clubs = db.get_client().table("clubs").select("club_id, club_name").execute().data
matched, unmatched = [], []
for c in clubs:
    if c["club_id"] in CLUB_EMBLEMS:
        matched.append(c["club_name"])
    else:
        unmatched.append(f'{c["club_id"]}  ({c["club_name"]})')

print(f"Matched: {len(matched)} / {len(clubs)}")
print()
print("=== NO EMBLEM ===")
for u in sorted(unmatched):
    print(u)
