-- Migration 015 — Website/offline revenue split + ad×country breakdown
-- Paste this entire file into the Supabase SQL editor. Safe to run multiple
-- times thanks to IF NOT EXISTS everywhere and a conditional alembic_version
-- bump at the bottom.
--
-- Use this when the automatic alembic upgrade on Zeabur cannot run (e.g.
-- because the deployed image still carries the pre-fix 015 migration that
-- raced alembic's own version bump). Running this SQL stamps the schema to
-- 015 so the next container start sees "no upgrades needed" and boots cleanly.

BEGIN;

SET LOCAL statement_timeout = 0;

-- ── metrics_cache: split revenue into website (pixel) vs offline upload ─
ALTER TABLE metrics_cache
    ADD COLUMN IF NOT EXISTS revenue_website NUMERIC(15,2) NOT NULL DEFAULT 0;
ALTER TABLE metrics_cache
    ADD COLUMN IF NOT EXISTS revenue_offline NUMERIC(15,2) NOT NULL DEFAULT 0;

-- ── ad_country_metrics: per-(ad|campaign)×date×country breakdown ────────
CREATE TABLE IF NOT EXISTS ad_country_metrics (
    id                   VARCHAR(36) PRIMARY KEY,
    platform             VARCHAR(20) NOT NULL,
    campaign_id          VARCHAR(36) NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    ad_id                VARCHAR(36)          REFERENCES ads(id)       ON DELETE CASCADE,
    date                 DATE        NOT NULL,
    country              VARCHAR(4)  NOT NULL,
    spend                NUMERIC(15,2) NOT NULL DEFAULT 0,
    impressions          INTEGER       NOT NULL DEFAULT 0,
    clicks               INTEGER       NOT NULL DEFAULT 0,
    revenue_website      NUMERIC(15,2) NOT NULL DEFAULT 0,
    revenue_offline      NUMERIC(15,2) NOT NULL DEFAULT 0,
    conversions_website  INTEGER       NOT NULL DEFAULT 0,
    conversions_offline  INTEGER       NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_date
    ON ad_country_metrics(date);
CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_platform_date
    ON ad_country_metrics(platform, date);
CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_ad_date
    ON ad_country_metrics(ad_id, date);
CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_campaign_date
    ON ad_country_metrics(campaign_id, date);

-- Partial unique indexes: at most one row per ad|campaign × date × country
CREATE UNIQUE INDEX IF NOT EXISTS uix_ad_country_metrics_ad
    ON ad_country_metrics(ad_id, date, country)
    WHERE ad_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uix_ad_country_metrics_campaign
    ON ad_country_metrics(campaign_id, date, country)
    WHERE ad_id IS NULL;

-- ── booking_matches: record which ad + which purchase kind produced each match ─
ALTER TABLE booking_matches
    ADD COLUMN IF NOT EXISTS ad_id         VARCHAR(36);
ALTER TABLE booking_matches
    ADD COLUMN IF NOT EXISTS ad_name       VARCHAR(500);
ALTER TABLE booking_matches
    ADD COLUMN IF NOT EXISTS purchase_kind VARCHAR(20);

CREATE INDEX IF NOT EXISTS ix_booking_matches_ad_id
    ON booking_matches(ad_id);

-- ── Bump alembic_version to 015 ────────────────────────────────────────
-- Conditional: only bump if currently at 014. Re-running this file after
-- the version already moved to 015 is a no-op.
UPDATE alembic_version
   SET version_num = '015_ad_country_matching'
 WHERE version_num = '014_booking_rate_plan';

COMMIT;

-- Sanity check after commit — should print one row with '015_ad_country_matching':
-- SELECT version_num FROM alembic_version;
