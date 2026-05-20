"""Verify CLUB_EMBLEMS against actual pack indices."""
import json
import sys
import io
import re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from club_emblems import CLUB_EMBLEMS

with open(r"C:\Users\fdasert\Documents\pack_full.json", encoding="utf-8") as f:
    pack = json.load(f)

id_to_idx = {item["custom_emoji_id"]: item["index"] for item in pack}

with open("club_emblems.py", encoding="utf-8") as f:
    src = f.read()

pattern = re.compile(r'"(\d+)":\s*"(\d+)",\s*#\s*(\d+)\s+(.+)')
print(f"{'club_id':<8} {'exp':<5} {'act':<5} {'name':<30} status")
print("-" * 75)

mismatches = []
for m in pattern.finditer(src):
    club_id, emoji_id, expected_idx_str, name = m.groups()
    name = name.strip()
    expected_idx = int(expected_idx_str)
    actual_idx = id_to_idx.get(emoji_id, -1)
    if actual_idx != expected_idx:
        mismatches.append((club_id, name, emoji_id, expected_idx, actual_idx))
        status = f"MISMATCH (off by {actual_idx - expected_idx})"
    else:
        status = "OK"
    print(f"{club_id:<8} {expected_idx:<5} {actual_idx:<5} {name:<30} {status}")

print()
print(f"Total mismatches: {len(mismatches)}")

# Show context around problem clubs: what emoji is at each index
print("\n=== Pack context for key clubs ===")
for check_idx in [29, 30, 54, 55, 80, 102, 128, 167]:
    items = [p for p in pack if p["index"] == check_idx]
    if items:
        p = items[0]
        print(f"  idx {check_idx:3}: emoji={p['emoji']!r:8} id={p['custom_emoji_id']} unique_id={p['file_unique_id']}")

