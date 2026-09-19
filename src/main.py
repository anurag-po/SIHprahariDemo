"""
Main Application Entry Point for PRAHARI HAR Space Experiment Assistant.
Wires camera capture, perception, micro-FSM tracking, predictive risk engine,
deterministic sequence validator, outcome verifier, procedure-quality scorer,
voice alerts, structured JSONL logging, local MP4 recording/UDP streaming, and PyQt6 GUI.
"""

import os
import sys
import json
import time
import argparse
import threading
from typing import Dict, Any

from capture import VideoCaptureThread
from perception import PerceptionEngine
from object_tracker import ObjectTracker
from risk_engine import RiskEngine
from scorer import ProcedureScorer
from verifier import OutcomeVerifier
from voice import VoiceAssistant
from logger import SessionLogger
from validator import ExperimentValidator
from streamer import DualStreamer

try:
    from PyQt6.QtWidgets import QApplication
    from gui import PrahariMainWindow
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False
    PrahariMainWindow = None


def parse_arguments():
    parser = argparse.ArgumentParser(description="PRAHARI Mission HAR Space Experiment Assistant")
    parser.add_argument(
        "--config",
        type=str,
        default="config/desk_objects_experiment.json",
        help="Path to experiment step sequence JSON configuration",
    )
    parser.add_argument("--camera", type=int, default=0, help="Webcam device index")
    parser.add_argument("--video-file", type=str, default=None, help="Path to offline video file for replay")
    parser.add_argument("--stream-ip", type=str, default=None, help="Target IP for low-latency UDP stream")
    parser.add_argument("--stream-port", type=int, default=5000, help="Target UDP port")
    parser.add_argument("--flip", action="store_true", help="Flip camera horizontally for mirror view")
    parser.add_argument("--no-voice", action="store_true", help="Disable text-to-speech audio output")
    parser.add_argument("--headless", action="store_true", help="Run without graphical user interface")
    return parser.parse_args()


def load_config(config_path: str) -> Dict[str, Any]:
    if not os.path.exists(config_path):
        # Check if relative to project root
        alt_path = os.path.join(os.path.dirname(__file__), "..", config_path)
        if os.path.exists(alt_path):
            config_path = alt_path
        else:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


class PrahariApplication:
    def __init__(self, args):
        self.args = args
        self.config = load_config(args.config)
        self.experiment_id = self.config.get("experiment_id", "experiment")
        self.rois = self.config.get("rois", {})
        self.steps = self.config.get("steps", [])

        # 1. Logging & Voice
        self.logger = SessionLogger(self.experiment_id)
        self.voice = VoiceAssistant(enabled=not args.no_voice)

        # 2. Quality Scorer & Outcome Verifier
        expected_dur = float(self.config.get("expected_duration_seconds", 60.0))
        self.scorer = ProcedureScorer(
            total_steps=len(self.steps), expected_duration_seconds=expected_dur
        )
        self.verifier = OutcomeVerifier(self.rois)

        # 3. Validation Macro-FSM
        self.validator = ExperimentValidator(
            experiment_config=self.config,
            voice_assistant=self.voice,
            session_logger=self.logger,
            procedure_scorer=self.scorer,
            outcome_verifier=self.verifier,
            on_status_change=self._on_validator_status_change,
        )

        # 4. Perception, Tracker & Risk Engine
        self.perception = PerceptionEngine()
        self.tracker = ObjectTracker(rois=self.rois)
        self.risk_engine = RiskEngine(rois=self.rois, risk_threshold=0.5)

        # 5. Capture & Streamer
        self.capture = VideoCaptureThread(
            source=args.camera,
            video_file=args.video_file,
            flip_horizontal=args.flip,
        )
        self.streamer = DualStreamer(
            experiment_id=self.experiment_id,
            stream_ip=args.stream_ip,
            stream_port=args.stream_port,
        )

        self.gui_window: Optional[PrahariMainWindow] = None
        self.running = False
        self.worker_thread = None

    def _on_validator_status_change(self, data: Dict[str, Any]):
        if self.gui_window:
            self.gui_window.update_status(data)
            banner = data.get("banner", "")
            self.gui_window.append_log(banner)

    def start(self):
        self.running = True
        self.capture.start()

        # Start worker pipeline thread
        self.worker_thread = threading.Thread(target=self._pipeline_loop, daemon=True)
        self.worker_thread.start()

    def _pipeline_loop(self):
        while self.running:
            t_start = time.time()
            ret, frame = self.capture.read()
            if not ret or frame is None:
                time.sleep(0.02)
                continue

            # 1. Perception (YOLO + MediaPipe)
            detected_objects, hands, hands_gloved, annotated_frame = self.perception.process_frame(frame)

            # 2. Update Hand and Object Tracker
            self.tracker.update_hands(hands, now=t_start)
            emitted_events = self.tracker.update_detections(
                detected_objects=detected_objects,
                hands_gloved=hands_gloved,
                now=t_start,
            )

            # 3. Evaluate Predictive Risk Engine (§2)
            current_expected = self.validator.get_current_expected_step()
            risk_event = self.risk_engine.evaluate(
                hand_trajectories=self.tracker.hand_trajectories,
                current_step=current_expected,
                now=t_start,
            )
            if risk_event:
                emitted_events.append(risk_event)

            # 4. Process discrete events through Deterministic Validator FSM (§3, §5)
            for ev in emitted_events:
                self.validator.process_event(ev, current_frame=frame, now=t_start)

            # 5. Record / Stream frame
            self.streamer.write_frame(annotated_frame)

            # 6. Push to GUI
            if self.gui_window:
                self.gui_window.update_frame(annotated_frame, self.tracker.hand_trajectories)

            # Maintain ~30 FPS loop rate
            elapsed = time.time() - t_start
            time.sleep(max(0.005, (1.0 / 30.0) - elapsed))

    def stop(self):
        print("\n[PRAHARI] Initiating graceful shutdown...")
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

        self.capture.stop()
        self.streamer.close()
        self.voice.stop()

        # Compute and write final procedure quality score summary
        score_breakdown = self.scorer.compute_score()
        overall_status = "PASS" if len(self.validator.completed_step_ids) == len(self.steps) else "INCOMPLETE"
        summary = self.logger.end_session(
            total_steps=len(self.steps),
            completed_ok_count=len(self.validator.completed_step_ids),
            deviation_count=self.scorer.deviation_count,
            warning_count=self.scorer.predictive_warning_count,
            procedure_score_data=score_breakdown,
            overall_status=overall_status,
        )
        print(f"[PRAHARI] Final Procedure Quality Score: {score_breakdown['overall_score']}%")
        print(f"[PRAHARI] Session Log: {self.logger.log_filepath}")


def main():
    args = parse_arguments()

    if args.headless or not HAS_PYQT:
        app_engine = PrahariApplication(args)
        app_engine.start()
        if not HAS_PYQT and not args.headless:
            print("[PRAHARI] PyQt6 not installed. Running in console headless mode.")
        print("[PRAHARI] Running in headless mode. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            app_engine.stop()
    else:
        qt_app = QApplication(sys.argv)
        app_engine = PrahariApplication(args)
        gui_window = PrahariMainWindow(
            experiment_config=app_engine.config,
            video_capture=app_engine.capture,
            validator=app_engine.validator,
            risk_engine=app_engine.risk_engine,
            scorer=app_engine.scorer,
            verifier=app_engine.verifier,
            initial_flip=args.flip,
        )
        app_engine.gui_window = gui_window
        gui_window.show()
        app_engine.start()

        try:
            sys.exit(qt_app.exec())
        finally:
            app_engine.stop()


if __name__ == "__main__":
    main()
