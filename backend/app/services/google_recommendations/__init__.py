"""Google Ads Power Pack Recommendation Engine.

SOP-driven detectors + Claude enrichment + applier. Surfaces optimization
recommendations on top of the existing Google Ads sync pipeline.

Entry points:
- engine.run_recommendations(db, cadence)  — orchestrator
- applier.apply_recommendation(db, rec_id) — executes via google_actions
- registry.all_detectors() / registry.by_cadence(tag)
"""

from app.services.google_recommendations.base import (
    Detector,
    DetectorFinding,
    DetectorTarget,
)
from app.services.google_recommendations.catalog import CATALOG, RecTypeSpec
from app.services.google_recommendations.registry import (
    all_detectors,
    by_cadence,
    get_detector,
    register,
)

__all__ = [
    "Detector",
    "DetectorFinding",
    "DetectorTarget",
    "CATALOG",
    "RecTypeSpec",
    "all_detectors",
    "by_cadence",
    "get_detector",
    "register",
]
