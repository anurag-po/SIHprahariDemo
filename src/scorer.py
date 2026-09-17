"""
Procedure-Quality Scoring Engine for PRAHARI HAR Space Experiment Assistant.
Evaluates human operator execution quality in real-time and post-session.

Formulas:
  accuracy    = completed_ok_steps / total_steps
  speed       = clamp(expected_total_time / max(actual_total_time, 1), 0.0, 1.0)
  cleanliness = max(0.0, 1.0 - (deviation_count + 0.5 * predictive_warning_count) / total_steps)
  total_score = w_acc * accuracy + w_speed * speed + w_clean * cleanliness
"""

import time
from typing import Dict, List, Any, Optional


class ProcedureScorer:
    def __init__(
        self,
        total_steps: int,
        expected_duration_seconds: float = 60.0,
        weight_accuracy: float = 0.5,
        weight_speed: float = 0.2,
        weight_cleanliness: float = 0.3,
    ):
        self.total_steps = max(1, total_steps)
        self.expected_duration = max(1.0, expected_duration_seconds)
        self.w_acc = weight_accuracy
        self.w_speed = weight_speed
        self.w_clean = weight_cleanliness

        self.start_time = time.time()
        self.completed_ok_steps = set()
        self.deviation_count = 0
        self.predictive_warning_count = 0
        self.unverifiable_count = 0
        self.step_timestamps: List[Dict[str, Any]] = []

    def on_step_ok(self, step_id: int, timestamp: Optional[float] = None):
        t = timestamp or time.time()
        self.completed_ok_steps.add(step_id)
        self.step_timestamps.append({
            "step_id": step_id,
            "status": "OK",
            "time": t,
        })

    def on_deviation(self, step_id: Optional[int] = None, timestamp: Optional[float] = None):
        self.deviation_count += 1
        t = timestamp or time.time()
        self.step_timestamps.append({
            "step_id": step_id,
            "status": "OUT_OF_SEQUENCE",
            "time": t,
        })

    def on_predictive_warning(self, step_id: Optional[int] = None, timestamp: Optional[float] = None):
        self.predictive_warning_count += 1

    def on_unverifiable(self):
        self.unverifiable_count += 1

    def compute_score(self, current_time: Optional[float] = None) -> Dict[str, Any]:
        """Calculates live or post-session quality metrics."""
        now = current_time or time.time()
        actual_time = max(1.0, now - self.start_time)

        # 1. Accuracy
        accuracy = len(self.completed_ok_steps) / float(self.total_steps)

        # 2. Speed (clamped between 0.0 and 1.0)
        speed = min(1.0, max(0.0, self.expected_duration / actual_time))

        # 3. Cleanliness (penalizes deviations and near-miss warnings)
        penalty = (self.deviation_count + 0.5 * self.predictive_warning_count) / float(self.total_steps)
        cleanliness = max(0.0, 1.0 - penalty)

        # Composite score
        composite = (self.w_acc * accuracy) + (self.w_speed * speed) + (self.w_clean * cleanliness)
        normalized_score = round(min(1.0, max(0.0, composite)) * 100.0, 1)

        return {
            "overall_score": normalized_score,  # 0 to 100
            "accuracy": round(accuracy * 100.0, 1),
            "speed_factor": round(speed, 2),
            "cleanliness": round(cleanliness * 100.0, 1),
            "completed_steps": len(self.completed_ok_steps),
            "total_steps": self.total_steps,
            "deviations": self.deviation_count,
            "predictive_warnings": self.predictive_warning_count,
            "unverifiable_events": self.unverifiable_count,
            "elapsed_seconds": round(actual_time, 1),
        }
