"""
Automated Test Suite for PRAHARI Feature Upgrade Pack v1.
Validates:
- Config JSON schema extension
- Explainable alerts + confidence-gated degradation
- RiskEngine predictive deviation generation and risk formula
- ProcedureScorer metrics calculation
- OutcomeVerifier modes (vision_only, vision+brightness, vision+mock_sensor)
- Digital Twin Failure Injector harness
"""

import os
import sys
import json
import time
import numpy as np

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))

from validator import ExperimentValidator
from risk_engine import RiskEngine
from scorer import ProcedureScorer
from verifier import OutcomeVerifier
from logger import SessionLogger
from object_tracker import ObjectTracker
from failure_injector import DigitalTwinFailureInjector


def test_config_schema():
    print("[TEST] 1. Testing Config Schema Extension...")
    config_path = "config/desk_objects_experiment.json"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    assert "steps" in cfg and len(cfg["steps"]) == 7
    assert "rois" in cfg and "log_zone" in cfg["rois"]

    # Verify additive fields
    step_5 = next(s for s in cfg["steps"] if s["id"] == 5)
    assert step_5["severity"] == 0.95
    assert step_5["irreversible"] is True
    assert "storage_zone" in step_5["expected_targets"]
    print("  -> PASSED: Config schema contains all Addendum fields.")


def test_confidence_gating_and_explainable_alerts():
    print("[TEST] 2. Testing Confidence-Gated Degradation & Explainable Alerts...")
    with open("config/desk_objects_experiment.json", "r") as f:
        cfg = json.load(f)

    logger = SessionLogger("test_exp", logs_dir="logs/test")
    scorer = ProcedureScorer(total_steps=7)
    validator = ExperimentValidator(
        experiment_config=cfg,
        session_logger=logger,
        procedure_scorer=scorer,
    )

    # 1. Low Confidence (<0.5) -> UNVERIFIABLE
    low_conf_ev = {
        "type": "object_in_roi:book:log_zone",
        "confidence": 0.42,
        "timestamp": time.time(),
    }
    res_low = validator.process_event(low_conf_ev)
    assert res_low is not None and res_low["status"] == "UNVERIFIABLE"
    assert 1 not in validator.completed_step_ids
    assert scorer.unverifiable_count == 1

    # 2. Medium Confidence (0.5 - 0.8) -> Hold for confirmation
    med_conf_ev = {
        "type": "object_in_roi:book:log_zone",
        "confidence": 0.65,
        "timestamp": time.time(),
    }
    res_med_1 = validator.process_event(med_conf_ev)
    assert res_med_1 is not None and res_med_1["status"] == "CONFIRMING"
    assert 1 not in validator.completed_step_ids

    # Second frame confirmation -> Auto-accepts
    res_med_2 = validator.process_event(med_conf_ev)
    assert res_med_2 is not None and res_med_2["status"] == "OK"
    assert 1 in validator.completed_step_ids

    # 3. Out of sequence with high confidence -> Explainable Alert
    early_bottle_ev = {
        "type": "object_in_roi:bottle:staging_zone",
        "confidence": 0.95,
        "timestamp": time.time(),
    }
    res_alert = validator.process_event(early_bottle_ev)
    assert res_alert is not None and res_alert["status"] == "OUT_OF_SEQUENCE"
    alert = res_alert["alert_payload"]
    assert "expected" in alert
    assert "detected" in alert
    assert alert["confidence"] == 0.95
    assert "recommended_action" in alert
    print("  -> PASSED: Confidence gating and Explainable Alerts verified.")


def test_predictive_risk_engine():
    print("[TEST] 3. Testing Predictive Risk Engine & Extrapolation...")
    rois = {
        "staging_zone": [20, 40, 220, 220],
        "log_zone": [100, 120, 540, 460],
        "storage_zone": [420, 40, 620, 220],
    }
    engine = RiskEngine(rois=rois, risk_threshold=0.4, extrapolation_horizon_seconds=0.8)

    # Step: place_bottle_staging in staging_zone, confusable target is storage_zone
    step_bottle_staging = {
        "id": 4,
        "name": "place_bottle_staging",
        "expected_targets": ["staging_zone"],
        "confusable_targets": ["storage_zone"],
        "severity": 0.8,
        "irreversible": True,
    }

    # Simulate hand moving towards storage_zone (center ~520, 130)
    t0 = time.time()
    trajectories = {
        "hand_any": [
            (250, 130, t0),
            (290, 130, t0 + 0.1),
            (330, 130, t0 + 0.2),
            (370, 130, t0 + 0.3),
        ]
    }

    risk_event = engine.evaluate(trajectories, step_bottle_staging, now=t0 + 0.3)
    assert risk_event is not None
    assert risk_event["type"] == "predicted_deviation"
    assert risk_event["predicted_wrong_target"] == "storage_zone"
    assert risk_event["risk_score"] >= 0.4
    assert risk_event["irreversible"] is True
    print(f"  -> PASSED: Risk Engine generated predicted_deviation with Risk={risk_event['risk_score']}")


def test_procedure_scorer():
    print("[TEST] 4. Testing Procedure-Quality Scorer...")
    scorer = ProcedureScorer(
        total_steps=7,
        expected_duration_seconds=60.0,
        weight_accuracy=0.5,
        weight_speed=0.2,
        weight_cleanliness=0.3,
    )
    # Simulate 7 completed OK steps, 1 deviation, 1 predictive warning
    for s_id in range(1, 8):
        scorer.on_step_ok(s_id)
    scorer.on_deviation(5)
    scorer.on_predictive_warning(5)

    score_data = scorer.compute_score(current_time=scorer.start_time + 45.0)
    assert score_data["accuracy"] == 100.0
    assert score_data["speed_factor"] == 1.0  # completed in 45s <= 60s
    assert score_data["deviations"] == 1
    assert score_data["predictive_warnings"] == 1
    assert 80.0 <= score_data["overall_score"] <= 100.0
    print(f"  -> PASSED: Procedure Quality Score calculated: {score_data['overall_score']}%")


def test_outcome_verifier():
    print("[TEST] 5. Testing Multi-Modal Outcome Verifier...")
    rois = {"staging_zone": [20, 40, 220, 220]}
    verifier = OutcomeVerifier(rois=rois)

    # 1. vision_only
    step_v = {"verification": {"mode": "vision_only"}}
    pass_v, msg_v, _ = verifier.verify_step_outcome(step_v)
    assert pass_v is True

    # 2. vision+brightness
    dark_frame = np.zeros((240, 240, 3), dtype=np.uint8)
    verifier.capture_baseline(dark_frame, "staging_zone")

    bright_frame = np.full((240, 240, 3), 120, dtype=np.uint8)
    step_bright = {
        "verification": {
            "mode": "vision+brightness",
            "target_roi": "staging_zone",
            "brightness_delta_threshold": 10.0,
        }
    }
    pass_b, msg_b, metrics_b = verifier.verify_step_outcome(step_bright, bright_frame)
    assert pass_b is True
    assert metrics_b["delta"] >= 10.0

    # 3. vision+mock_sensor
    step_sensor = {"verification": {"mode": "vision+mock_sensor"}}
    verifier.set_mock_sensor(confirmed=True, reading=3.3)
    pass_s1, _, _ = verifier.verify_step_outcome(step_sensor)
    assert pass_s1 is True

    verifier.set_mock_sensor(confirmed=False, reading=0.0)
    pass_s2, _, _ = verifier.verify_step_outcome(step_sensor)
    assert pass_s2 is False
    print("  -> PASSED: Outcome Verifier modes (vision, brightness, mock sensor) verified.")


def test_digital_twin_failure_injector():
    print("[TEST] 6. Testing Digital Twin Failure Injector Harness...")
    injector = DigitalTwinFailureInjector("config/desk_objects_experiment.json")
    results = injector.run_benchmark_suite()
    assert results["total_injections"] >= 5
    assert results["detection_rate_pct"] >= 80.0
    print("  -> PASSED: Failure injector benchmark suite completed successfully.")


if __name__ == "__main__":
    test_config_schema()
    test_confidence_gating_and_explainable_alerts()
    test_predictive_risk_engine()
    test_procedure_scorer()
    test_outcome_verifier()
    test_digital_twin_failure_injector()
    print("\nALL 6 UPGRADE PACK TEST SUITES PASSED SUCCESSFULLY!")
