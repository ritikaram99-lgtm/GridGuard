"""Backend tests for the ML Action Engine integration.

Verifies:
- F01 (normal/safe feeder) returns NO_ACTION_REQUIRED.
- F05 (industrial feeder) recommendations.
- F06 at demo origin (2020-01-20 14:00) returns actionable BATTERY recommendation.
- F09 & F10 (EV-heavy feeders) behavior.
- Invalid origin handling (raises ValueError).
- Reserved ML feeders (F01-F10) never fall back to legacy F12/mock data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from app.services.recommendation_service import generate_recommendation
from app.schemas.recommendation import RecommendationStatus
from app.services.ml_adapter_service import is_reserved_ml_feeder_id


DEMO_ORIGIN = "2020-01-20 14:00"


def test_reserved_ml_feeder_ids():
    """Verify F01-F10 are recognized as reserved ML feeder IDs."""
    for i in range(1, 11):
        fid = f"F{i:02d}"
        assert is_reserved_ml_feeder_id(fid) is True
    assert is_reserved_ml_feeder_id("F12") is False


def test_recommendation_f06_demo_origin():
    """Verify F06 at 2020-01-20 14:00 generates a real actionable recommendation."""
    rec = generate_recommendation("F06", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F06"
    assert rec.source in ("ml_action_engine", "ml_prevention_engine")
    assert rec.action_required is True
    assert rec.status == RecommendationStatus.PREVENTED
    assert "BATTERY" in rec.actions
    assert rec.predicted_after < rec.predicted_load
    assert rec.intervention_cost > 0.0
    assert "Elevated risk predicted for feeder F06" in rec.reason


def test_recommendation_f01_safe():
    """Verify F01 at demo origin returns NO_ACTION_REQUIRED."""
    rec = generate_recommendation("F01", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F01"
    assert rec.source in ("ml_action_engine", "ml_prevention_engine")
    assert rec.action_required is False
    assert rec.status == RecommendationStatus.NO_ACTION_REQUIRED
    assert len(rec.actions) == 0


def test_recommendation_f05_industrial():
    """Verify F05 at demo origin returns ML Action Engine response."""
    rec = generate_recommendation("F05", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F05"
    assert rec.source in ("ml_action_engine", "ml_prevention_engine")
    assert rec.status in (RecommendationStatus.NO_ACTION_REQUIRED, RecommendationStatus.PREVENTED)


def test_recommendation_f09_ev_heavy():
    """Verify F09 (EV heavy) returns ML Action Engine response."""
    rec = generate_recommendation("F09", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F09"
    assert rec.source in ("ml_action_engine", "ml_prevention_engine")


def test_recommendation_f10_ev_heavy():
    """Verify F10 (EV heavy) returns ML Action Engine response."""
    rec = generate_recommendation("F10", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F10"
    assert rec.source in ("ml_action_engine", "ml_prevention_engine")


def test_invalid_origin_raises():
    """Verify invalid origin timestamp raises ValueError."""
    with pytest.raises(ValueError, match="origin_datetime"):
        generate_recommendation("F06", origin="2099-01-01 00:00")


def test_no_fallback_to_mock_data_for_ml_feeders():
    """Verify F01-F10 recommendations always carry source='ml_action_engine' and never 'legacy_optimization'."""
    for fid in ["F01", "F05", "F06", "F09", "F10"]:
        rec = generate_recommendation(fid, origin=DEMO_ORIGIN)
        assert rec.source in ("ml_action_engine", "ml_prevention_engine")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
