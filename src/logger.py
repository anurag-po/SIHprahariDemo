"""
Structured session and audit logger for PRAHARI HAR Space Experiment Assistant.
Outputs JSON Lines (.jsonl) with explainable alert payloads, confidence metrics,
and procedure quality scores.
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional


class SessionLogger:
    def __init__(self, experiment_id: str, logs_dir: str = "logs"):
        self.experiment_id = experiment_id
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        
        self.session_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.log_filepath = os.path.join(
            self.logs_dir, f"{self.experiment_id}_{self.session_timestamp}.jsonl"
        )
        self.start_time = time.time()
        self.entries = []

    def _get_iso_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def log_step(
        self,
        step_id: int,
        step_name: str,
        status: str,
        detail: Optional[str] = None,
        confidence: Optional[float] = None,
        alert_payload: Optional[Dict[str, Any]] = None,
        verification_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record a step event entry.
        Status types: OK, OUT_OF_SEQUENCE, UNVERIFIABLE, PASS, FAIL, PREDICTED_DEVIATION
        """
        entry = {
            "timestamp": self._get_iso_timestamp(),
            "step_id": step_id,
            "step_name": step_name,
            "status": status,
        }
        if detail is not None:
            entry["detail"] = detail
        if confidence is not None:
            entry["confidence"] = round(confidence, 3)
        if alert_payload is not None:
            entry["alert"] = alert_payload
        if verification_mode is not None:
            entry["verification_mode"] = verification_mode

        self._write_entry(entry)
        return entry

    def log_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Log generic raw or advisory events (e.g. predicted_deviation, sensor triggers)."""
        entry = {
            "timestamp": self._get_iso_timestamp(),
            "event_type": event_type,
            **data,
        }
        self._write_entry(entry)
        return entry

    def log_unverifiable(self, event_name: str, confidence: float, reason: str = "Low confidence detection"):
        """Log when an event is discarded / held due to confidence-gated degradation."""
        entry = {
            "timestamp": self._get_iso_timestamp(),
            "status": "UNVERIFIABLE",
            "event": event_name,
            "confidence": round(confidence, 3),
            "reason": reason,
        }
        self._write_entry(entry)
        return entry

    def end_session(
        self,
        total_steps: int,
        completed_ok_count: int,
        deviation_count: int,
        warning_count: int,
        procedure_score_data: Optional[Dict[str, Any]] = None,
        overall_status: str = "PASS",
    ) -> Dict[str, Any]:
        """Emit a one-line session summary at session conclusion."""
        duration = round(time.time() - self.start_time, 2)
        summary = {
            "session_summary": True,
            "timestamp": self._get_iso_timestamp(),
            "experiment_id": self.experiment_id,
            "duration_seconds": duration,
            "total_steps_expected": total_steps,
            "steps_completed_ok": completed_ok_count,
            "deviations_count": deviation_count,
            "predictive_warnings_count": warning_count,
            "overall_status": overall_status,
            "procedure_score": procedure_score_data or {},
        }
        self._write_entry(summary)
        return summary

    def _write_entry(self, entry: Dict[str, Any]):
        self.entries.append(entry)
        try:
            with open(self.log_filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[SessionLogger] Error writing to {self.log_filepath}: {e}")
