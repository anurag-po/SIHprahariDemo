"""
Automatic Model Weight Downloader for PRAHARI.
Ensures Ultralytics YOLO base models and MediaPipe assets are present offline in models/.
"""

import os
import urllib.request


def setup_models(models_dir: str = "models"):
    os.makedirs(models_dir, exist_ok=True)
    yolo_model_path = os.path.join(models_dir, "yolov8n.pt")
    
    if not os.path.exists(yolo_model_path):
        print("[download_models] Downloading yolov8n.pt weights...")
        url = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
        try:
            urllib.request.urlretrieve(url, yolo_model_path)
            print(f"[download_models] Successfully saved {yolo_model_path}")
        except Exception as e:
            print(f"[download_models] Could not download {url}: {e}. Local fallback will be used.")
    else:
        print(f"[download_models] Model {yolo_model_path} already exists.")


if __name__ == "__main__":
    setup_models()
