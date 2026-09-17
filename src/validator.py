"""
Deterministic Sequence Validation FSM for PRAHARI HAR Space Experiment Assistant.
Features:
- Event-driven deterministic macro-FSM
- Explainable structured alert payloads
- 3-tier Confidence-gated degradation (High > 0.8, Medium 0.5-0.8, Low < 0.5 UNVERIFIABLE)
- Advisory Predicted Deviation handling (never corrupts step sequence)
- Multi-modal outcome verification integration
"""

import time
from typing import Dict, List, Set, Optional, Any, Callable
import numpy as np


class ExperimentValidator:
    def __init__(
        self,
        experiment_config: Dict[str, Any],
        voice_assistant: Optional[Any] = None,
        session_logger: Optional[Any] = None,
        procedure_scorer: Optional[Any] = None,
        outcome_verifier: Optional[Any] = None,
        on_status_change: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.config = experiment_config
        self.experiment_id = experiment_config.get("experiment_id", "experiment")
        self.display_name = experiment_config.get("display_name", "Experiment")
        self.steps = experiment_config.get("steps", [])
        self.steps_by_id = {s["id"]: s for s in self.steps}

        self.voice = voice_assistant
        self.logger = session_logger
        self.scorer = procedure_scorer
        self.verifier = outcome_verifier
        self.on_status_change = on_status_change

        self.completed_step_ids: Set[int] = set()
        self.step_outcomes: Dict[int, str] = {}  # step_id -> "OK", "PASS", "FAIL", "OUT_OF_SEQUENCE"
        self.pending_confirmations: Dict[str, int] = {}  # event_key -> hold_count for medium confidence
        self.last_alert_payload: Optional[Dict[str, Any]] = None
        self.current_status_banner = "Ready. Awaiting step 1."
        self.is_completed = False

        # Initial prompt announcement
        self._announce_initial()

    def _announce_initial(self):
        first_steps = self.get_expected_next_steps()
        if first_steps and self.voice:
            first_step = self.steps_by_id[first_steps[0]]
            self.voice.say_guidance(first_step.get("voice_prompt", f"Begin with {first_step['name']}."))

    def get_expected_next_steps(self) -> List[int]:
        """Returns list of step IDs whose dependencies are fully satisfied but not yet completed."""
        available = []
        for step in self.steps:
            s_id = step["id"]
            if s_id in self.completed_step_ids:
                continue
            deps = step.get("depends_on", [])
            if all(d in self.completed_step_ids for d in deps):
                available.append(s_id)
        return available

    def get_current_expected_step(self) -> Optional[Dict[str, Any]]:
        """Returns the primary next expected step dict."""
        nxt = self.get_expected_next_steps()
        if nxt:
            return self.steps_by_id[min(nxt)]
        return None

    def _match_event_to_step(self, event_type: str) -> Optional[Dict[str, Any]]:
        """Finds step definition matching the emitted event string."""
        for step in self.steps:
            target_event = step.get("event")
            if not target_event:
                continue
            allowed_events = [e.strip() for e in target_event.split("|")] if "|" in target_event else [target_event]
            for allowed in allowed_events:
                if event_type == allowed or (allowed.startswith("dwell") and event_type.startswith("dwell")):
                    return step
        return None

    def handle_predicted_deviation(self, event_data: Dict[str, Any]):
        """
        Advisory warning handler for RiskEngine predictions.
        Does NOT alter step states or corrupt deterministic sequence log.
        """
        step_id = event_data.get("step_id")
        step_name = event_data.get("step_name", "")
        target_roi = event_data.get("predicted_wrong_target", "")
        risk_score = event_data.get("risk_score", 0.5)
        alert_payload = event_data.get("alert_payload", {})

        # 1. Voice warning (rate-limited)
        if self.voice:
            self.voice.say_predictive_warning(target_roi, step_name, f"pred_{step_id}_{target_roi}")

        # 2. Structured Log
        if self.logger:
            self.logger.log_event("predicted_deviation", event_data)

        # 3. Scorer update
        if self.scorer:
            self.scorer.on_predictive_warning(step_id)

        # 4. GUI notification
        self.last_alert_payload = alert_payload
        self.current_status_banner = f"PREDICTIVE CAUTION: Heading toward {target_roi} (Risk {risk_score:.2f})"
        if self.on_status_change:
            self.on_status_change({
                "type": "predictive_warning",
                "risk_score": risk_score,
                "banner": self.current_status_banner,
                "alert_payload": alert_payload,
                "expected_next": self.get_expected_next_steps(),
            })

    def process_event(
        self,
        event: Dict[str, Any],
        current_frame: Optional[np.ndarray] = None,
        now: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Main entry point for discrete events emitted by perception / tracker.
        Applies 3-tier confidence gating before state machine execution.
        """
        now = now or time.time()
        event_type = event.get("type", "")
        confidence = float(event.get("confidence", 0.9))

        # Handle advisory predicted_deviation separately
        if event_type == "predicted_deviation":
            self.handle_predicted_deviation(event)
            return None

        matched_step = self._match_event_to_step(event_type)
        if not matched_step:
            return None  # Irrelevant or background event

        step_id = matched_step["id"]
        step_name = matched_step["name"]

        # If already completed, ignore duplicate
        if step_id in self.completed_step_ids:
            return None

        # --- FEATURE 3: Confidence-Gated Degradation ---
        if confidence < 0.5:
            # Low confidence: Do not guess. Record UNVERIFIABLE.
            if self.logger:
                self.logger.log_unverifiable(
                    event_name=event_type,
                    confidence=confidence,
                    reason="Perception confidence below 0.5 threshold",
                )
            if self.scorer:
                self.scorer.on_unverifiable()
            return {"status": "UNVERIFIABLE", "confidence": confidence, "step_id": step_id}

        elif 0.5 <= confidence < 0.8:
            # Medium confidence: hold 1 extra cycle for confirmation
            hold_count = self.pending_confirmations.get(event_type, 0) + 1
            self.pending_confirmations[event_type] = hold_count
            if hold_count < 2:
                # Hold for next frame confirmation
                return {"status": "CONFIRMING", "confidence": confidence, "step_id": step_id}
            # Confirmed over 2 frames, proceed
            self.pending_confirmations.pop(event_type, None)

        else:
            # High confidence (>0.8): Auto-accept
            self.pending_confirmations.pop(event_type, None)

        # --- Deterministic Dependency Check ---
        deps = matched_step.get("depends_on", [])
        missing_deps = [d for d in deps if d not in self.completed_step_ids]

        if not missing_deps:
            # IN-ORDER STEP EXECUTION
            self.completed_step_ids.add(step_id)
            final_status = "OK"
            detail = "Step completed in valid sequence"

            # Check outcome verification if defined (§5)
            if self.verifier and matched_step.get("verification"):
                ver_pass, ver_msg, ver_metrics = self.verifier.verify_step_outcome(
                    matched_step, current_frame
                )
                final_status = "PASS" if ver_pass else "FAIL"
                detail = ver_msg

            self.step_outcomes[step_id] = final_status

            if self.logger:
                self.logger.log_step(
                    step_id=step_id,
                    step_name=step_name,
                    status=final_status,
                    detail=detail,
                    confidence=confidence,
                    verification_mode=matched_step.get("verification", {}).get("mode", "vision_only"),
                )

            if self.scorer:
                self.scorer.on_step_ok(step_id, timestamp=now)

            # Announce next step guidance or completion
            nxt = self.get_expected_next_steps()
            if nxt:
                next_step = self.steps_by_id[min(nxt)]
                self.current_status_banner = f"Current: Step {step_id} completed ({final_status}). Next: Step {next_step['id']} - {next_step['name']}"
                if self.voice:
                    self.voice.say_guidance(next_step.get("voice_prompt", f"Proceed to {next_step['name']}."))
            else:
                self.is_completed = True
                self.current_status_banner = "Experiment sequence complete. All steps verified."
                if self.voice:
                    self.voice.say_guidance("Experiment sequence complete. Well done.")

            res = {
                "step_id": step_id,
                "step_name": step_name,
                "status": final_status,
                "detail": detail,
                "confidence": confidence,
            }

            if self.on_status_change:
                self.on_status_change({
                    "type": "step_completed",
                    "step_id": step_id,
                    "status": final_status,
                    "banner": self.current_status_banner,
                    "expected_next": self.get_expected_next_steps(),
                    "completed": list(self.completed_step_ids),
                })
            return res

        else:
            # OUT-OF-SEQUENCE / VIOLATION
            expected_step_ids = self.get_expected_next_steps()
            expected_names = [self.steps_by_id[eid]["name"] for eid in expected_step_ids]
            missing_names = [self.steps_by_id[mid]["name"] for mid in missing_deps]

            # Build explainable alert payload (§3)
            alert_payload = {
                "expected": f"Complete prerequisite step(s): {', '.join(missing_names)} (IDs: {missing_deps})",
                "detected": f"{step_name} (Step {step_id}) triggered prematurely",
                "confidence": round(confidence, 2),
                "critical": bool(matched_step.get("severity", 0.5) >= 0.7 or matched_step.get("irreversible", False)),
                "recommended_action": f"Stop action immediately. Return object and complete {', '.join(expected_names)} first.",
                "can_continue": False,
            }

            self.last_alert_payload = alert_payload
            self.current_status_banner = f"ALERT: Step {step_id} ({step_name}) out of sequence! Missing: {missing_deps}"

            if self.logger:
                self.logger.log_step(
                    step_id=step_id,
                    step_name=step_name,
                    status="OUT_OF_SEQUENCE",
                    detail=f"Missing prerequisites: {missing_deps}",
                    confidence=confidence,
                    alert_payload=alert_payload,
                )

            if self.voice:
                self.voice.say_alert(alert_payload)

            if self.scorer:
                self.scorer.on_deviation(step_id, timestamp=now)

            if self.on_status_change:
                self.on_status_change({
                    "type": "alert",
                    "status": "OUT_OF_SEQUENCE",
                    "step_id": step_id,
                    "banner": self.current_status_banner,
                    "alert_payload": alert_payload,
                    "expected_next": self.get_expected_next_steps(),
                })

            return {
                "step_id": step_id,
                "step_name": step_name,
                "status": "OUT_OF_SEQUENCE",
                "detail": f"Missing prerequisites: {missing_deps}",
                "confidence": confidence,
                "alert_payload": alert_payload,
            }
