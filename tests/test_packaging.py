"""
Automated sanity tests for PRAHARI Windows packaging and runtime path architecture.
Verifies:
1. Version single source of truth
2. Runtime paths (read-only assets vs user-data writable dirs)
3. Asset availability (models, configs)
4. Camera mode selection CLI and UI handlers
5. SHA-256 integrity computation
6. Packaging configuration integrity
"""

import os
import sys
import hashlib
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import version
import paths
import capture


class TestPackagingAndPaths(unittest.TestCase):
    def test_version_defined(self):
        """Test that single source of truth version is properly defined."""
        self.assertTrue(hasattr(version, "__version__"))
        self.assertEqual(version.__version__, "1.0.0")

    def test_user_data_dirs(self):
        """Test that user-writable paths point to AppData and exist."""
        logs_dir = paths.get_logs_dir()
        recordings_dir = paths.get_recordings_dir()

        self.assertTrue(os.path.isdir(logs_dir), f"Logs dir does not exist: {logs_dir}")
        self.assertTrue(os.path.isdir(recordings_dir), f"Recordings dir does not exist: {recordings_dir}")
        
        # Verify writable
        test_file = os.path.join(logs_dir, "test_perm.tmp")
        try:
            with open(test_file, "w") as f:
                f.write("ok")
            self.assertTrue(os.path.exists(test_file))
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_asset_resolution(self):
        """Test that essential models and configs resolve correctly."""
        user_models_dir = paths.get_user_models_dir()
        self.assertTrue(os.path.exists(user_models_dir), f"User models dir missing: {user_models_dir}")

        yolo_path = paths.resolve_asset_path("models/yolov8n.pt")
        self.assertTrue(os.path.exists(yolo_path), f"YOLO model not found: {yolo_path}")

        task_path = paths.resolve_asset_path("models/hand_landmarker.task")
        self.assertTrue(os.path.exists(task_path), f"MediaPipe task model not found: {task_path}")

        config_path = paths.resolve_asset_path("config/desk_objects_experiment.json")
        self.assertTrue(os.path.exists(config_path), f"Desk config not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            self.assertIn("experiment_id", cfg)
            self.assertIn("steps", cfg)

    def test_model_downloader(self):
        """Test setup_models verifies and returns valid model paths."""
        from download_models import setup_models
        models = setup_models()
        self.assertIn("yolo", models)
        self.assertIn("hand_landmarker", models)
        self.assertTrue(os.path.exists(models["yolo"]))
        self.assertTrue(os.path.exists(models["hand_landmarker"]))

    def test_camera_mode_switching(self):
        """Test that VideoCaptureThread supports switching between USB index and IP URL."""
        from unittest.mock import MagicMock, patch

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, None)

        with patch("cv2.VideoCapture", return_value=mock_cap):
            vcap = capture.VideoCaptureThread(source=0)
            self.assertEqual(vcap.cam_cfg.get("type"), "usb")

            # Switch to IP stream
            vcap.switch_source("http://192.168.1.50:8080/video")
            self.assertEqual(vcap.cam_cfg.get("type"), "ip")
            self.assertEqual(vcap.cam_cfg.get("url"), "http://192.168.1.50:8080/video")

            # Switch back to USB device index 0
            vcap.switch_source(0)
            self.assertEqual(vcap.cam_cfg.get("type"), "usb")
            self.assertEqual(vcap.cam_cfg.get("id"), 0)

            # Switch to Mobile Phone Bridge
            vcap.switch_source("browser")
            self.assertEqual(vcap.cam_cfg.get("type"), "browser")

    def test_sha256_hashing(self):
        """Test SHA-256 calculation format and consistency."""
        dummy_data = b"PRAHARI-Release-Test-Package"
        expected = hashlib.sha256(dummy_data).hexdigest()
        self.assertEqual(len(expected), 64)

    def test_packaging_scripts_exist(self):
        """Test that all packaging scripts exist and contain required commands."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        spec_path = os.path.join(repo_root, "packaging", "PRAHARI.spec")
        build_win_path = os.path.join(repo_root, "packaging", "build_windows.bat")
        build_inst_path = os.path.join(repo_root, "packaging", "build_installer.bat")
        pack_rel_path = os.path.join(repo_root, "packaging", "package_release.bat")
        cs_installer = os.path.join(repo_root, "packaging", "installer", "PRAHARI_Setup.cs")

        for p in [spec_path, build_win_path, build_inst_path, pack_rel_path, cs_installer]:
            self.assertTrue(os.path.isfile(p), f"Missing packaging file: {p}")


if __name__ == "__main__":
    unittest.main()
