# PRAHARI

**AI-Based Human Activity Recognition (HAR) System for On-Board Space Experiment Assistance**

PRAHARI is an offline, edge-running computer vision desktop application designed to assist operators performing multi-step physical experiments (such as space payload rack procedures).

> **Note:** If the Mobile Phone Bridge camera source isn't connecting, see [If Mobile Bridge isn't working](#if-mobile-bridge-isnt-working) at the bottom of this README for a step-by-step fix.

---

## Table of Contents
- [How to Run the Project Using Git Clone (Quickstart)](#how-to-run-the-project-using-git-clone-quickstart)
- [Camera & Vision Input Selection](#camera--vision-input-selection)
- [Accessing an IP Camera](#accessing-an-ip-camera)
- [Developer & Source Workflow](#developer--source-workflow)
- [Repository Structure](#repository-structure)
- [Security & Data Paths](#security--data-paths)
- [If Mobile Bridge isn't working](#if-mobile-bridge-isnt-working)

---

## How to Run the Project Using Git Clone (Quickstart)

Follow these simple steps to clone, set up, and run PRAHARI directly from source:

### Step 1: Clone the Repository
```bash
git clone https://github.com/anurag-po/SIHprahariDemo.git
cd SIHprahariDemo
```

### Step 2: Set Up Python Environment & Install Dependencies
*(Python 3.10+ recommended)*
```bash
# Optional: create & activate a virtual environment
python -m venv venv

# Activate on Windows:
venv\Scripts\activate
# Or on Linux / macOS:
source venv/bin/activate

# Upgrade pip and install required dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Run the Application

You can launch PRAHARI using any of the following convenient options:

#### Option A: 1-Click Automated Setup (Windows)
Double-click **`setup.bat`** or execute:
```powershell
.\setup.bat
```
*(This verifies dependencies, model weights, and launches PRAHARI automatically).*

#### Option B: 1-Click Batch Launcher (Windows)
Double-click **`run_prahari.bat`** or execute:
```powershell
.\run_prahari.bat
```

#### Option C: Direct Python Command
```bash
# Launch PRAHARI Desktop GUI (Everyday Desk Objects Protocol)
python src/main.py --config config/desk_objects_experiment.json

# Launch with an IP Camera stream
python src/main.py --camera-type ip --ip-url http://192.168.1.50:8080/video

# Launch in Headless Console Mode (No GUI)
python src/main.py --headless --no-voice
```

---

## Camera & Vision Input Selection

PRAHARI features a dedicated **Camera Source Selection Panel** right in the desktop application:

| Camera Mode | Button | Description |
| :--- | :--- | :--- |
| **Local USB Webcam** | `Web Camera` | Connects instantly to your built-in webcam or external USB camera (device index 0, 1, ...). |
| **Network IP Camera** | `IP Camera` | Connects to an RTSP, HTTP MJPEG, or snapshot stream (e.g. `http://192.168.1.50:8080/video` or `rtsp://...`). |
| **Mobile Phone Bridge** | `Mobile Phone Bridge` | Starts an in-process zero-install web server on port 8000. Open the displayed URL (`http://<LAN-IP>:8000`) on your phone's Chrome browser to stream live video directly to PRAHARI. |

### Stream Controls:
- **Flip Camera (Mirror)**: Horizontally flip camera video.
- **Rotate Selector**: 0°, 90°, 180°, 270° orientation adjustments for phone or mounted webcams.
- **Recite Step**: Single-shot voice prompt recitation of the current active protocol step.
- **Advance Step**: Manual override or spacebar trigger for workflow testing.

---

## Accessing an IP Camera

If you're streaming from a dedicated IP camera, a networked CCTV unit, or an IP-camera app on a phone (instead of the Mobile Phone Bridge), you can feed that stream straight into PRAHARI using its feed link.

### Step 1: Find your camera's feed URL
Most IP cameras and IP-camera apps expose a live feed URL once they're running, usually in one of these formats:
- **HTTP MJPEG stream**: `http://192.168.1.50:8080/video`
- **HTTP snapshot stream**: `http://192.168.1.50:8080/shot.jpg`
- **RTSP stream**: `rtsp://192.168.1.50:8554/live`

This URL is normally shown on the camera's own status page or app screen. Make sure the camera and the computer running PRAHARI are on the same local network (Wi-Fi/LAN).

### Step 2: Enter it into PRAHARI
1. Launch PRAHARI and open the **Camera Source Selection Panel**.
2. Click the **`IP Camera`** button.
3. An input bar will appear — paste the full feed URL from Step 1 into this bar.
4. Press **Enter** (or click **Connect**) to start the stream.

You can also skip the GUI and pass the URL directly at launch:
```bash
python src/main.py --camera-type ip --ip-url http://192.168.1.50:8080/video
```

### Tips
- Always include the scheme (`http://` or `rtsp://`) and the port number exactly as shown by the camera or app.
- If the stream doesn't connect, confirm the camera and computer are on the same network and that no firewall is blocking the port.
- Use the **Rotate Selector** and **Flip Camera** controls (see above) if the feed appears sideways or mirrored.

---

## Developer & Source Workflow

### 1. Run Automated Tests
```powershell
python tests/test_capture_ip.py
python tests/test_prahari_upgrade.py
python tests/test_packaging.py
```

### 2. Build Standalone Distribution & Packages
```powershell
# Build PyInstaller onedir distribution (dist/PRAHARI/PRAHARI.exe)
.\packaging\build_windows.bat

# Package portable ZIP release & generate SHA256SUMS.txt (release/)
.\packaging\package_release.bat

# Compile native Windows bootstrapper installer (release/PRAHARI-Setup-v1.0.0.exe)
.\packaging\build_installer.bat
```

---

## Repository Structure

```text
SIHprahariDemo/
├── config/
│   ├── desk_objects_experiment.json       # Mission protocol sequence & ROIs
│   └── led_circuit_continuity_test.json   # Electronics continuity protocol
├── models/
│   ├── yolov8n.pt                         # Bundled YOLOv8 object detector weights
│   └── hand_landmarker.task               # Bundled MediaPipe hand landmarker model
├── src/
│   ├── version.py                         # Single source of truth versioning
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
│   ├── test_prahari_upgrade.py            # Sequence, risk engine & verification test suite
│   └── test_packaging.py                  # Path, packaging & SHA-256 integrity test suite
├── tools/
│   └── failure_injector.py                # Digital Twin failure injection harness
├── run_prahari.bat                        # 1-Click launcher script
├── setup.bat                              # Automated setup and launch script
├── requirements.txt                       # Project Python dependencies
└── README.md
```

---

## Security & Data Paths

When running the application:
- **Application Binaries & Assets**: Loaded from installation/project root (`models/`, `config/`).
- **Audit Logs**: Stored under `%LOCALAPPDATA%\PRAHARI\logs\`.
- **Session MP4 Recordings**: Stored under `%LOCALAPPDATA%\PRAHARI\recordings\`.

---

## If Mobile Bridge isn't working

The Mobile Phone Bridge streams video from your phone's browser to PRAHARI over your local network using a plain `http://` address (not `https://`). Modern versions of Chrome treat camera access on insecure (non-HTTPS) origins as unsafe by default, so your phone may refuse to grant camera permission even though the connection itself is working fine. If the stream won't start, follow these steps:

1. On the phone (or device) you're using to stream, open Chrome and go to:
   ```
   chrome://flags/#unsafely-treat-insecure-origin-as-secure
   ```
2. In the text box for that flag, enter the exact URL shown on the PRAHARI desktop client for the Mobile Phone Bridge (e.g. `http://<LAN-IP>:8000`).
3. Set the flag to **Enabled**, then use the **Relaunch** button that appears to restart Chrome.
4. After Chrome relaunches, go to the same Mobile Phone Bridge URL from the desktop client again.
5. When prompted, **allow camera access** for the page.
6. The live stream should now reach PRAHARI as expected — proceed with your session.

**Important:** This flag disables a browser security protection for the origin you entered. Once you're done with the demonstration or session, go back to `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, reset it to **Default**, and relaunch Chrome to remove the exception.
