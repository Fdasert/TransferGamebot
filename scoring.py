"""Pure scoring engine — no side effects, testable standalone."""
from config import ACCURACY_TIERS, ELO_K_CALIBRATION, ELO_K_RATED, CALIBRATION_GAMES


def calculate_deviation(guess: int, actual: int) -> float:
    if actual == 0:
        return 0.0 if guess == 0 else 100.0
    return abs(guess - actual) / actual * 100.0


def get_accuracy_tier(guess: int, actual: int) -> tuple[str, int]:
    """Return (tier_name, base_points) for a guess vs actual fee."""
    dev = calculate_deviation(guess, actual)
    for name, max_dev, pts in ACCURACY_TIERS:
        if name == "exact":
            if dev == 0.0:
                return "exact", pts
        else:
            if dev <= max_dev:
                return name, pts
    return "miss", 0


def calculate_points(guess: int, actual: int, hints_used: int) -> tuple[str, int]:
    """Return (tier_name, final_points) after applying hint penalty."""
    tier, base = get_accuracy_tier(guess, actual)
    points = max(0, base - hints_used)
    return tier, points


def calculate_elo(
    rating_a: int,
    rating_b: int,
    score_a: int,
    score_b: int,
    is_calibrated_a: bool,
    is_calibrated_b: bool,
    games_played_a: int,
    games_played_b: int,
    rounds_a: list[dict] | None = None,
    rounds_b: list[dict] | None = None,
) -> tuple[int, int, int, int]:
    """
    Performance-based ELO with skill bonuses.

    Performance score = share of total points scored (continuous, not binary).
    Bonuses: +ELO_EXACT_BONUS per exact guess, +ELO_CLOSE_BONUS per ±5% guess.
    Penalty: -ELO_HINT_PENALTY per hint used.

    Returns (new_rating_a, new_rating_b, delta_a, delta_b).
    """
    from config import ELO_EXACT_BONUS, ELO_CLOSE_BONUS, ELO_HINT_PENALTY

    k_a = ELO_K_CALIBRATION if not is_calibrated_a else ELO_K_RATED
    k_b = ELO_K_CALIBRATION if not is_calibrated_b else ELO_K_RATED

    # Expected scores from ELO formula
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a

    # Performance score: share of total points (continuous 0→1)
    total = score_a + score_b
    if total == 0:
        perf_a = perf_b = 0.5
    else:
        perf_a = score_a / total
        perf_b = score_b / total

    # Base ELO delta from performance
    delta_a = k_a * (perf_a - expected_a)
    delta_b = k_b * (perf_b - expected_b)

    # Skill bonuses from round results
    def _skill_bonus(rounds: list[dict] | None) -> float:
        if not rounds:
            return 0.0
        bonus = 0.0
        for r in rounds:
            if not r.get("completed"):
                continue
            tier = r.get("accuracy_tier", "miss")
            if tier == "exact":
                bonus += ELO_EXACT_BONUS
            elif tier == "5pct":
                bonus += ELO_CLOSE_BONUS
            bonus -= (r.get("hints_used") or 0) * ELO_HINT_PENALTY
        return bonus

    delta_a += _skill_bonus(rounds_a)
    delta_b += _skill_bonus(rounds_b)

    new_a = round(rating_a + delta_a)
    new_b = round(rating_b + delta_b)

    # Minimum rating floor = 100
    new_a = max(100, new_a)
    new_b = max(100, new_b)

    return new_a, new_b, round(delta_a), round(delta_b)


def format_fee(amount: int | None) -> str:
    if amount is None:
        return "Неизвестно"
    if amount == 0:
        return "Бесплатно"
    if amount >= 1_000_000:
        val = amount / 1_000_000
        return f"€{val:g}M"
    if amount >= 1_000:
        val = amount / 1_000
        return f"€{val:g}K"
    return f"€{amount:,}"


def parse_fee_input(text: str) -> int | None:
    """Parse user fee input like '45M', '45.5m', '500K', '45000000'. Returns euros."""
    text = text.strip().replace(",", "").replace(".", "").replace(" ", "")
    text_lower = text.lower()

    try:
        if text_lower.endswith("m"):
            return int(float(text[:-1].replace(",", ".")) * 1_000_000)
        if text_lower.endswith("k"):
            return int(float(text[:-1].replace(",", ".")) * 1_000)
        return int(text)
    except (ValueError, AttributeError):
        return None


# ── Self-tests ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        # (guess, actual, hints, expected_tier, expected_pts)
        (100_000_000, 100_000_000, 0, "exact", 10),
        (100_000_000, 100_000_000, 1, "exact", 9),
        (100_000_000, 100_000_000, 2, "exact", 8),
        (104_000_000, 100_000_000, 0, "5pct",  8),   # 4% off
        (110_000_000, 100_000_000, 0, "10pct", 6),   # 10% off
        (118_000_000, 100_000_000, 0, "20pct", 4),   # 18% off
        (130_000_000, 100_000_000, 0, "miss",  0),   # 30% off
        (130_000_000, 100_000_000, 2, "miss",  0),   # miss + 2 hints = still 0
        (106_000_000, 100_000_000, 1, "10pct", 5),   # 6% off, 1 hint → 6-1=5
    ]
    all_ok = True
    for guess, actual, hints, exp_tier, exp_pts in tests:
        tier, pts = calculate_points(guess, actual, hints)
        ok = tier == exp_tier and pts == exp_pts
        status = "✓" if ok else "✗"
        if not ok:
            all_ok = False
        print(f"{status} guess={format_fee(guess)} actual={format_fee(actual)} hints={hints} → {tier}/{pts} (expected {exp_tier}/{exp_pts})")

    print()
    # parse_fee_input tests
    parse_tests = [
        ("45M", 45_000_000),
        ("45.5M", 45_500_000),
        ("500K", 500_000),
        ("45000000", 45_000_000),
        ("abc", None),
    ]
    for inp, expected in parse_tests:
        result = parse_fee_input(inp)
        ok = result == expected
        if not ok:
            all_ok = False
        print(f"{'✓' if ok else '✗'} parse_fee_input({inp!r}) = {result} (expected {expected})")

    print()
    print("All tests passed ✓" if all_ok else "SOME TESTS FAILED ✗")
