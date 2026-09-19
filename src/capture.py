"""
Asynchronous video capture thread for PRAHARI HAR Space Experiment Assistant.
Captures frames in a background thread to prevent camera buffer latency.
Provides automatic synthetic frame generation fallback when no webcam is present.
Supports OpenCV hardware access, RTSP/TCP, and direct HTTP MJPEG / snapshot streaming for mobile IP cams.
"""

import os
import threading
import time
import urllib.request
import urllib.error
from typing import Optional, Tuple, List
import cv2
import numpy as np

# Configure OpenCV FFmpeg to avoid hanging and network -138 timeouts on IP camera streams
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;3000000|buffer_size;1024000"


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
        self.http_stream_url: Optional[str] = None
        self.http_stream_response = None
        self.http_buffer = b""

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
        frame[:] = (20, 20, 20)
        
        # Grid lines
        for y in range(0, self.height, 40):
            cv2.line(frame, (0, y), (self.width, y), (35, 35, 35), 1)
        for x in range(0, self.width, 40):
            cv2.line(frame, (x, 0), (x, self.height), (35, 35, 35), 1)

        # Header watermark
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"PRAHARI SENSOR STREAM | {t_str}", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 100), 1, cv2.LINE_AA)
        return frame

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _read_http_frame(self) -> Optional[np.ndarray]:
        """Reads a JPEG frame directly over HTTP (supports MJPEG streams and snapshot endpoints)."""
        if not self.http_stream_url:
            return None

        url = self.http_stream_url
        # If static snapshot endpoint (e.g. /shot.jpg)
        if "/shot.jpg" in url:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    data = resp.read()
                    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    return img
            except Exception:
                return None

        # Continuous MJPEG stream
        try:
            if self.http_stream_response is None:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                self.http_stream_response = urllib.request.urlopen(req, timeout=3.0)

            while self.running:
                chunk = self.http_stream_response.read(8192)
                if not chunk:
                    self.http_stream_response = None
                    break
                self.http_buffer += chunk

                a = self.http_buffer.find(b"\xff\xd8")
                b = self.http_buffer.find(b"\xff\xd9")
                if a != -1 and b != -1:
                    jpg_bytes = self.http_buffer[a : b + 2]
                    self.http_buffer = self.http_buffer[b + 2 :]
                    img = cv2.imdecode(np.frombuffer(jpg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        return img
                elif len(self.http_buffer) > 200000:
                    self.http_buffer = b""
        except Exception:
            self.http_stream_response = None

        return None

    def _capture_loop(self):
        frame_interval = 1.0 / float(self.fps)
        while self.running:
            t0 = time.time()

            # Priority 1: Direct HTTP stream (IP camera)
            if self.http_stream_url:
                frame = self._read_http_frame()
                if frame is not None:
                    with self.lock:
                        self.latest_frame = frame
                        self.is_synthetic = False
                else:
                    time.sleep(0.01)

            # Priority 2: OpenCV VideoCapture (webcam, video file, or RTSP)
            elif not self.is_synthetic and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.latest_frame = frame
                else:
                    if self.video_file:
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    else:
                        time.sleep(0.01)

            # Priority 3: Synthetic workbench feed fallback
            else:
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

    def _close_current_sources(self):
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        if self.http_stream_response:
            try:
                self.http_stream_response.close()
            except Exception:
                pass
            self.http_stream_response = None

        self.http_stream_url = None
        self.http_buffer = b""

    def switch_source(self, source) -> bool:
        """
        Switch to a new video source (IP camera URL or device index) at runtime.
        Handles -138 network timeouts by normalizing URLs and using direct HTTP MJPEG fallback.
        """
        # 1. Device index (Webcam)
        if isinstance(source, str) and source.strip().isdigit():
            source = int(source.strip())

        if isinstance(source, int):
            try:
                new_cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
                if not new_cap or not new_cap.isOpened():
                    new_cap = cv2.VideoCapture(source)

                if new_cap and new_cap.isOpened():
                    ret, frame = new_cap.read()
                    if ret and frame is not None:
                        with self.lock:
                            self._close_current_sources()
                            self.cap = new_cap
                            self.latest_frame = frame
                            self.is_synthetic = False
                        print(f"[VideoCaptureThread] Switched to webcam index: {source}")
                        return True
                    new_cap.release()
            except Exception as e:
                print(f"[VideoCaptureThread] Failed to switch to webcam {source}: {e}")
            return False

        # 2. Network IP Camera URL
        clean_url = str(source).strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://") or clean_url.startswith("rtsp://")):
            clean_url = "http://" + clean_url

        # Generate intelligent endpoint candidates to eliminate -138 error from missing stream paths
        candidates: List[str] = []
        parsed = clean_url.rstrip("/")
        # Check if URL already specifies an endpoint
        has_subpath = any(ext in parsed.lower() for ext in ["/video", "/mjpeg", "/shot", ".sdp", ".m3u8", ".mp4"])
        if not has_subpath:
            # Common mobile IP cam streams (IP Webcam, DroidCam, etc.)
            candidates.append(f"{parsed}/video")
            candidates.append(f"{parsed}/mjpegfeed")
            candidates.append(f"{parsed}/shot.jpg")
            candidates.append(parsed)
        else:
            candidates.append(parsed)
            if "/video" in parsed:
                candidates.append(parsed.replace("/video", "/shot.jpg"))

        for cand in candidates:
            print(f"[VideoCaptureThread] Probing IP cam candidate: {cand}")

            # Option A: Try OpenCV VideoCapture
            try:
                new_cap = cv2.VideoCapture(cand, cv2.CAP_FFMPEG)
                if new_cap and new_cap.isOpened():
                    ret, frame = new_cap.read()
                    if ret and frame is not None:
                        with self.lock:
                            self._close_current_sources()
                            self.cap = new_cap
                            self.latest_frame = frame
                            self.is_synthetic = False
                        print(f"[VideoCaptureThread] Connected via OpenCV: {cand}")
                        return True
                    new_cap.release()
            except Exception:
                pass

            # Option B: Direct Python HTTP stream / snapshot connection (bypasses OpenCV -138 error)
            if cand.startswith("http://") or cand.startswith("https://"):
                try:
                    req = urllib.request.Request(cand, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=2.5) as test_resp:
                        test_data = test_resp.read(32768)
                        # Look for JPEG SOI/EOI
                        a = test_data.find(b"\xff\xd8")
                        b = test_data.find(b"\xff\xd9")
                        if a != -1 and b != -1:
                            test_img = cv2.imdecode(np.frombuffer(test_data[a : b + 2], dtype=np.uint8), cv2.IMREAD_COLOR)
                        else:
                            test_img = cv2.imdecode(np.frombuffer(test_data, dtype=np.uint8), cv2.IMREAD_COLOR)

                        if test_img is not None:
                            with self.lock:
                                self._close_current_sources()
                                self.http_stream_url = cand
                                self.latest_frame = test_img
                                self.is_synthetic = False
                            print(f"[VideoCaptureThread] Connected via HTTP Streamer: {cand}")
                            return True
                except Exception as e:
                    print(f"[VideoCaptureThread] Candidate {cand} note: {e}")

        print(f"[VideoCaptureThread] Could not connect to IP cam: {source}")
        return False

    def stop(self):
        self.running = False
        if hasattr(self, "thread") and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self._close_current_sources()

