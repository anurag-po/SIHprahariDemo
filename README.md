# PRAHARI

**AI-Based Human Activity Recognition (HAR) System for On-Board Space Experiment Assistance**

PRAHARI is an offline, edge-running computer vision desktop application designed to assist operators performing multi-step physical experiments (such as space payload rack procedures).

---

## Key Features

- **Predictive Error Prevention**: Linear trajectory forecasting warns operators before physical contact with incorrect ROIs ($R = P(\text{wrong\_target}) \times \text{severity} \times (1.5 \text{ if irreversible})$).
- **Explainable Alerts & Confidence Gating**: 3-tier confidence gating (High >0.8, Medium 0.5-0.8 confirmation hold, Low <0.5 `UNVERIFIABLE`), emitting structured alert diagnostics.
- **Procedure-Quality Scoring**: Live composite performance index measuring accuracy, execution speed, and cleanliness/near-misses.
- **Multi-Modal Outcome Verification**: Verifies physical experiment outcomes (`vision_only`, `vision+brightness` LED delta, and `vision+mock_sensor` telemetry fusion).
- **Digital Twin Failure Injection Harness**: Offline test harness injecting synthetic occlusions, reordered steps, jitter, and misclassifications to verify system detection benchmarks.
- **Offline Perception Pipeline**: Powered by Ultralytics YOLO and MediaPipe Hand Landmarkers running in real-time on edge CPU/GPU.
- **Deterministic Sequence Validation**: Evaluates actions against a pre-configured step dependency graph defined in JSON.
- **Voice Guidance & Voice Warnings**: Local offline text-to-speech (`pyttsx3`) with guidance, rate-limited predictive warnings, and violation alerts.
- **Dual Video Output**: Concurrently writes an MP4 local recording to disk and streams low-latency video via UDP/RTSP (`ffmpeg`).
- **Single-Window GUI**: Built with PyQt6, featuring video overlays, status banners, score meter, and a live structured event log.
- **Structured Audit Logging**: Emits JSON Lines (`.jsonl`) records for every completed action and session summary.

---

## Directory Structure

```text
PRAHARI/
├── config/
│   ├── led_circuit_continuity_test.json   # Step sequence definition & ROIs (Extended Schema)
│   └── desk_objects_experiment.json       # Everyday desk objects experiment
├── models/
│   ├── yolov8n.pt                         # Pretrained / fine-tuned detector weights
│   └── hand_landmarker.task               # MediaPipe hand landmarks bundle
├── src/
│   ├── capture.py                         # Asynchronous webcam capture thread
│   ├── download_models.py                 # Automatic model weight downloader
│   ├── gui.py                             # PyQt6 desktop application
│   ├── logger.py                          # Structured JSON Lines session logger
│   ├── object_tracker.py                  # Interaction micro-FSM & trajectory tracker
│   ├── perception.py                      # YOLO + MediaPipe inference layer
│   ├── risk_engine.py                     # Predictive error prevention & risk engine
│   ├── scorer.py                          # Procedure-quality scoring engine
│   ├── streamer.py                        # Local MP4 writer + UDP ffmpeg streamer
│   ├── validator.py                       # Experiment sequence validation FSM
│   ├── verifier.py                        # Multi-modal & outcome verifier
│   ├── voice.py                           # Threaded offline TTS alert system
│   └── main.py                            # Application entry point
├── tools/
│   └── failure_injector.py                # Digital Twin failure injection harness
├── tests/
│   └── test_prahari_upgrade.py            # Automated test suite
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

### 2. Run Automated Verification Tests
```powershell
python tests/test_prahari_upgrade.py
```

### 3. Run Digital Twin Benchmark Suite
```powershell
python tools/failure_injector.py
```

### 4. Run the Application

**Run with the Breadboard/Circuit Experiment (PRD & Addendum):**
```powershell
python src/main.py --config config/led_circuit_continuity_test.json
```

**Run with Everyday Desk Objects Experiment:**
```powershell
python src/main.py --config config/desk_objects_experiment.json
```

**Run in Headless Mode (Console Only):**
```powershell
python src/main.py --headless --no-voice
```

---

## Network Stream (Optional)

To view the live network stream from another device or locally via VLC:
1. Open **VLC Media Player**.
2. Navigate to **Media** > **Open Network Stream...**
3. Enter: `udp://@:5000`
4. Click **Play**.
