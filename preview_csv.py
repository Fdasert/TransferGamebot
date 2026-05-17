import csv, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('fut_players.csv', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print('Total rows:', len(rows))
print()

for r in rows[:6]:
    pac = r['pac']; sho = r['sho']; pas = r['pas']
    dri = r['dri']; df  = r['def']; phy = r['phy']
    name = r['name'][:20].ljust(20)
    nation = r['nation'][:12].ljust(12)
    club = r['club'][:15].ljust(15)
    line = (f"{r['rating']} {name} {nation} {club} "
            f"{r['position']:<4} PAC={pac} SHO={sho} PAS={pas} "
            f"DRI={dri} DEF={df} PHY={phy}  [{r['version']}]")
    print(line)

print()
from collections import Counter
ratings = Counter(int(r['rating']) for r in rows)
for rating in sorted(ratings, reverse=True):
    print(f'  OVR {rating}: {ratings[rating]} players')
