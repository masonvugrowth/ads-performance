"""Detector implementations.

Each module below registers one detector via @register. Importing this package
triggers all @register decorators.

Currently implemented (13 detectors that work with existing synced data):
- Phase 3 smoke-test detectors (5)
- Phase 6 extensions (8)

Detectors requiring sync_engine expansion (ad_strength, bidding_strategy_type,
attribution_model, AI Max settings, impression_share, search_term_report,
brand_exclusions list, audience signals, conversion action metadata,
policy_summary) are tracked in the plan file but not yet implemented here —
they would register but never fire until google_sync_engine captures those
fields.
"""

from app.services.google_recommendations.detectors import (  # noqa: F401
    # Phase 3 smoke-test detectors
    dg_missing_video,
    pmax_learning_stuck,
    seasonality_lead_time_approaching,
    budget_mix_off_target,
    zero_conversions_2d,
    # Phase 6 extensions
    dg_ctr_below_benchmark,
    rsa_insufficient_assets,
    pmax_asset_group_incomplete,
    pmax_tcpa_change_too_large,
    spend_vs_budget_anomaly,
    impressions_drop_50,
    ctr_spike_100,
    budget_daily_exhausted_early,
    pmax_branded_leak,
    conv_ads_vs_pms_delta,
    seasonality_tcpa_adjust_due,
    low_season_shift_to_demandgen,
)
