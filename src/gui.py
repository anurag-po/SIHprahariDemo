"""
Single-Window PyQt6 Desktop GUI for PRAHARI HAR Space Experiment Assistant.
Features:
- Live video feed with CV overlays, ROI bounds, and predictive trajectory vectors
- Camera Lateral Flip (Mirror View) toggle control
- Full Experiment Protocol Step Sequence roadmap with live progress badges
- Explainable Alert and Predictive Warning banner card
- Live Procedure-Quality Scoring widget (accuracy, speed, cleanliness breakdown)
- Live scrolling structured JSONL-mirroring audit log
- Mock Telemetry Sensor override switch for demo verification
"""

import os
import sys
import json
import time
import threading
import queue
from typing import Dict, Any, Optional, List
import cv2
import numpy as np

try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QImage, QPixmap, QFont
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QTextEdit, QProgressBar, QGroupBox, QCheckBox, QPushButton, QLineEdit, QComboBox
    )
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False


class PrahariMainWindow(QMainWindow if HAS_PYQT else object):
    def __init__(
        self,
        experiment_config: Dict[str, Any],
        video_capture=None,
        validator=None,
        risk_engine=None,
        scorer=None,
        verifier=None,
        initial_flip: bool = False,
    ):
        if not HAS_PYQT:
            return

        super().__init__()
        self.config = experiment_config
        self.cap = video_capture
        self.validator = validator
        self.risk_engine = risk_engine
        self.scorer = scorer
        self.verifier = verifier

        self.rois = experiment_config.get("rois", {})
        self.steps = experiment_config.get("steps", [])
        self.display_name = experiment_config.get("display_name", "PRAHARI Experiment")

        # Thread-safe buffers
        self.frame_lock = threading.Lock()
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_trajectories: Optional[Dict[str, Any]] = None
        self.status_queue = queue.Queue()
        self.log_queue = queue.Queue()

        self.initial_flip = initial_flip
        self.step_labels: Dict[int, QLabel] = {}

        self.setWindowTitle(f"PRAHARI — Mission HAR Assistant [{self.display_name}]")
        self.setMinimumSize(1280, 800)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #000000;
                color: #e6e6e6;
            }
            QGroupBox {
                background-color: #0c0c0c;
                border: 1px solid #222222;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #f0f0f0;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: #cccccc;
            }
            QTextEdit {
                background-color: #050505;
                border: 1px solid #222222;
                border-radius: 4px;
                color: #00e676;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
            QProgressBar {
                border: 1px solid #222222;
                border-radius: 4px;
                text-align: center;
                background-color: #141414;
                color: #ffffff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #ff9800;
                border-radius: 3px;
            }
            QCheckBox {
                color: #e6e6e6;
                font-size: 12px;
                font-weight: 500;
            }
        """)

        self._build_ui()
        self._init_timer()
        self._refresh_steps_display()

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ================= LEFT PANEL: LIVE VIDEO & CONTROLS =================
        left_box = QGroupBox("LIVE SENSOR & EXPERIMENT STREAM")
        left_layout = QVBoxLayout(left_box)

        self.video_label = QLabel("Initializing Video Feed...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("background-color: #000000; border: 1px solid #222222; border-radius: 4px;")
        left_layout.addWidget(self.video_label, stretch=4)

        # Connect IP Camera Section
        ip_cam_box = QGroupBox("CONNECT IP CAM / VIDEO SOURCE")
        ip_cam_box.setStyleSheet("""
            QGroupBox {
                background-color: #050505;
                border: 1px solid #1f1f1f;
                border-radius: 5px;
                margin-top: 4px;
                padding-top: 10px;
                color: #e0e0e0;
                font-size: 11px;
            }
        """)
        ip_cam_layout = QHBoxLayout(ip_cam_box)
        ip_cam_layout.setContentsMargins(8, 4, 8, 6)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("IP cam URL (e.g. http://192.168.1.50:8080/video or rtsp://...) or webcam index (0, 1)")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                background-color: #121212;
                border: 1px solid #333333;
                border-radius: 4px;
                color: #ffffff;
                padding: 5px 8px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #ff9800;
            }
        """)
        self.ip_input.returnPressed.connect(self._on_connect_ip_cam)
        ip_cam_layout.addWidget(self.ip_input, stretch=3)

        self.btn_connect_ip = QPushButton("🔗 Connect IP Cam")
        self.btn_connect_ip.setStyleSheet("""
            QPushButton {
                background-color: #212121;
                color: #ff9800;
                border: 1px solid #ff9800;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #ff9800;
                color: #000000;
            }
        """)
        self.btn_connect_ip.clicked.connect(self._on_connect_ip_cam)
        ip_cam_layout.addWidget(self.btn_connect_ip)

        self.ip_status_lbl = QLabel("Source: Camera 0")
        self.ip_status_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        ip_cam_layout.addWidget(self.ip_status_lbl)

        left_layout.addWidget(ip_cam_box)

        # Stream Controls Row (Flip Camera, Rotate, Advance Button, Recite Steps, Protocol Info)
        controls_layout = QHBoxLayout()
        self.flip_checkbox = QCheckBox("Flip Camera (Mirror)")
        self.flip_checkbox.setChecked(self.initial_flip)
        self.flip_checkbox.stateChanged.connect(self._on_flip_toggle)
        controls_layout.addWidget(self.flip_checkbox)

        # Rotation Selector
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(["Rotate: 0°", "Rotate: 90°", "Rotate: 180°", "Rotate: 270°"])
        self.rotation_combo.setStyleSheet("""
            QComboBox {
                background-color: #1a1a1a;
                color: #e6e6e6;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QComboBox:hover {
                border: 1px solid #00e676;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: #e6e6e6;
                selection-background-color: #00e676;
                selection-color: #000000;
            }
        """)
        self.rotation_combo.currentIndexChanged.connect(self._on_rotation_changed)
        controls_layout.addWidget(self.rotation_combo)

        self.btn_recite = QPushButton("🔊 Recite Step")
        self.btn_recite.setStyleSheet("""
            QPushButton {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 1px solid #333333;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
                border: 1px solid #ff9800;
            }
        """)
        self.btn_recite.clicked.connect(self._on_recite_clicked)
        controls_layout.addWidget(self.btn_recite)

        self.btn_advance = QPushButton("⏭ Advance Step (Space)")
        self.btn_advance.setStyleSheet("""
            QPushButton {
                background-color: #1b5e20;
                color: #ffffff;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
                border: 1px solid #2e7d32;
            }
            QPushButton:hover {
                background-color: #2e7d32;
            }
        """)
        self.btn_advance.clicked.connect(self.trigger_next_step)
        controls_layout.addWidget(self.btn_advance)

        controls_layout.addStretch()

        stream_info = QLabel(f"Protocol: {self.display_name}")
        stream_info.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        controls_layout.addWidget(stream_info)
        left_layout.addLayout(controls_layout)

        main_layout.addWidget(left_box, stretch=3)

        # ================= RIGHT PANEL: STATUS, STEPS, SCORE, LOG =================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # --- 1. Current Step & Explainable Alert Banner ---
        self.status_box = QGroupBox("MISSION HAR STATUS & SAFETY BANNER")
        status_layout = QVBoxLayout(self.status_box)

        self.status_banner = QLabel("SYSTEM READY — AWAITING STEP 1")
        self.status_banner.setWordWrap(True)
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_banner.setStyleSheet("""
            background-color: #161616;
            border: 1px solid #333333;
            color: #ffffff;
            font-size: 13px;
            font-weight: bold;
            padding: 8px;
            border-radius: 5px;
        """)
        status_layout.addWidget(self.status_banner)

        # Explainable Detail Label
        self.alert_detail_label = QLabel("No active deviations. Sequence nominal.")
        self.alert_detail_label.setWordWrap(True)
        self.alert_detail_label.setStyleSheet("color: #888888; font-size: 11px; padding: 2px;")
        status_layout.addWidget(self.alert_detail_label)

        right_layout.addWidget(self.status_box)

        # --- 2. Protocol Steps Checklist / Roadmap Panel ---
        self.steps_box = QGroupBox("EXPERIMENT PROTOCOL STEPS")
        self.steps_layout = QVBoxLayout(self.steps_box)
        self.steps_layout.setSpacing(4)
        self.steps_layout.setContentsMargins(10, 12, 10, 8)

        for step in self.steps:
            s_id = step["id"]
            s_name = step["name"].replace("_", " ").title()
            exp_targets = step.get("expected_targets", [])
            target_str = f" [ROI: {', '.join(exp_targets)}]" if exp_targets else ""

            lbl = QLabel(f"○ Step {s_id}: {s_name}{target_str}")
            lbl.setStyleSheet("color: #777777; font-size: 11px; padding: 2px;")
            self.step_labels[s_id] = lbl
            self.steps_layout.addWidget(lbl)

        right_layout.addWidget(self.steps_box)

        # --- 3. Procedure-Quality Score Panel ---
        score_box = QGroupBox("PROCEDURE-QUALITY SCORE METER")
        score_layout = QVBoxLayout(score_box)

        score_header = QHBoxLayout()
        self.score_label = QLabel("LIVE QUALITY SCORE: 100.0%")
        self.score_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        score_header.addWidget(self.score_label)
        score_layout.addLayout(score_header)

        self.score_bar = QProgressBar()
        self.score_bar.setValue(100)
        self.score_bar.setFixedHeight(16)
        score_layout.addWidget(self.score_bar)

        self.metrics_label = QLabel("Accuracy: 100% | Speed: 1.00 | Cleanliness: 100% | Deviations: 0 | Near-Misses: 0")
        self.metrics_label.setStyleSheet("color: #888888; font-size: 11px;")
        score_layout.addWidget(self.metrics_label)

        # Mock Sensor Telemetry Checkbox (§5 demo trigger)
        mock_layout = QHBoxLayout()
        self.mock_sensor_cb = QCheckBox("Instrument Telemetry Signal (Mock Sensor PASS)")
        self.mock_sensor_cb.setChecked(True)
        self.mock_sensor_cb.stateChanged.connect(self._on_mock_sensor_toggle)
        mock_layout.addWidget(self.mock_sensor_cb)
        score_layout.addLayout(mock_layout)

        right_layout.addWidget(score_box)

        # --- 4. Structured Audit Log ---
        log_box = QGroupBox("STRUCTURED AUDIT LOG (JSONL STREAM)")
        log_layout = QVBoxLayout(log_box)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        right_layout.addWidget(log_box, stretch=2)
        main_layout.addWidget(right_widget, stretch=2)

    def _init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_loop)
        self.timer.start(30)  # ~30 FPS on main GUI thread

    def _on_connect_ip_cam(self):
        url_text = self.ip_input.text().strip()
        if not url_text:
            return
        if url_text.isdigit():
            source = int(url_text)
        else:
            source = url_text

        self.ip_status_lbl.setText("Connecting...")
        self.ip_status_lbl.setStyleSheet("color: #ff9800; font-size: 11px;")
        QApplication.processEvents()

        if self.cap and self.cap.switch_source(source):
            src_display = str(source)
            if len(src_display) > 28:
                src_display = src_display[:25] + "..."
            self.ip_status_lbl.setText(f"Connected: {src_display}")
            self.ip_status_lbl.setStyleSheet("color: #00e676; font-size: 11px; font-weight: bold;")
            self.append_log(f"VIDEO: Connected to source: {source} (IP Cam active)")
        else:
            self.ip_status_lbl.setText("Connection failed")
            self.ip_status_lbl.setStyleSheet("color: #f44336; font-size: 11px;")
            self.append_log(f"VIDEO: Failed to connect to {source}. Ensure device is on same Wi-Fi and stream URL is active (e.g. http://<ip>:8080/video)")

    def _on_recite_clicked(self):
        if self.validator:
            self.validator.recite_protocol()
            self.append_log("VOICE: Recited current step once.")

    def _on_rotation_changed(self, index: int):
        angle = index * 90
        if self.cap and hasattr(self.cap, "set_rotation"):
            self.cap.set_rotation(angle)
        self.append_log(f"CAMERA: Video Rotation set to {angle}°")

    def _on_flip_toggle(self, state):
        flip_enabled = (state == 2 or state == Qt.CheckState.Checked)
        if self.cap:
            self.cap.set_flip(flip_enabled)
        self.append_log(f"CAMERA: Horizontal Mirror View -> {'ENABLED' if flip_enabled else 'DISABLED'}")

    def _on_mock_sensor_toggle(self, state):
        confirmed = (state == 2 or state == Qt.CheckState.Checked)
        if self.verifier:
            self.verifier.set_mock_sensor(confirmed=confirmed, reading=3.3 if confirmed else 0.0)
            self.append_log(f"TELEMETRY: Mock Sensor State toggled -> {'CONFIRMED (3.3V)' if confirmed else 'FAILED (0.0V)'}")

    def trigger_next_step(self):
        """Force-advance the validator to the next expected step (for demo/manual override)."""
        if not self.validator:
            self.append_log("ADVANCE: No validator connected.")
            return

        expected = self.validator.get_expected_next_steps()
        if not expected:
            self.append_log("ADVANCE: All steps already completed.")
            return

        step_id = min(expected)
        step_def = self.validator.steps_by_id.get(step_id)
        if not step_def:
            return

        # Synthesize a high-confidence event matching this step's trigger
        event_str = step_def.get("event", "")
        # Take the first alternative if pipe-separated
        primary_event = event_str.split("|")[0].strip() if event_str else f"manual_advance:{step_id}"

        synthetic_event = {
            "type": primary_event,
            "object": "manual",
            "confidence": 1.0,
            "timestamp": time.time(),
        }
        result = self.validator.process_event(synthetic_event, current_frame=None, now=time.time())
        if result:
            self.append_log(f"ADVANCE: Step {step_id} ({step_def['name']}) -> {result.get('status', 'OK')}")
        else:
            self.append_log(f"ADVANCE: Step {step_id} event sent but not accepted (check dependencies).")

    def append_log(self, text: str):
        self.log_queue.put(text)

    def update_frame(self, frame: np.ndarray, trajectories: Optional[Dict[str, Any]] = None):
        """Thread-safe frame buffer update called from worker thread."""
        with self.frame_lock:
            self.latest_frame = frame.copy() if frame is not None else None
            self.latest_trajectories = trajectories

    def update_status(self, data: Dict[str, Any]):
        """Thread-safe status update called from worker thread."""
        self.status_queue.put(data)

    def _refresh_steps_display(self):
        if not self.validator:
            return

        completed_ids = getattr(self.validator, "completed_step_ids", set())
        expected_ids = self.validator.get_expected_next_steps()
        primary_active_id = min(expected_ids) if expected_ids else None

        for step in self.steps:
            s_id = step["id"]
            s_name = step["name"].replace("_", " ").title()
            exp_targets = step.get("expected_targets", [])
            target_str = f" [ROI: {', '.join(exp_targets)}]" if exp_targets else ""

            if s_id in completed_ids:
                status_text = f"✓ Step {s_id}: {s_name} — COMPLETED (OK)"
                style = "color: #00e676; font-weight: bold; font-size: 11px; padding: 2px;"
            elif s_id == primary_active_id:
                status_text = f"▶ Step {s_id}: {s_name}{target_str} — CURRENT ACTIVE"
                style = "color: #ff9800; font-weight: bold; font-size: 11px; padding: 2px; background-color: #181818; border: 1px solid #ff9800; border-radius: 3px;"
            else:
                status_text = f"○ Step {s_id}: {s_name}{target_str} — PENDING"
                style = "color: #777777; font-size: 11px; padding: 2px;"

            if s_id in self.step_labels:
                self.step_labels[s_id].setText(status_text)
                self.step_labels[s_id].setStyleSheet(style)

    def _render_frame(self, frame: np.ndarray, trajectories: Optional[Dict[str, Any]]):
        display_frame = frame.copy()

        # Draw ROI Polygons
        for r_name, r_box in self.rois.items():
            color = (0, 165, 255) if "work" in r_name else ((50, 205, 50) if "staging" in r_name else (255, 100, 0))
            cv2.rectangle(display_frame, (r_box[0], r_box[1]), (r_box[2], r_box[3]), color, 2)
            cv2.putText(
                display_frame,
                f"ROI: {r_name.upper()}",
                (r_box[0] + 5, r_box[1] + 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

        # Draw Next Step text overlay in bottom-right corner
        if self.validator:
            overlay_h, overlay_w = display_frame.shape[:2]
            margin = 12
            line_height = 22
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.50
            thickness = 1

            # Find last completed step name for green text
            completed_ids = getattr(self.validator, "completed_step_ids", set())
            if completed_ids:
                last_done_id = max(completed_ids)
                last_done_step = self.validator.steps_by_id.get(last_done_id)
                if last_done_step:
                    done_text = f"[OK] Step {last_done_id}: {last_done_step['name'].replace('_', ' ').title()}"
                    text_size = cv2.getTextSize(done_text, font, font_scale, thickness)[0]
                    tx = overlay_w - text_size[0] - margin
                    ty = overlay_h - margin - line_height
                    # Dark background for readability
                    cv2.rectangle(display_frame, (tx - 4, ty - text_size[1] - 4), (tx + text_size[0] + 4, ty + 6), (0, 0, 0), -1)
                    cv2.putText(display_frame, done_text, (tx, ty), font, font_scale, (126, 231, 135), thickness, cv2.LINE_AA)

            # Find next pending step for white text
            expected = self.validator.get_expected_next_steps()
            if expected:
                next_id = min(expected)
                next_step = self.validator.steps_by_id.get(next_id)
                if next_step:
                    next_text = f">> Step {next_id}: {next_step['name'].replace('_', ' ').title()}"
                    text_size = cv2.getTextSize(next_text, font, font_scale, thickness)[0]
                    tx = overlay_w - text_size[0] - margin
                    ty = overlay_h - margin
                    cv2.rectangle(display_frame, (tx - 4, ty - text_size[1] - 4), (tx + text_size[0] + 4, ty + 6), (0, 0, 0), -1)
                    cv2.putText(display_frame, next_text, (tx, ty), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
            elif self.validator.is_completed:
                done_text = ">> ALL STEPS COMPLETED"
                text_size = cv2.getTextSize(done_text, font, font_scale, thickness)[0]
                tx = overlay_w - text_size[0] - margin
                ty = overlay_h - margin
                cv2.rectangle(display_frame, (tx - 4, ty - text_size[1] - 4), (tx + text_size[0] + 4, ty + 6), (0, 0, 0), -1)
                cv2.putText(display_frame, done_text, (tx, ty), font, font_scale, (126, 231, 135), thickness, cv2.LINE_AA)

        # Convert to QPixmap on GUI thread
        rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.video_label.setPixmap(pix.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def _apply_status_update(self, data: Dict[str, Any]):
        event_type = data.get("type", "")
        banner = data.get("banner", "")
        alert = data.get("alert_payload", {})

        if event_type == "alert":
            self.status_banner.setStyleSheet("""
                background-color: #da3633;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            """)
            self.status_banner.setText(f"VIOLATION: {banner}")
            if alert:
                self.alert_detail_label.setText(
                    f"DETECTED: {alert.get('detected')}\n"
                    f"EXPECTED: {alert.get('expected')}\n"
                    f"ACTION: {alert.get('recommended_action')}"
                )
                self.alert_detail_label.setStyleSheet("color: #f85149; font-size: 11px;")

        elif event_type == "predictive_warning":
            self.status_banner.setStyleSheet("""
                background-color: #d29922;
                color: #0d1117;
                font-size: 13px;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            """)
            self.status_banner.setText(f"PREDICTIVE CAUTION: {banner}")
            if alert:
                self.alert_detail_label.setText(
                    f"FORECAST: {alert.get('detected')} (Confidence {alert.get('confidence')})\n"
                    f"ACTION: {alert.get('recommended_action')}"
                )
                self.alert_detail_label.setStyleSheet("color: #e3b341; font-size: 11px;")

        elif event_type == "step_completed":
            self.status_banner.setStyleSheet("""
                background-color: #238636;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
            """)
            self.status_banner.setText(banner)
            self.alert_detail_label.setText("Step verified nominally. Sequence progression active.")
            self.alert_detail_label.setStyleSheet("color: #7ee787; font-size: 11px;")

        self._refresh_steps_display()

    def _update_loop(self):
        """Main GUI update loop triggered by QTimer at ~30 FPS."""
        # 1. Drain log messages
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            except queue.Empty:
                break

        # 2. Drain status messages
        while not self.status_queue.empty():
            try:
                st = self.status_queue.get_nowait()
                self._apply_status_update(st)
            except queue.Empty:
                break

        # 3. Render latest video frame
        with self.frame_lock:
            frame = self.latest_frame
            trajectories = self.latest_trajectories

        if frame is not None:
            self._render_frame(frame, trajectories)

        # 4. Update live procedure-quality score
        if self.scorer:
            metrics = self.scorer.compute_score()
            score = metrics["overall_score"]
            self.score_label.setText(f"LIVE QUALITY SCORE: {score:.1f}%")
            self.score_bar.setValue(int(score))
            self.metrics_label.setText(
                f"Accuracy: {metrics['accuracy']}% | Speed: {metrics['speed_factor']} | "
                f"Cleanliness: {metrics['cleanliness']}% | Violations: {metrics['deviations']} | "
                f"Near-Misses: {metrics['predictive_warnings']}"
            )
