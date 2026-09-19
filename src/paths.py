"""
Centralized path resolution for PRAHARI HAR Assistant.
Handles path routing for both frozen PyInstaller environments and development environments.
User-writable data (logs, recordings) -> %LOCALAPPDATA%\\PRAHARI (Windows) or ~/.prahari
Read-only assets (models, config) -> Bundle / App Directory
"""

import os
import sys
from typing import Optional


def get_app_root() -> str:
    """
    Returns the root directory where application executables and bundled assets reside.
    If frozen via PyInstaller onedir/onefile, points to sys._MEIPASS or executable directory.
    """
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return sys._MEIPASS
        return os.path.dirname(os.path.abspath(sys.executable))
    # Running from source (src/ is one level below project root)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(src_dir, ".."))


def get_user_data_dir() -> str:
    """
    Returns the user-writable data directory (%LOCALAPPDATA%\\PRAHARI on Windows).
    Ensures directory exists.
    """
    if os.name == "nt":
        base_dir = os.environ.get("LOCALAPPDATA")
        if not base_dir:
            base_dir = os.path.expanduser("~")
        data_dir = os.path.join(base_dir, "PRAHARI")
    else:
        data_dir = os.path.join(os.path.expanduser("~"), ".prahari")

    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_logs_dir() -> str:
    """Returns path to the user-writable logs directory."""
    logs_path = os.path.join(get_user_data_dir(), "logs")
    os.makedirs(logs_path, exist_ok=True)
    return logs_path


def get_recordings_dir() -> str:
    """Returns path to the user-writable MP4 recordings directory."""
    rec_path = os.path.join(get_user_data_dir(), "recordings")
    os.makedirs(rec_path, exist_ok=True)
    return rec_path


def resolve_asset_path(relative_path: str) -> str:
    """
    Resolves an asset file path (e.g. 'models/yolov8n.pt', 'config/desk_objects_experiment.json').
    Checks app root first, then current working directory.
    """
    app_root = get_app_root()
    candidate = os.path.join(app_root, relative_path)
    if os.path.exists(candidate):
        return os.path.abspath(candidate)

    # Fallback to CWD
    if os.path.exists(relative_path):
        return os.path.abspath(relative_path)

    return os.path.abspath(candidate)
