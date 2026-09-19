"""
Asynchronous video capture thread for PRAHARI HAR Space Experiment Assistant.
Captures frames in a background thread to prevent camera buffer latency.
Provides automatic synthetic frame generation fallback when no webcam is present.
Supports:
  1. "usb": OpenCV DirectShow / V4L2 local webcam access
  2. "ip": RTSP/TCP and HTTP MJPEG network streams with auto-reconnection
  3. "browser": In-process zero-install Android Chrome browser camera bridge with rotation, lens switch, and pause/resume controls.
"""

import os
import socket
import threading
import time
import json
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional, Tuple, List, Dict, Any, Union
import cv2
import numpy as np

# Configure OpenCV FFmpeg to avoid hanging and network -138 timeouts on IP camera streams
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;3000000|buffer_size;1024000"

# 1. Camera Configuration Block Schema (JSON / Dict specification)
DEFAULT_CAMERA_CONFIG: Dict[str, Any] = {
    "id": "phone_cam",
    "type": "browser",  # "usb", "ip", or "browser"
    "bridge_port": 8000,
    "url": "rtsp://admin:${CAM_PASSWORD}@192.168.1.100:554/stream1",
    "backend": "cv2.CAP_FFMPEG",
    "reconnect": True,
    "max_reconnect_delay_s": 5.0,
    "read_timeout_s": 3.0,
}


def get_local_ip() -> str:
    """Detects the primary LAN IPv4 address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


# HTML page served to the mobile browser with Rotation, Lens Switch, and Pause/Resume controls
BROWSER_BRIDGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>PRAHARI Vision Bridge</title>
  <style>
    * { box-sizing: border-box; }
    body {
      background-color: #0a0e17;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0;
      padding: 16px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      text-align: center;
    }
    .card {
      background-color: #131926;
      border: 1px solid #1f293d;
      border-radius: 14px;
      padding: 20px 16px;
      max-width: 460px;
      width: 100%;
      box-shadow: 0 10px 30px rgba(0,0,0,0.6);
    }
    h1 {
      font-size: 19px;
      margin: 0 0 4px 0;
      color: #58a6ff;
      letter-spacing: 1.5px;
      font-weight: 700;
    }
    .subtitle {
      font-size: 11px;
      color: #7d8590;
      margin-bottom: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    .badge {
      display: inline-block;
      padding: 6px 16px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: bold;
      margin: 6px 0 12px 0;
      transition: all 0.3s ease;
    }
    .streaming {
      background-color: #238636;
      color: #ffffff;
      box-shadow: 0 0 12px rgba(35, 134, 54, 0.6);
    }
    .paused {
      background-color: #f0883e;
      color: #ffffff;
    }
    .waiting {
      background-color: #d29922;
      color: #000000;
    }
    .error {
      background-color: #da3633;
      color: #ffffff;
    }
    .video-container {
      position: relative;
      width: 100%;
      background-color: #000;
      border-radius: 8px;
      border: 1px solid #30363d;
      overflow: hidden;
      margin-bottom: 12px;
    }
    #video {
      width: 100%;
      max-height: 240px;
      object-fit: contain;
      display: block;
    }
    .stats {
      font-size: 12px;
      color: #00e676;
      font-family: monospace;
      margin-top: 6px;
    }
    .btn-row {
      display: flex;
      gap: 8px;
      justify-content: center;
      margin-top: 12px;
      flex-wrap: wrap;
    }
    button {
      background-color: #21262d;
      color: #e6edf3;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 9px 14px;
      font-size: 13px;
      font-weight: bold;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background-color 0.2s;
    }
    button:hover {
      background-color: #30363d;
    }
    button.btn-stop {
      background-color: #b62324;
      border-color: #da3633;
      color: white;
    }
    button.btn-stop:hover {
      background-color: #da3633;
    }
    button.btn-resume {
      background-color: #238636;
      border-color: #2ea043;
      color: white;
    }
    button.btn-resume:hover {
      background-color: #2ea043;
    }
    .info-box {
      background-color: #0d1117;
      border: 1px solid #21262d;
      border-radius: 8px;
      padding: 8px 10px;
      margin-top: 14px;
      font-size: 11px;
      color: #8b949e;
      line-height: 1.4;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>[PRAHARI] VISION BRIDGE</h1>
    <div class="subtitle">Mobile Camera Telemetry Stream</div>
    
    <div id="statusBadge" class="badge waiting">Connecting to Camera...</div>
    <div id="statusText" style="font-size: 12px; color: #8b949e; margin-bottom: 8px;">
      Grant camera permission when prompted by Chrome.
    </div>

    <div class="video-container">
      <video id="video" autoplay playsinline muted></video>
    </div>
    <canvas id="canvas" style="display:none;"></canvas>

    <div class="stats" id="stats">Frames Sent: 0 | Rate: ~8 FPS | Orientation: 0°</div>

    <!-- Interactive Controls -->
    <div class="btn-row">
      <button id="btnToggleStream" class="btn-stop" onclick="toggleStreaming()">
        <span>⏹</span> Stop Streaming
      </button>
      <button id="btnRotate" onclick="rotatePhoneCamera()">
        <span>🔄</span> Rotate: <span id="lblAngle">0°</span>
      </button>
      <button id="btnSwitchLens" onclick="switchCameraLens()">
        <span>📷</span> Switch Lens
      </button>
    </div>
    
    <button id="retryBtn" style="display:none; margin-top: 10px; width: 100%; background-color: #238636;" onclick="startStream()">Grant Camera Access</button>

    <div class="info-box">
      <b>Active Uplink:</b> Transmitting video directly to PRAHARI workbench. Use buttons above to rotate or stop transmission.
    </div>
  </div>

  <script>
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const statusBadge = document.getElementById('statusBadge');
    const statusText = document.getElementById('statusText');
    const stats = document.getElementById('stats');
    const retryBtn = document.getElementById('retryBtn');
    const btnToggleStream = document.getElementById('btnToggleStream');
    const lblAngle = document.getElementById('lblAngle');

    let frameCount = 0;
    let isSending = false;
    let streamActive = false;
    let isStreamingPaused = false;
    let sendIntervalTimer = null;
    let currentRotation = 0; // 0, 90, 180, 270
    let currentFacingMode = "environment"; // "environment" or "user"
    let currentMediaStream = null;

    async function startStream() {
      retryBtn.style.display = 'none';
      statusBadge.className = 'badge waiting';
      statusBadge.textContent = 'Connecting...';
      statusText.textContent = 'Opening camera sensor...';

      if (currentMediaStream) {
        currentMediaStream.getTracks().forEach(track => track.stop());
      }

      try {
        const constraints = {
          video: {
            facingMode: { ideal: currentFacingMode },
            width: { ideal: 1280, max: 1920 },
            height: { ideal: 720, max: 1080 }
          },
          audio: false
        };
        currentMediaStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = currentMediaStream;
        await video.play();

        statusBadge.className = 'badge streaming';
        statusBadge.textContent = 'Streaming to PRAHARI...';
        statusText.textContent = 'Live camera stream connected to PRAHARI pipeline.';
        streamActive = true;
        isStreamingPaused = false;
        btnToggleStream.className = 'btn-stop';
        btnToggleStream.innerHTML = '<span>⏹</span> Stop Streaming';

        if (sendIntervalTimer) clearInterval(sendIntervalTimer);
        sendIntervalTimer = setInterval(sendFrame, 120);
      } catch (err) {
        console.error("Camera access error:", err);
        statusBadge.className = 'badge error';
        statusBadge.textContent = 'Camera Access Blocked';
        statusText.textContent = 'Please enable camera permissions in Chrome settings.';
        retryBtn.style.display = 'inline-block';
      }
    }

    function toggleStreaming() {
      if (isStreamingPaused) {
        // Resume streaming
        isStreamingPaused = false;
        statusBadge.className = 'badge streaming';
        statusBadge.textContent = 'Streaming to PRAHARI...';
        statusText.textContent = 'Live feed active.';
        btnToggleStream.className = 'btn-stop';
        btnToggleStream.innerHTML = '<span>⏹</span> Stop Streaming';
      } else {
        // Stop streaming
        isStreamingPaused = true;
        statusBadge.className = 'badge paused';
        statusBadge.textContent = '⏸ Stream Paused';
        statusText.textContent = 'Transmission stopped. PRAHARI is holding last frame.';
        btnToggleStream.className = 'btn-resume';
        btnToggleStream.innerHTML = '<span>▶</span> Resume Streaming';
      }
    }

    function rotatePhoneCamera() {
      currentRotation = (currentRotation + 90) % 360;
      lblAngle.textContent = currentRotation + '°';
      updateStats(0);
    }

    async function switchCameraLens() {
      currentFacingMode = (currentFacingMode === "environment") ? "user" : "environment";
      await startStream();
    }

    function updateStats(latencyMs) {
      const latText = latencyMs > 0 ? latencyMs + 'ms' : '-- ms';
      const statusTextState = isStreamingPaused ? '[PAUSED]' : '[STREAMING]';
      stats.textContent = `Frames: ${frameCount} | ${statusTextState} | Rotation: ${currentRotation}° | Latency: ${latText}`;
    }

    async function sendFrame() {
      if (!streamActive || isStreamingPaused || isSending) return;
      if (video.videoWidth === 0 || video.videoHeight === 0) return;

      const vw = video.videoWidth;
      const vh = video.videoHeight;

      if (currentRotation === 90 || currentRotation === 270) {
        canvas.width = vh;
        canvas.height = vw;
      } else {
        canvas.width = vw;
        canvas.height = vh;
      }

      ctx.save();
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate((currentRotation * Math.PI) / 180);
      ctx.drawImage(video, -vw / 2, -vh / 2, vw, vh);
      ctx.restore();

      isSending = true;
      const t0 = performance.now();

      canvas.toBlob(async (blob) => {
        if (!blob) {
          isSending = false;
          return;
        }
        try {
          const resp = await fetch('/frame', {
            method: 'POST',
            body: blob,
            headers: { 'Content-Type': 'image/jpeg' }
          });
          if (resp.ok) {
            frameCount++;
            const lat = Math.round(performance.now() - t0);
            updateStats(lat);
          }
        } catch (e) {
          console.warn("Upload failed:", e);
        } finally {
          isSending = false;
        }
      }, 'image/jpeg', 0.80);
    }

    window.addEventListener('load', startStream);
  </script>
</body>
</html>
"""


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BrowserBridgeHTTPHandler(BaseHTTPRequestHandler):
    bridge: Optional["BrowserCameraBridge"] = None

    def log_message(self, format, *args):
        # Silence standard HTTP access logs to keep PRAHARI CLI output clean
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            body = BROWSER_BRIDGE_HTML.encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            has_frame = self.bridge.has_recent_frame() if self.bridge else False
            body = json.dumps({"active": has_frame}).encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/frame":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                jpeg_data = self.rfile.read(content_length)
                if self.bridge:
                    self.bridge.update_frame(jpeg_data)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


class BrowserCameraBridge:
    """
    In-process lightweight HTTP server that receives JPEG frames from
    a mobile Chrome browser session and decodes them into memory.
    """
    _instance: Optional["BrowserCameraBridge"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, port: int = 8000) -> "BrowserCameraBridge":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(port=port)
            return cls._instance

    def __init__(self, port: int = 8000):
        self.port = port
        self.lan_ip = get_local_ip()
        self.latest_frame: Optional[np.ndarray] = None
        self.last_frame_time: float = 0.0
        self.frame_count: int = 0
        self.lock = threading.Lock()
        self.server: Optional[ThreadedHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False

    def start(self):
        if self.running:
            return
        try:
            handler_class = BrowserBridgeHTTPHandler
            handler_class.bridge = self
            self.server = ThreadedHTTPServer(("0.0.0.0", self.port), handler_class)
            self.running = True
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()

            print("\n" + "=" * 76)
            print("[PRAHARI] BROWSER CAMERA BRIDGE ACTIVE")
            print(f"   Open this URL on your phone's Chrome browser:")
            print(f"   --> http://{self.lan_ip}:{self.port}")
            print("=" * 76 + "\n")
        except Exception as e:
            print(f"[BrowserCameraBridge] Error starting server on port {self.port}: {e}")

    def update_frame(self, jpeg_bytes: bytes):
        try:
            frame = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is not None:
                with self.lock:
                    self.latest_frame = frame
                    self.last_frame_time = time.time()
                    self.frame_count += 1
        except Exception as e:
            print(f"[BrowserCameraBridge] Decode error: {e}")

    def has_recent_frame(self, timeout_s: float = 4.0) -> bool:
        with self.lock:
            return (self.latest_frame is not None) and ((time.time() - self.last_frame_time) <= timeout_s)

    def get_latest_frame(self, timeout_s: float = 4.0) -> Optional[np.ndarray]:
        with self.lock:
            if self.latest_frame is not None and (time.time() - self.last_frame_time <= timeout_s):
                return self.latest_frame.copy()
            return None

    def stop(self):
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None


class BrowserVideoCapture:
    """VideoCapture-compatible wrapper around BrowserCameraBridge."""
    def __init__(self, port: int = 8000):
        self.port = port
        self.bridge = BrowserCameraBridge.get_instance(port)
        self.bridge.start()
        self._is_opened = True

    def isOpened(self) -> bool:
        return self._is_opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        frame = self.bridge.get_latest_frame()
        if frame is not None:
            return (True, frame)
        return (False, None)

    def set(self, propId, value):
        return True

    def get(self, propId):
        return 0

    def release(self):
        self._is_opened = False

    def open(self, *args, **kwargs):
        self._is_opened = True
        return True


def open_camera(cam_cfg: Optional[Union[Dict[str, Any], int, str]] = None) -> Optional[Any]:
    """
    Opens a video capture device based on the camera configuration block.

    Branches on cam_cfg["type"]:
      - "usb": Opens cv2.VideoCapture(device_index)
      - "ip": Substitutes environment variables in the RTSP URL via os.path.expandvars,
              opens cv2.VideoCapture(url, cv2.CAP_FFMPEG), and sets cv2.CAP_PROP_BUFFERSIZE to 1
              so stale buffered frames are not processed.
      - "browser": Starts the local in-process browser camera bridge on bridge_port, prints
              the phone URL to console, and returns a BrowserVideoCapture instance.

    Parameters:
        cam_cfg: Dictionary with keys: id, type, bridge_port, url, backend, reconnect, max_reconnect_delay_s, read_timeout_s.
                 Can also be an int device index or URL string shorthand.

    Returns:
        VideoCapture or BrowserVideoCapture instance.
    """
    if cam_cfg is None:
        cam_cfg = DEFAULT_CAMERA_CONFIG

    if isinstance(cam_cfg, int):
        cam_cfg = {"type": "usb", "id": cam_cfg}
    elif isinstance(cam_cfg, str):
        if cam_cfg.strip().isdigit():
            cam_cfg = {"type": "usb", "id": int(cam_cfg.strip())}
        elif cam_cfg.strip().lower() in ("browser", "chrome", "phone", "web"):
            cam_cfg = {"type": "browser", "bridge_port": 8000}
        else:
            cam_cfg = {"type": "ip", "url": cam_cfg}

    cam_type = str(cam_cfg.get("type", "usb")).lower()

    if cam_type in ("browser", "chrome", "phone", "web"):
        port = int(cam_cfg.get("bridge_port", 8000))
        cap = BrowserVideoCapture(port=port)
        return cap

    elif cam_type == "usb":
        device_index = cam_cfg.get("id", 0)
        if isinstance(device_index, str) and device_index.isdigit():
            device_index = int(device_index)
        try:
            # Try DirectShow on Windows for instant, reliable hardware access
            cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
            if not cap or not cap.isOpened():
                cap = cv2.VideoCapture(device_index)
        except Exception as e:
            print(f"[open_camera] DirectShow initialization fallback ({device_index}): {e}")
            cap = cv2.VideoCapture(device_index)
        if cap and cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    elif cam_type == "ip":
        raw_url = cam_cfg.get("url", "")
        # Substitute environment variables into URL (e.g. ${CAM_PASSWORD})
        url = os.path.expandvars(raw_url)

        # Configure timeout in OpenCV FFmpeg capture options if read_timeout_s is specified
        read_timeout = float(cam_cfg.get("read_timeout_s", 3.0))
        timeout_us = int(read_timeout * 1000000)
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;tcp|timeout;{timeout_us}|buffer_size;1024000"
        )

        backend_val = cam_cfg.get("backend")
        backend_api = cv2.CAP_FFMPEG
        if isinstance(backend_val, int):
            backend_api = backend_val

        try:
            cap = cv2.VideoCapture(url, backend_api)
            if cap and cap.isOpened():
                # Set buffer size to 1 on IP path so we do not process stale buffered frames
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                print(f"[open_camera] IP Camera successfully connected (CAP_PROP_BUFFERSIZE=1).")
            else:
                print(f"[open_camera] Warning: Could not open IP camera stream: {url}")
        except Exception as e:
            print(f"[open_camera] Exception opening IP camera stream: {e}")
            cap = None
        return cap

    else:
        print(f"[open_camera] Unsupported camera type '{cam_type}'. Defaulting to USB 0.")
        return cv2.VideoCapture(0)


def read_frame_with_reconnect(
    cap: Optional[Any],
    cam_cfg: Optional[Union[Dict[str, Any], int, str]] = None,
) -> Optional[np.ndarray]:
    """
    Wrapper around cap.read() that, on a failed read:
    - releases the capture
    - waits up to max_reconnect_delay_s
    - reopens via open_camera() / in-place cap.open()
    - returns None for that cycle instead of crashing.

    The main capture loop treats a None frame as 'skip this cycle'.
    """
    if cam_cfg is None:
        cam_cfg = DEFAULT_CAMERA_CONFIG

    if isinstance(cam_cfg, int):
        cam_cfg = {"type": "usb", "id": cam_cfg}
    elif isinstance(cam_cfg, str):
        if cam_cfg.strip().isdigit():
            cam_cfg = {"type": "usb", "id": int(cam_cfg.strip())}
        elif cam_cfg.strip().lower() in ("browser", "chrome", "phone", "web"):
            cam_cfg = {"type": "browser", "bridge_port": 8000}
        else:
            cam_cfg = {"type": "ip", "url": cam_cfg}

    cam_type = str(cam_cfg.get("type", "usb")).lower()

    # Special handling for Browser Camera Bridge
    if cam_type in ("browser", "chrome", "phone", "web") or isinstance(cap, BrowserVideoCapture):
        if cap is not None and cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                return frame
        return None

    should_reconnect = bool(cam_cfg.get("reconnect", True))
    max_delay = float(cam_cfg.get("max_reconnect_delay_s", 5.0))

    if cap is not None and cap.isOpened():
        try:
            ret, frame = cap.read()
            if ret and frame is not None:
                return frame
        except Exception as e:
            print(f"[read_frame_with_reconnect] Frame read exception: {e}")

    # Failed read handling
    print("[read_frame_with_reconnect] Frame read failed or capture not open.")
    if cap is not None:
        try:
            cap.release()
        except Exception as e:
            print(f"[read_frame_with_reconnect] Capture release error: {e}")

    if should_reconnect:
        print(f"[read_frame_with_reconnect] Waiting {max_delay:.1f}s before reconnecting...")
        time.sleep(max_delay)
        if cap is not None and hasattr(cap, "open"):
            try:
                if cam_type == "usb":
                    device_index = cam_cfg.get("id", 0)
                    if isinstance(device_index, str) and device_index.isdigit():
                        device_index = int(device_index)
                    cap.open(device_index, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap.open(device_index)
                elif cam_type == "ip":
                    raw_url = cam_cfg.get("url", "")
                    url = os.path.expandvars(raw_url)
                    backend_val = cam_cfg.get("backend")
                    backend_api = cv2.CAP_FFMPEG if not isinstance(backend_val, int) else backend_val
                    cap.open(url, backend_api)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if cap.isOpened():
                    print("[read_frame_with_reconnect] Camera successfully reconnected.")
            except Exception as e:
                print(f"[read_frame_with_reconnect] Reconnect attempt error: {e}")
        else:
            open_camera(cam_cfg)

    return None


class VideoCaptureThread:
    def __init__(
        self,
        source: Union[int, str, Dict[str, Any]] = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        video_file: Optional[str] = None,
        flip_horizontal: bool = False,
        camera_config: Optional[Dict[str, Any]] = None,
    ):
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.video_file = video_file
        self.flip_horizontal = flip_horizontal
        self.rotation: int = 0  # 0, 90, 180, 270 degrees

        if camera_config is not None:
            self.cam_cfg = camera_config
        elif isinstance(source, dict):
            self.cam_cfg = source
        elif isinstance(source, str) and not source.strip().isdigit() and source.strip().lower() in ("browser", "chrome", "phone", "web"):
            self.cam_cfg = {
                "id": "phone_cam",
                "type": "browser",
                "bridge_port": 8000,
            }
        elif isinstance(source, str) and not source.strip().isdigit() and any(source.startswith(p) for p in ["rtsp://", "http://", "https://"]):
            self.cam_cfg = {
                "id": "ip_camera",
                "type": "ip",
                "url": source,
                "backend": "cv2.CAP_FFMPEG",
                "reconnect": True,
                "max_reconnect_delay_s": 5.0,
                "read_timeout_s": 3.0,
            }
        elif os.environ.get("PRAHARI_CAMERA_TYPE", "").lower() in ("browser", "chrome", "phone", "web") or os.environ.get("USE_BROWSER_CAM") == "1":
            port = int(os.environ.get("BRIDGE_PORT", 8000))
            self.cam_cfg = {
                "id": "phone_cam",
                "type": "browser",
                "bridge_port": port,
            }
        elif os.environ.get("RTSP_URL"):
            self.cam_cfg = {
                "id": "ip_camera",
                "type": "ip",
                "url": os.environ["RTSP_URL"],
                "backend": "cv2.CAP_FFMPEG",
                "reconnect": True,
                "max_reconnect_delay_s": 5.0,
                "read_timeout_s": 3.0,
            }
        elif os.environ.get("CAM_URL"):
            self.cam_cfg = {
                "id": "ip_camera",
                "type": "ip",
                "url": os.environ["CAM_URL"],
                "backend": "cv2.CAP_FFMPEG",
                "reconnect": True,
                "max_reconnect_delay_s": 5.0,
                "read_timeout_s": 3.0,
            }
        else:
            self.cam_cfg = {
                "id": source,
                "type": "usb",
                "url": "",
                "backend": "cv2.CAP_DSHOW" if os.name == "nt" else "cv2.CAP_ANY",
                "reconnect": True,
                "max_reconnect_delay_s": 5.0,
                "read_timeout_s": 3.0,
            }

        self.cap: Optional[Any] = None
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

    def set_rotation(self, angle: int):
        """Set video frame rotation: 0, 90, 180, or 270 degrees."""
        with self.lock:
            self.rotation = int(angle) % 360

    def _init_capture(self):
        target = self.video_file if self.video_file else self.source
        try:
            if self.video_file:
                self.cap = cv2.VideoCapture(self.video_file)
            else:
                self.cap = open_camera(self.cam_cfg)

            if self.cap and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    self.latest_frame = frame
                    self.is_synthetic = False
                    print(f"[VideoCaptureThread] Camera {target} successfully opened and streaming.")
                    return
        except Exception as e:
            print(f"[VideoCaptureThread] Camera init error ({target}): {e}")

        # Fallback / waiting synthetic feed
        cam_type = str(self.cam_cfg.get("type", "usb")).lower()
        if cam_type in ("browser", "chrome", "phone", "web"):
            port = self.cam_cfg.get("bridge_port", 8000)
            lan_ip = get_local_ip()
            print(f"[VideoCaptureThread] Waiting for mobile Chrome connection at http://{lan_ip}:{port}")
        else:
            print(f"[VideoCaptureThread] Physical/network camera ({target}) not available. Falling back to synthetic feed.")
        
        self.is_synthetic = True
        self.latest_frame = self._generate_synthetic_frame()

    def _generate_synthetic_frame(self) -> np.ndarray:
        """Generates a clean simulated workbench / waiting video frame."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:] = (20, 20, 20)
        
        # Grid lines
        for y in range(0, self.height, 40):
            cv2.line(frame, (0, y), (self.width, y), (35, 35, 35), 1)
        for x in range(0, self.width, 40):
            cv2.line(frame, (x, 0), (x, self.height), (35, 35, 35), 1)

        # Header watermark
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cam_type = str(self.cam_cfg.get("type", "usb")).lower()
        if cam_type in ("browser", "chrome", "phone", "web"):
            port = self.cam_cfg.get("bridge_port", 8000)
            lan_ip = get_local_ip()
            cv2.putText(frame, f"PRAHARI BROWSER BRIDGE | {t_str}", (15, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 100), 1, cv2.LINE_AA)
            cv2.putText(frame, f"WAITING FOR PHONE CAMERA UPLINK", (15, self.height // 2 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 230, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Open http://{lan_ip}:{port} in Chrome", (15, self.height // 2 + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        else:
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
        if "/shot.jpg" in url:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    data = resp.read()
                    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    return img
            except Exception:
                return None

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

            # Priority 1: Direct HTTP stream (IP camera MJPEG/snapshot)
            if self.http_stream_url:
                frame = self._read_http_frame()
                if frame is not None:
                    with self.lock:
                        self.latest_frame = frame
                        self.is_synthetic = False
                else:
                    time.sleep(0.01)

            # Priority 2: Video file replay
            elif self.video_file and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.latest_frame = frame
                        self.is_synthetic = False
                else:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            # Priority 3: Browser bridge / OpenCV VideoCapture (USB or RTSP)
            elif self.cap and self.cap.isOpened():
                frame = read_frame_with_reconnect(self.cap, self.cam_cfg)
                if frame is not None:
                    with self.lock:
                        self.latest_frame = frame
                        self.is_synthetic = False
                else:
                    # If waiting for browser frame or reconnecting, provide waiting feed
                    if self.is_synthetic or str(self.cam_cfg.get("type", "")).lower() in ("browser", "chrome", "phone", "web"):
                        self.frame_count += 1
                        with self.lock:
                            self.latest_frame = self._generate_synthetic_frame()
                    time.sleep(0.01)

            # Priority 4: Synthetic workbench feed fallback
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
                
                # Apply rotation if configured
                if self.rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif self.rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif self.rotation == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

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
        Switch to a new video source (IP camera URL, browser bridge, config dict, or device index) at runtime.
        """
        # 1. Config dictionary
        if isinstance(source, dict):
            self.cam_cfg = source
            new_cap = open_camera(source)
            if new_cap and new_cap.isOpened():
                with self.lock:
                    self._close_current_sources()
                    self.cap = new_cap
                    self.is_synthetic = False
                print(f"[VideoCaptureThread] Switched to camera config: {source.get('id', 'custom')}")
                return True
            return False

        # 2. Browser Bridge shorthand ("browser", "chrome", "phone", "web")
        if isinstance(source, str) and source.strip().lower() in ("browser", "chrome", "phone", "web"):
            self.cam_cfg = {
                "id": "phone_cam",
                "type": "browser",
                "bridge_port": 8000,
            }
            new_cap = open_camera(self.cam_cfg)
            if new_cap and new_cap.isOpened():
                with self.lock:
                    self._close_current_sources()
                    self.cap = new_cap
                    self.is_synthetic = False
                print(f"[VideoCaptureThread] Switched to Browser Camera Bridge on port 8000")
                return True
            return False

        # 3. Device index (Webcam)
        if isinstance(source, str) and source.strip().isdigit():
            source = int(source.strip())

        if isinstance(source, int):
            self.cam_cfg = {
                "id": source,
                "type": "usb",
                "url": "",
                "backend": "cv2.CAP_DSHOW" if os.name == "nt" else "cv2.CAP_ANY",
                "reconnect": True,
                "max_reconnect_delay_s": 5.0,
                "read_timeout_s": 3.0,
            }
            try:
                new_cap = open_camera(self.cam_cfg)
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

        # 4. Network IP Camera URL
        clean_url = str(source).strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://") or clean_url.startswith("rtsp://")):
            clean_url = "http://" + clean_url

        self.cam_cfg = {
            "id": "ip_cam",
            "type": "ip",
            "url": clean_url,
            "backend": "cv2.CAP_FFMPEG",
            "reconnect": True,
            "max_reconnect_delay_s": 5.0,
            "read_timeout_s": 3.0,
        }

        # Generate intelligent endpoint candidates to eliminate -138 error from missing stream paths
        candidates: List[str] = []
        parsed = clean_url.rstrip("/")
        has_subpath = any(ext in parsed.lower() for ext in ["/video", "/mjpeg", "/shot", ".sdp", ".m3u8", ".mp4"])
        if not has_subpath:
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

            try:
                cand_cfg = dict(self.cam_cfg)
                cand_cfg["url"] = cand
                new_cap = open_camera(cand_cfg)
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

            if cand.startswith("http://") or cand.startswith("https://"):
                try:
                    req = urllib.request.Request(os.path.expandvars(cand), headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=2.5) as test_resp:
                        test_data = test_resp.read(32768)
                        a = test_data.find(b"\xff\xd8")
                        b = test_data.find(b"\xff\xd9")
                        if a != -1 and b != -1:
                            test_img = cv2.imdecode(np.frombuffer(test_data[a : b + 2], dtype=np.uint8), cv2.IMREAD_COLOR)
                        else:
                            test_img = cv2.imdecode(np.frombuffer(test_data, dtype=np.uint8), cv2.IMREAD_COLOR)

                        if test_img is not None:
                            with self.lock:
                                self._close_current_sources()
                                self.http_stream_url = os.path.expandvars(cand)
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
