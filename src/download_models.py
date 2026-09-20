"""
Automatic Model Weight & Task Asset Downloader for PRAHARI.
Ensures YOLO detector weights and MediaPipe hand landmarker task assets are acquired
deterministically and stored in writable user application storage (%LOCALAPPDATA%\\PRAHARI\\models)
or bundled application locations.
"""

import os
import sys
import shutil
import urllib.request
from typing import Dict, Optional

try:
    from paths import get_user_models_dir, resolve_asset_path, get_app_root
except ImportError:
    # Standalone execution fallback
    def get_user_models_dir() -> str:
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        p = os.path.join(base, "PRAHARI", "models")
        os.makedirs(p, exist_ok=True)
        return p

    def resolve_asset_path(p: str) -> str:
        return os.path.abspath(p)

    def get_app_root() -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


YOLO_URL = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
MEDIAPIPE_TASK_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"


def _download_file(url: str, dest_path: str, label: str):
    print(f"[download_models] Acquiring {label} from {url}...")
    temp_dest = dest_path + ".tmp"
    try:
        # User-agent header to avoid CDN blocks
        req = urllib.request.Request(url, headers={"User-Agent": "PRAHARI-Installer/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(temp_dest, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(temp_dest, dest_path)
        print(f"[download_models] Successfully saved {label} -> {dest_path}")
    except Exception as e:
        if os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except OSError:
                pass
        raise RuntimeError(f"Failed downloading {label} from {url}: {e}") from e


def setup_models(models_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Ensures both yolov8n.pt and hand_landmarker.task are present.
    Resolves writable target directory via %LOCALAPPDATA%\\PRAHARI\\models.
    Migrates legacy root-level yolov8n.pt if detected.
    Fails fast if a required model cannot be acquired.
    """
    target_dir = models_dir or get_user_models_dir()
    os.makedirs(target_dir, exist_ok=True)

    app_root = get_app_root()

    # 1. Legacy Migration: check if yolov8n.pt exists in repo root
    legacy_root_yolo = os.path.join(app_root, "yolov8n.pt")
    target_yolo = os.path.join(target_dir, "yolov8n.pt")
    bundled_models_yolo = os.path.join(app_root, "models", "yolov8n.pt")

    if os.path.exists(legacy_root_yolo) and not os.path.exists(bundled_models_yolo):
        try:
            os.makedirs(os.path.dirname(bundled_models_yolo), exist_ok=True)
            shutil.move(legacy_root_yolo, bundled_models_yolo)
            print(f"[download_models] Migrated legacy root yolov8n.pt -> {bundled_models_yolo}")
        except Exception as e:
            print(f"[download_models] Notice: Legacy yolo migration skipped: {e}")

    # 2. Resolve or acquire YOLO weights (required)
    resolved_yolo = resolve_asset_path("models/yolov8n.pt")
    if not os.path.exists(resolved_yolo):
        dest_yolo = os.path.join(target_dir, "yolov8n.pt")
        try:
            _download_file(YOLO_URL, dest_yolo, "YOLOv8n weights")
            resolved_yolo = dest_yolo
        except Exception as e:
            raise RuntimeError(
                f"FATAL: Required model 'yolov8n.pt' could not be acquired.\n"
                f"Error: {e}\n"
                f"Please ensure internet connectivity or place 'yolov8n.pt' in:\n"
                f"  {target_dir}\n"
                f"or\n"
                f"  {os.path.join(app_root, 'models')}"
            ) from e
    else:
        print(f"[download_models] YOLO model confirmed at {resolved_yolo}")

    # 3. Resolve or acquire MediaPipe Hand Landmarker task (recommended/required)
    resolved_task = resolve_asset_path("models/hand_landmarker.task")
    if not os.path.exists(resolved_task):
        dest_task = os.path.join(target_dir, "hand_landmarker.task")
        try:
            _download_file(MEDIAPIPE_TASK_URL, dest_task, "MediaPipe hand landmarker task")
            resolved_task = dest_task
        except Exception as e:
            print(f"[download_models] Warning: Could not download hand_landmarker.task ({e}). MediaPipe fallback tracking will be active.")
    else:
        print(f"[download_models] MediaPipe task confirmed at {resolved_task}")

    return {
        "yolo": resolved_yolo,
        "hand_landmarker": resolved_task,
    }


if __name__ == "__main__":
    setup_models()
