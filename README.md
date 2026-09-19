# PRAHARI

**AI-Based Human Activity Recognition (HAR) System for On-Board Space Experiment Assistance**

PRAHARI is an offline, edge-running computer vision desktop application designed to assist operators performing multi-step physical experiments (such as space payload rack procedures).

---

## 🚀 Quick Setup & Installation (End-User)

### Option A: One-Click Windows Installer (Recommended)
1. Download **`PRAHARI-Setup-v1.0.0.exe`** from the `release/` folder or [Releases](https://github.com/anurag-po/SIHprahariDemo/releases).
2. Double-click **`PRAHARI-Setup-v1.0.0.exe`**.
3. Choose your desired install location (default: `%LOCALAPPDATA%\Programs\PRAHARI`).
4. Click **Install PRAHARI**. The installer will automatically:
   - Extract the complete standalone package.
   - Register Desktop & Start Menu shortcuts.
   - Verify package integrity (SHA-256).
5. Check **Launch PRAHARI after installation** and click **Finish**.
> **Note:** The installed application runs 100% standalone on any clean 64-bit Windows machine without requiring Python, pip, or Visual Studio.

### Option B: Portable Standalone ZIP (Zero-Install)
1. Download **`PRAHARI-v1.0.0-Windows-x64.zip`** from the `release/` folder.
2. Extract the ZIP archive anywhere on your system.
3. Double-click **`PRAHARI.exe`** to launch directly.

---

## 📹 Camera & Vision Input Selection

PRAHARI features a dedicated **Camera Source Selection Panel** right in the desktop application:

| Camera Mode | Button | Description |
| :--- | :--- | :--- |
| **Local USB Webcam** | `📹 Web Camera` | Connects instantly to your built-in webcam or external USB camera (device index 0, 1, ...). |
| **Network IP Camera** | `🌐 IP Camera` | Connects to an RTSP, HTTP MJPEG, or snapshot stream (e.g. `http://192.168.1.50:8080/video` or `rtsp://...`). |
| **Mobile Phone Bridge** | `📱 Mobile Phone Bridge` | Starts an in-process zero-install web server on port 8000. Open the displayed URL (`http://<LAN-IP>:8000`) on your phone's Chrome browser to stream live video directly to PRAHARI. |

### Stream Controls:
- **Flip Camera (Mirror)**: Horizontally flip camera video.
- **Rotate Selector**: 0°, 90°, 180°, 270° orientation adjustments for phone or mounted webcams.
- **🔊 Recite Step**: Single-shot voice prompt recitation of the current active protocol step.
- **⏭ Advance Step**: Manual override or spacebar trigger for workflow testing.

---

## 🛠 Developer & Source Workflow

### 1. Requirements & Installation
```powershell
pip install -r requirements.txt
```

### 2. Run Automated Tests
```powershell
python tests/test_capture_ip.py
python tests/test_prahari_upgrade.py
```

### 3. Launch from Source
```powershell
# Default experiment (Everyday Desk Objects)
python src/main.py --config config/desk_objects_experiment.json

# LED Circuit Continuity Test
python src/main.py --config config/led_circuit_continuity_test.json

# Headless mode (no GUI)
python src/main.py --headless --no-voice
```

### 4. Build Standalone Distribution & Packages
```powershell
# Build PyInstaller onedir distribution (dist/PRAHARI/PRAHARI.exe)
.\packaging\build_windows.bat

# Package portable ZIP release & generate SHA256SUMS.txt (release/)
.\packaging\package_release.bat

# Compile native Windows bootstrapper installer (release/PRAHARI-Setup-v1.0.0.exe)
.\packaging\build_installer.bat
```

---

## 📁 Repository Structure

```text
SIHprahariDemo/
├── config/
│   ├── desk_objects_experiment.json       # Desk objects experiment sequence & ROIs
│   └── led_circuit_continuity_test.json   # LED breadboard circuit experiment
├── models/
│   └── yolov8n.pt                         # Bundled YOLOv8 object detector weights
├── src/
│   ├── capture.py                         # USB, RTSP IP, & Mobile Browser Bridge capture engine
│   ├── download_models.py                 # Automatic model weight resolver
│   ├── gui.py                             # PyQt6 dark-theme desktop interface & camera selectors
│   ├── logger.py                          # Structured JSONL session & audit logger
│   ├── main.py                            # Main application pipeline orchestrator
│   ├── object_tracker.py                  # Hand & object interaction tracker
│   ├── paths.py                           # Centralized runtime path abstraction
│   ├── perception.py                      # YOLOv8 + MediaPipe perception engine
│   ├── risk_engine.py                     # Predictive trajectory forecasting & risk calculator
│   ├── scorer.py                          # Procedure quality score index
│   ├── streamer.py                        # Dual local MP4 recorder + UDP streamer
│   ├── validator.py                       # Deterministic state-machine sequence validator
│   ├── verifier.py                        # Multi-modal outcome verification engine
│   └── voice.py                           # Threaded Windows SAPI & pyttsx3 voice engine
├── packaging/
│   ├── PRAHARI.spec                       # PyInstaller packaging specification
│   ├── build_windows.bat                  # PyInstaller executable builder
│   ├── package_release.bat                # Portable ZIP & SHA-256 generator
│   ├── build_installer.bat                # csc.exe C# installer compiler
│   └── installer/
│       └── PRAHARI_Setup.cs               # Native WinForms installer source
├── tests/
│   ├── test_capture_ip.py                 # Camera engine test suite
│   └── test_prahari_upgrade.py            # Sequence, risk engine & verification test suite
├── tools/
│   └── failure_injector.py                # Digital Twin failure injection harness
├── release/                               # Distributable installer and ZIP releases
│   ├── PRAHARI-Setup-v1.0.0.exe           # Native Windows Installer
│   ├── PRAHARI-v1.0.0-Windows-x64.zip     # Portable Standalone Archive
│   └── SHA256SUMS.txt                     # Cryptographic checksums
├── requirements.txt
└── README.md
```

---

## 🔒 Security & Data Paths

When running the packaged application:
- **Application Binaries & Assets**: Contained in the install directory (`%LOCALAPPDATA%\Programs\PRAHARI`).
- **Audit Logs**: Stored under `%LOCALAPPDATA%\PRAHARI\logs\`.
- **Session MP4 Recordings**: Stored under `%LOCALAPPDATA%\PRAHARI\recordings\`.
