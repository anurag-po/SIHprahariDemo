# PRAHARI

**AI-Based Human Activity Recognition (HAR) System for On-Board Space Experiment Assistance**

PRAHARI is an offline, edge-running computer vision desktop application designed to assist operators performing multi-step physical experiments (such as space payload rack procedures).

---

## Key Features

- **Offline Perception Pipeline**: Powered by Ultralytics YOLO and MediaPipe Hand Landmarkers running in real-time.
- **Multi-Object & Human Tracking**: Detects experimental components (`breadboard`, `resistor`, `led`, `wires`, `battery`, `glove`) as well as human operators (`human`), hands (`hand`), writing tools (`pen`), and devices (`phone`).
- **Deterministic Sequence Validation**: Evaluates actions against a pre-configured step dependency graph defined in JSON.
- **Voice Guidance & Out-of-Sequence Alerts**: Local text-to-speech (`pyttsx3`) alerts operators if steps are skipped or conducted out of order.
- **Dual Video Output**: Concurrently writes an MP4 local recording to disk and streams low-latency video via UDP/RTSP (`ffmpeg`).
- **Single-Window GUI**: Built with PyQt6, featuring video overlays, current status banners, and a live structured event log.
- **Structured Audit Logging**: Emits JSON Lines (`.jsonl`) records for every completed action and session summary.

---

## Directory Structure

```text
PRAHARI/
├── config/
│   └── led_circuit_continuity_test.json   # Step sequence definition & ROIs
├── models/
│   ├── yolov8n.pt                         # Pretrained / fine-tuned detector weights
│   └── hand_landmarker.task               # MediaPipe hand landmarks bundle
├── src/
│   ├── capture.py                         # Asynchronous webcam capture thread
│   ├── download_models.py                 # Automatic model weight downloader
│   ├── gui.py                             # PyQt6 desktop application
│   ├── logger.py                          # Structured JSON Lines session logger
│   ├── object_tracker.py                  # Interaction micro-FSM (in_hand, stationary, in_roi)
│   ├── perception.py                      # YOLO + MediaPipe inference layer
│   ├── streamer.py                        # Local MP4 writer + UDP ffmpeg streamer
│   ├── validator.py                       # Experiment sequence validation FSM
│   ├── voice.py                           # Threaded offline TTS alert system
│   └── main.py                            # Application entry point
├── logs/                                  # Timestamped session logs (.jsonl)
├── recordings/                            # Session video recordings (.mp4)
├── HAR-Space-Experiment-Assistant-PRD.md  # Detailed system PRD
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Download Model Weights
```powershell
python src/download_models.py
```

### 3. Run the Application

**Run with the Everyday Desk Objects Experiment (No electronics purchase needed):**
```powershell
python src/main.py
```
*(Uses everyday items: Book/Notebook, Phone, Pen, Cup/Bottle, and Operator presence).*

**Run with the Breadboard/Circuit Experiment (from PRD):**
```powershell
python src/main.py --config config/led_circuit_continuity_test.json
```

---

## Network Stream (Optional)

To view the live network stream from another device or locally via VLC:
1. Open **VLC Media Player**.
2. Navigate to **Media** > **Open Network Stream...**
3. Enter: `udp://@:5000`
4. Click **Play**.
