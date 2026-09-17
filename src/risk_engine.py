"""
Predictive Error Prevention & Risk Engine for PRAHARI HAR Space Experiment Assistant.
Uses linear trajectory extrapolation on rolling hand/object motion vectors to forecast
intended ROI targets before physical contact occurs.

Computes Risk Score R = P(wrong_target) * severity * (1.5 if irreversible else 1.0).
Emits explainable 'predicted_deviation' advisory events onto the system event stream.
"""

import math
import time
from typing import Dict, List, Tuple, Optional, Any


class RiskEngine:
    def __init__(
        self,
        rois: Dict[str, List[int]],
        risk_threshold: float = 0.5,
        extrapolation_horizon_seconds: float = 0.75,
        min_velocity_threshold: float = 25.0,  # pixels / sec
    ):
        """
        rois: Dict mapping roi_name -> [x1, y1, x2, y2]
        risk_threshold: threshold (0.0 to 1.0) above which predicted_deviation is triggered
        extrapolation_horizon_seconds: lookahead window into future
        """
        self.rois = rois
        self.risk_threshold = risk_threshold
        self.extrapolation_horizon = extrapolation_horizon_seconds
        self.min_velocity_threshold = min_velocity_threshold

        self.last_emitted_warning_step: Optional[int] = None
        self.last_emitted_target: Optional[str] = None
        self.last_warning_time: float = 0.0
        self.warning_cooldown: float = 3.0  # seconds cooldown between identical warnings

    def _roi_center(self, roi_box: List[int]) -> Tuple[float, float]:
        return ((roi_box[0] + roi_box[2]) / 2.0, (roi_box[1] + roi_box[3]) / 2.0)

    def _point_in_box(self, pt: Tuple[float, float], box: List[int]) -> bool:
        x, y = pt
        return box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def _calculate_velocity(
        self, trajectory: List[Tuple[float, float, float]]
    ) -> Tuple[float, float, float]:
        """
        Calculates average velocity vector (vx, vy, speed) from rolling trajectory.
        trajectory: [(x, y, timestamp), ...]
        """
        if len(trajectory) < 2:
            return (0.0, 0.0, 0.0)

        # Use first and last samples in buffer
        p_start = trajectory[0]
        p_end = trajectory[-1]
        dt = p_end[2] - p_start[2]

        if dt <= 0.001:
            # Fallback if timestamps identical (e.g. frame count based, assume 30fps)
            dt = len(trajectory) / 30.0

        dx = p_end[0] - p_start[0]
        dy = p_end[1] - p_start[1]
        vx = dx / dt
        vy = dy / dt
        speed = math.hypot(vx, vy)
        return (vx, vy, speed)

    def _calculate_approach_probability(
        self,
        curr_pos: Tuple[float, float],
        velocity: Tuple[float, float, float],
        target_roi_name: str,
    ) -> float:
        """
        Calculates P(target) based on angle alignment between velocity vector
        and target center vector, and distance to target.
        """
        if target_roi_name not in self.rois:
            return 0.0

        roi_box = self.rois[target_roi_name]
        target_center = self._roi_center(roi_box)
        vx, vy, speed = velocity

        if speed < self.min_velocity_threshold:
            return 0.0

        # Vector from current pos to target center
        to_target_x = target_center[0] - curr_pos[0]
        to_target_y = target_center[1] - curr_pos[1]
        dist_to_target = math.hypot(to_target_x, to_target_y)

        if dist_to_target < 1.0:
            return 1.0

        # Dot product for cosine similarity
        dot = (vx * to_target_x) + (vy * to_target_y)
        cos_theta = dot / (speed * dist_to_target)

        # Extrapolated position in lookahead horizon
        future_x = curr_pos[0] + (vx * self.extrapolation_horizon)
        future_y = curr_pos[1] + (vy * self.extrapolation_horizon)
        future_pos = (future_x, future_y)

        # Check if projected endpoint falls inside target ROI
        if self._point_in_box(future_pos, roi_box):
            projected_hit = 1.0
        else:
            # Distance from projected point to target center compared to current distance
            future_dist = math.hypot(target_center[0] - future_x, target_center[1] - future_y)
            projected_hit = max(0.0, 1.0 - (future_dist / max(dist_to_target, 100.0)))

        # Alignment confidence: clamp cos_theta to [0, 1]
        alignment = max(0.0, cos_theta)
        p_target = (0.5 * alignment) + (0.5 * projected_hit)
        return min(1.0, max(0.0, p_target))

    def evaluate(
        self,
        hand_trajectories: Dict[str, List[Tuple[float, float, float]]],
        current_step: Optional[Dict[str, Any]],
        now: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluate predictive risk for the current expected step.
        Returns a predicted_deviation event dictionary if risk >= threshold, else None.
        """
        if not current_step:
            return None

        now = now or time.time()
        step_id = current_step.get("id")
        step_name = current_step.get("name", f"step_{step_id}")
        expected_targets = current_step.get("expected_targets", [])
        confusable_targets = current_step.get("confusable_targets", [])
        severity = float(current_step.get("severity", 0.5))
        irreversible = bool(current_step.get("irreversible", False))

        if not confusable_targets:
            return None

        # Check each active hand trajectory
        for hand_id, traj in hand_trajectories.items():
            if len(traj) < 3:
                continue

            curr_pos = (traj[-1][0], traj[-1][1])
            vx, vy, speed = self._calculate_velocity(traj)

            if speed < self.min_velocity_threshold:
                continue

            # Compute P(wrong_target) for each confusable target
            for conf_target in confusable_targets:
                if conf_target not in self.rois:
                    continue

                # Don't flag if hand is already inside that ROI
                if self._point_in_box(curr_pos, self.rois[conf_target]):
                    continue

                p_wrong = self._calculate_approach_probability(curr_pos, (vx, vy, speed), conf_target)

                # If there are expected targets, compare relative probability
                p_expected_max = 0.0
                for exp_target in expected_targets:
                    p_exp = self._calculate_approach_probability(curr_pos, (vx, vy, speed), exp_target)
                    p_expected_max = max(p_expected_max, p_exp)

                # Weight wrong target probability higher if clearly heading away from expected target
                relative_p_wrong = max(0.0, p_wrong - (0.5 * p_expected_max)) if p_expected_max > 0 else p_wrong

                # Compute Risk Score: R = P(wrong_target) * severity * (1.5 if irreversible else 1.0)
                multiplier = 1.5 if irreversible else 1.0
                risk_score = round(min(1.0, relative_p_wrong * severity * multiplier), 3)

                if risk_score >= self.risk_threshold:
                    # Check rate limiting / debounce
                    if (
                        self.last_emitted_warning_step == step_id
                        and self.last_emitted_target == conf_target
                        and (now - self.last_warning_time) < self.warning_cooldown
                    ):
                        return None  # Rate-limited

                    self.last_emitted_warning_step = step_id
                    self.last_emitted_target = conf_target
                    self.last_warning_time = now

                    expected_str = ", ".join(expected_targets) if expected_targets else "designated area"
                    alert_payload = {
                        "expected": f"Move towards {expected_str}",
                        "detected": f"Trajectory heading toward wrong ROI: {conf_target}",
                        "confidence": round(relative_p_wrong, 2),
                        "critical": risk_score >= 0.7 or irreversible,
                        "recommended_action": f"Pause movement. Reroute toward {expected_str}.",
                        "can_continue": True,
                    }

                    return {
                        "type": "predicted_deviation",
                        "step_id": step_id,
                        "step_name": step_name,
                        "predicted_wrong_target": conf_target,
                        "expected_targets": expected_targets,
                        "risk_score": risk_score,
                        "confidence": round(relative_p_wrong, 3),
                        "severity": severity,
                        "irreversible": irreversible,
                        "alert_payload": alert_payload,
                        "timestamp": now,
                    }

        return None

    def reset_cooldown(self):
        self.last_emitted_warning_step = None
        self.last_emitted_target = None
        self.last_warning_time = 0.0
