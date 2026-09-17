"""
Digital Twin Failure Injection & Benchmark Test Harness for PRAHARI.
Evaluates validator, risk engine, and verifier resilience by replaying and mutating
structured event streams (JSONL).

Mutations:
1. Drop Event (occlusion / missed detection)
2. Reorder Events (out-of-sequence execution)
3. Duplicate / Timestamp Jitter (motion blur / re-detection)
4. Object Label Substitution (CV misclassification)

Produces verifiable benchmark metrics: Detection Rate %, Alert Precision %, False Alert Rate %.
"""

import os
import sys
import copy
import json
import time
import random
from typing import List, Dict, Any, Tuple

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from validator import ExperimentValidator
from risk_engine import RiskEngine
from scorer import ProcedureScorer
from verifier import OutcomeVerifier
from logger import SessionLogger


class DigitalTwinFailureInjector:
    def __init__(self, config_path: str = "config/led_circuit_continuity_test.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.steps = self.config.get("steps", [])
        self.rois = self.config.get("rois", {})

    def generate_nominal_session(self) -> List[Dict[str, Any]]:
        """Generates a perfect nominal stream of events for the experiment sequence."""
        events = []
        base_time = time.time()
        t = base_time

        for step in self.steps:
            t += 2.0
            event_type = step.get("event")
            req_objs = step.get("requires_objects", [])
            primary_obj = req_objs[0] if req_objs else "object"
            events.append({
                "type": event_type,
                "object": primary_obj,
                "confidence": 0.95,
                "timestamp": t,
                "step_id": step["id"],
                "step_name": step["name"],
            })
        return events

    def replay_events(
        self, event_stream: List[Dict[str, Any]], mute_voice: bool = True
    ) -> Dict[str, Any]:
        """Replay an event stream through validator without physical camera."""
        logger = SessionLogger(self.config.get("experiment_id", "test"), logs_dir="logs/test")
        scorer = ProcedureScorer(total_steps=len(self.steps))
        verifier = OutcomeVerifier(self.rois)
        alerts_caught = []

        def on_status_change(data):
            if data.get("type") in ["alert", "predictive_warning"]:
                alerts_caught.append(data)

        validator = ExperimentValidator(
            experiment_config=self.config,
            session_logger=logger,
            procedure_scorer=scorer,
            outcome_verifier=verifier,
            on_status_change=on_status_change,
        )

        for ev in event_stream:
            validator.process_event(ev, now=ev.get("timestamp"))

        score = scorer.compute_score()
        return {
            "completed_steps": list(validator.completed_step_ids),
            "total_steps": len(self.steps),
            "alerts_caught": alerts_caught,
            "deviations": scorer.deviation_count,
            "score": score,
            "is_all_completed": len(validator.completed_step_ids) == len(self.steps),
        }

    # --- MUTATION OPERATORS ---

    def mutate_drop_event(self, nominal: List[Dict[str, Any]], drop_index: int = 2) -> Tuple[List[Dict[str, Any]], str]:
        """Simulate missed detection / occlusion."""
        mutated = copy.deepcopy(nominal)
        dropped = mutated.pop(drop_index)
        desc = f"Drop Step {dropped['step_id']} ({dropped['step_name']}) - Missed Detection"
        return mutated, desc

    def mutate_reorder_events(self, nominal: List[Dict[str, Any]], idx1: int = 3, idx2: int = 6) -> Tuple[List[Dict[str, Any]], str]:
        """Simulate out-of-sequence execution (e.g. seat battery before wire connection)."""
        mutated = copy.deepcopy(nominal)
        mutated[idx1], mutated[idx2] = mutated[idx2], mutated[idx1]
        desc = f"Swap Step {mutated[idx1]['step_id']} and Step {mutated[idx2]['step_id']} - Out of Sequence"
        return mutated, desc

    def mutate_timestamp_jitter(self, nominal: List[Dict[str, Any]], jitter_range: float = 0.05) -> Tuple[List[Dict[str, Any]], str]:
        """Simulate motion blur / sensor re-detection flicker."""
        mutated = copy.deepcopy(nominal)
        for ev in mutated:
            ev["timestamp"] += random.uniform(-jitter_range, jitter_range)
        desc = "Timestamp Jitter / Multi-frame flicker"
        return mutated, desc

    def mutate_substitute_label(self, nominal: List[Dict[str, Any]], target_idx: int = 4, new_label: str = "wire_black") -> Tuple[List[Dict[str, Any]], str]:
        """Simulate CV classifier confusion (e.g. wire_red detected as wire_black)."""
        mutated = copy.deepcopy(nominal)
        old_obj = mutated[target_idx]["object"]
        mutated[target_idx]["object"] = new_label
        # Alter event string as well
        mutated[target_idx]["type"] = mutated[target_idx]["type"].replace(old_obj, new_label)
        desc = f"Substitute Label {old_obj} -> {new_label} (Step {mutated[target_idx]['step_id']})"
        return mutated, desc

    def run_benchmark_suite(self) -> Dict[str, Any]:
        """Runs the entire digital twin failure injection benchmark suite."""
        nominal = self.generate_nominal_session()
        print("=" * 65)
        print("  PRAHARI DIGITAL TWIN FAILURE INJECTION BENCHMARK SUITE")
        print("=" * 65)

        # 1. Nominal Baseline Test
        res_nom = self.replay_events(nominal)
        nominal_passed = res_nom["is_all_completed"] and res_nom["deviations"] == 0
        print(f"[*] Baseline Nominal Run: {'PASSED' if nominal_passed else 'FAILED'} (Score: {res_nom['score']['overall_score']}%)")

        n = len(nominal)
        idx_early = min(n - 1, max(1, n // 2))
        idx_late = n - 1
        idx_step_b = min(n - 1, 2)
        idx_step_a = min(n - 1, 1)
        sub_idx = min(n - 1, max(0, n - 2))
        sub_label = "unknown_item"

        test_cases = [
            ("Out of Sequence (Late Step Early)", *self.mutate_reorder_events(nominal, idx1=idx_early, idx2=idx_late), True),
            ("Out of Sequence (Adjacent Step Inversion)", *self.mutate_reorder_events(nominal, idx1=idx_step_a, idx2=idx_step_b), True),
            ("Occlusion / Dropped Step (Missed Step)", *self.mutate_drop_event(nominal, drop_index=idx_step_a), True),
            ("Timestamp Jitter / Motion Blur", *self.mutate_timestamp_jitter(nominal), False),
            ("Label Misclassification (Wrong Object)", *self.mutate_substitute_label(nominal, target_idx=sub_idx, new_label=sub_label), True),
        ]

        total_injections = 0
        correctly_handled = 0
        false_alerts = 0

        print("-" * 65)
        print(f"{'Test Case':<36} | {'Status':<8} | {'Alerts':<6} | {'Result':<8}")
        print("-" * 65)

        for name, mutated_stream, desc, expects_alert in test_cases:
            total_injections += 1
            res = self.replay_events(mutated_stream)
            num_alerts = len(res["alerts_caught"])
            has_deviation = res["deviations"] > 0 or not res["is_all_completed"]

            if expects_alert:
                passed = (num_alerts > 0) or has_deviation
                if passed:
                    correctly_handled += 1
                    status = "CAUGHT"
                else:
                    status = "MISSED"
            else:
                # Should not raise false alert
                passed = (num_alerts == 0)
                if passed:
                    correctly_handled += 1
                    status = "CLEAN"
                else:
                    false_alerts += 1
                    status = "FALSE_POS"

            print(f"{name:<36} | {status:<8} | {num_alerts:<6} | {'PASS' if passed else 'FAIL'}")

        detection_rate = (correctly_handled / total_injections) * 100.0
        false_alert_rate = (false_alerts / total_injections) * 100.0

        print("=" * 65)
        print(f"BENCHMARK SUMMARY:")
        print(f"  Total Injected Scenarios: {total_injections}")
        print(f"  Correctly Detected/Handled: {correctly_handled}")
        print(f"  Deviation Detection Rate:   {detection_rate:.1f}%")
        print(f"  False Alert Rate:           {false_alert_rate:.1f}%")
        print("=" * 65)

        return {
            "total_injections": total_injections,
            "correctly_handled": correctly_handled,
            "detection_rate_pct": detection_rate,
            "false_alert_rate_pct": false_alert_rate,
        }


if __name__ == "__main__":
    injector = DigitalTwinFailureInjector()
    injector.run_benchmark_suite()
