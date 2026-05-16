-- Casino migration: global roulette tables
-- Run once in Supabase SQL editor before starting the bot.

-- Single-row table that holds the current round state
CREATE TABLE IF NOT EXISTS global_roulette (
    id            INTEGER PRIMARY KEY DEFAULT 1,
    round         INTEGER      NOT NULL DEFAULT 0,
    pot           BIGINT       NOT NULL DEFAULT 0,
    last_spin_at  TIMESTAMPTZ
);

-- Seed the single row (idempotent)
INSERT INTO global_roulette (id, round, pot)
VALUES (1, 0, 0)
ON CONFLICT (id) DO NOTHING;

-- Individual bets per round
CREATE TABLE IF NOT EXISTS global_roulette_bets (
    id         BIGSERIAL    PRIMARY KEY,
    round      INTEGER      NOT NULL,
    user_id    BIGINT       NOT NULL,
    amount     BIGINT       NOT NULL,
    created_at TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grb_round ON global_roulette_bets (round);
