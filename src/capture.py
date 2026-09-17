"""
Asynchronous video capture thread for PRAHARI HAR Space Experiment Assistant.
Captures frames in a background thread to prevent camera buffer latency.
Provides automatic synthetic frame generation fallback when no webcam is present.
"""

import threading
import time
from typing import Optional, Tuple
import cv2
import numpy as np


class VideoCaptureThread:
    def __init__(
        self,
        source: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        video_file: Optional[str] = None,
        flip_horizontal: bool = False,
    ):
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.video_file = video_file
        self.flip_horizontal = flip_horizontal

        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.running = False
        self.lock = threading.Lock()
        self.is_synthetic = False
        self.frame_count = 0

        self._init_capture()

    def set_flip(self, flip: bool):
        with self.lock:
            self.flip_horizontal = flip

    def _init_capture(self):
        target = self.video_file if self.video_file else self.source
        try:
            if isinstance(target, int):
                # Try DirectShow on Windows for instant, reliable hardware access
                self.cap = cv2.VideoCapture(target, cv2.CAP_DSHOW)
                if not self.cap or not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(target)
            else:
                self.cap = cv2.VideoCapture(target)

            if self.cap and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    self.latest_frame = frame
                    self.is_synthetic = False
                    print(f"[VideoCaptureThread] Camera {target} successfully opened and streaming.")
                    return
        except Exception as e:
            print(f"[VideoCaptureThread] Camera init error ({target}): {e}")

        # Fallback to synthetic frame generator
        print(f"[VideoCaptureThread] Physical camera ({target}) not available. Falling back to synthetic feed.")
        self.is_synthetic = True
        self.latest_frame = self._generate_synthetic_frame()

    def _generate_synthetic_frame(self) -> np.ndarray:
        """Generates a clean simulated workbench video frame for offline demos."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        # Background dark slate
        frame[:] = (35, 30, 25)
        
        # Grid lines
        for y in range(0, self.height, 40):
            cv2.line(frame, (0, y), (self.width, y), (45, 40, 35), 1)
        for x in range(0, self.width, 40):
            cv2.line(frame, (x, 0), (x, self.height), (45, 40, 35), 1)

        # Header watermark
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"PRAHARI SIMULATION FEED | {t_str}", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 220, 100), 1, cv2.LINE_AA)
        return frame

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        frame_interval = 1.0 / float(self.fps)
        while self.running:
            t0 = time.time()
            if not self.is_synthetic and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.latest_frame = frame
                else:
                    if self.video_file:
                        # Loop video file
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            else:
                # Update synthetic animation
                self.frame_count += 1
                with self.lock:
                    self.latest_frame = self._generate_synthetic_frame()

            elapsed = time.time() - t0
            sleep_time = max(0.001, frame_interval - elapsed)
            time.sleep(sleep_time)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        with self.lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()
                if self.flip_horizontal:
                    frame = cv2.flip(frame, 1)
                return (True, frame)
            return (False, None)

    def stop(self):
        self.running = False
        if hasattr(self, "thread") and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap and self.cap.isOpened():
            self.cap.release()
