# PRAHARI Release Notes — v1.0.0

**Release Tag**: `v1.0.0`  
**Release Date**: September 2026  
**Target Platform**: Windows 10 / Windows 11 (64-bit x64)

---

## 🌟 What's New in v1.0.0

### 1. Dedicated Camera Source Selection
- **📹 Web Camera**: Instant 1-click switching to local USB webcams and built-in cameras (device index 0, 1, ...).
- **🌐 IP / RTSP Camera**: Live streaming over network cameras (RTSP, HTTP MJPEG, and snapshot endpoints) with automatic reconnect.
- **📱 Mobile Phone Bridge**: In-process zero-install browser camera uplink on port 8000 with phone lens switching, rotation, and pause/resume controls.

### 2. Standalone Windows Desktop Distribution
- **Zero-Dependency Portable Build**: Runs out of the box on any clean 64-bit Windows PC without requiring Python, pip, Visual Studio, or dev tools.
- **Native Bootstrapper Installer (`PRAHARI-Setup-v1.0.0.exe`)**: 
  - Automated package integrity verification (SHA-256).
  - Per-user extraction to `%LOCALAPPDATA%\Programs\PRAHARI`.
  - Desktop and Start Menu shortcut generation.
  - Finish screen with 1-click "Launch PRAHARI" option.

### 3. Core Vision & Procedural Assistance Engine
- **Ultralytics YOLOv8 & MediaPipe Hands**: Real-time object detection and hand landmarking tracking workspace ROIs.
- **Predictive Error Prevention**: Trajectory forecasting predicting incorrect ROI contacts before they happen.
- **Explainable Alerts & Confidence Gating**: 3-tier confidence gating with structured diagnostic alert payloads.
- **Procedure-Quality Scoring**: Live composite performance index measuring accuracy, execution speed, and cleanliness.
- **Voice Guidance & Rate-Limited Alerts**: Single-shot step recitation and debounced voice warnings.
- **Structured Audit Logging & Session Recording**: Emits JSONL records and MP4 session recordings to `%LOCALAPPDATA%\PRAHARI\`.

---

## 📦 Release Assets & Checksums

| Asset File | Size | Description | SHA-256 Hash |
| :--- | :--- | :--- | :--- |
| **`PRAHARI-Setup-v1.0.0.exe`** | ~19 KB | Native Windows Installer Bootstrapper | *(Compiled binary)* |
| **`PRAHARI-v1.0.0-Windows-x64.zip`** | ~306 MB | Self-Contained Portable Application Archive | `74b84533cff79f22760b5dc07f4488f73fae529a7a14a472cf3207c1f2b0b42d` |
| **`SHA256SUMS.txt`** | ~100 B | Cryptographic SHA-256 Checksum List | — |

---

## 🚀 Installation & Usage

### Method 1: Windows Installer (Recommended)
1. Download and run **`PRAHARI-Setup-v1.0.0.exe`**.
2. Click **Install PRAHARI**.
3. Launch from Desktop shortcut or Start Menu.

### Method 2: Portable ZIP
1. Download and extract **`PRAHARI-v1.0.0-Windows-x64.zip`**.
2. Run **`PRAHARI.exe`**.
