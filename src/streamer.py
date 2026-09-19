"""
Dual Video Streamer and Local MP4 Recorder for PRAHARI.
Writes session recordings to disk and asynchronously streams low-latency video via UDP ffmpeg.
Streaming failure is non-blocking and never interrupts local recording.
"""

import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional
import cv2
import numpy as np

try:
    from paths import get_recordings_dir
except ImportError:
    get_recordings_dir = lambda: os.path.abspath("recordings")


class DualStreamer:
    def __init__(
        self,
        experiment_id: str,
        recordings_dir: Optional[str] = None,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        stream_ip: Optional[str] = None,
        stream_port: int = 5000,
    ):
        self.experiment_id = experiment_id
        self.recordings_dir = recordings_dir if recordings_dir is not None else get_recordings_dir()
        self.width = width
        self.height = height
        self.fps = fps
        self.stream_ip = stream_ip
        self.stream_port = stream_port

        os.makedirs(self.recordings_dir, exist_ok=True)
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.recording_path = os.path.join(
            self.recordings_dir, f"{self.experiment_id}_{self.timestamp}.mp4"
        )

        self.writer: Optional[cv2.VideoWriter] = None
        self.ffmpeg_proc: Optional[subprocess.Popen] = None
        self.ffmpeg_failed = False

        self._init_local_writer()
        if self.stream_ip:
            self._init_network_stream()

    def _init_local_writer(self):
        try:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.writer = cv2.VideoWriter(
                self.recording_path, fourcc, self.fps, (self.width, self.height)
            )
            print(f"[DualStreamer] Local recording initiated: {self.recording_path}")
        except Exception as e:
            print(f"[DualStreamer] Failed to initialize local VideoWriter: {e}")

    def _init_network_stream(self):
        """Spawns an ffmpeg subprocess to push UDP stream."""
        target_url = f"udp://{self.stream_ip}:{self.stream_port}"
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-b:v", "500k",
            "-f", "mpegts",
            target_url,
        ]
        try:
            self.ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[DualStreamer] UDP network stream started: {target_url}")
        except Exception as e:
            print(f"[DualStreamer] FFmpeg network stream failed to launch ({e}). Continuing local recording only.")
            self.ffmpeg_failed = True

    def write_frame(self, frame: np.ndarray):
        """Write frame to local disk and pipe to ffmpeg if active."""
        if frame is None:
            return

        # Ensure correct dimensions
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))

        # 1. Local disk write
        if self.writer is not None:
            try:
                self.writer.write(frame)
            except Exception as e:
                print(f"[DualStreamer] Error writing local frame: {e}")

        # 2. FFmpeg stream write
        if self.ffmpeg_proc is not None and not self.ffmpeg_failed:
            try:
                self.ffmpeg_proc.stdin.write(frame.tobytes())
            except Exception:
                # Broken pipe or process terminated; fallback smoothly
                self.ffmpeg_failed = True
                self.ffmpeg_proc = None

    def close(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            print(f"[DualStreamer] Recording saved to: {self.recording_path}")

        if self.ffmpeg_proc is not None:
            try:
                self.ffmpeg_proc.stdin.close()
                self.ffmpeg_proc.terminate()
                self.ffmpeg_proc.wait(timeout=1.0)
            except Exception:
                pass
            self.ffmpeg_proc = None
