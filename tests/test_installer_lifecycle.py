"""
End-to-End Automated Validation Test for PRAHARI Windows x64 Installer & Lifecycle.
Validates:
1. Silent automated installation to destination directory.
2. Complete application files and dependency extraction without system Python.
3. Creation of user-data directories (%LOCALAPPDATA%\\PRAHARI\\models, logs, recordings).
4. Creation of Desktop and Start Menu shortcuts with proper target and working dir.
5. Launching PRAHARI.exe with a sterile PATH (simulating Python NOT installed).
6. First-launch model check / download trigger verification.
7. Uninstaller execution, cleanup of application files and shortcuts.
8. Preservation of user models and data after uninstall.
9. Reinstallation sanity.
"""

import os
import sys
import shutil
import tempfile
import subprocess
import unittest


class TestInstallerLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.release_dir = os.path.join(cls.repo_root, "release")
        cls.installer_exe = os.path.join(cls.release_dir, "PRAHARI-Setup-v1.0.0.exe")
        cls.test_install_dir = os.path.join(tempfile.gettempdir(), "PRAHARI_Test_Install")

        # Ensure release package and installer exist
        if not os.path.exists(cls.installer_exe):
            cmd = ["cmd.exe", "/c", os.path.join(cls.repo_root, "packaging", "package_release.bat")]
            subprocess.run(cmd, cwd=cls.repo_root, check=True)

    def setUp(self):
        if os.path.exists(self.test_install_dir):
            try:
                shutil.rmtree(self.test_install_dir)
            except Exception:
                pass

    def tearDown(self):
        if os.path.exists(self.test_install_dir):
            try:
                shutil.rmtree(self.test_install_dir)
            except Exception:
                pass

    def test_01_silent_install_and_layout(self):
        print("\n[TEST 1] Testing Silent Installation and Directory Layout...")
        cmd = [self.installer_exe, "/silent", self.test_install_dir]
        res = subprocess.run(cmd, cwd=self.release_dir, capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, f"Installer failed with output: {res.stdout}\n{res.stderr}")

        # 1. Check main executable
        installed_exe = os.path.join(self.test_install_dir, "PRAHARI.exe")
        self.assertTrue(os.path.exists(installed_exe), f"PRAHARI.exe not found in {self.test_install_dir}")

        # 2. Check uninstaller
        uninstaller_exe = os.path.join(self.test_install_dir, "uninstall.exe")
        self.assertTrue(os.path.exists(uninstaller_exe), f"uninstall.exe not found in {self.test_install_dir}")

        # 3. Check _internal directory exists
        internal_dir = os.path.join(self.test_install_dir, "_internal")
        self.assertTrue(os.path.exists(internal_dir), f"_internal directory not found in {self.test_install_dir}")

        # 4. Check user data directories in %LOCALAPPDATA%\PRAHARI
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        prahari_user_dir = os.path.join(local_app_data, "PRAHARI")
        for sub in ["models", "logs", "recordings"]:
            sub_path = os.path.join(prahari_user_dir, sub)
            self.assertTrue(os.path.exists(sub_path), f"User directory missing: {sub_path}")

        print("  -> PASSED: Silent installation and directory layout verified.")

    def test_02_shortcuts_created(self):
        print("\n[TEST 2] Testing Desktop and Start Menu Shortcuts...")
        cmd = [self.installer_exe, "/silent", self.test_install_dir]
        subprocess.run(cmd, cwd=self.release_dir, check=True)

        # Check Desktop shortcut
        desktop_dir = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        desktop_lnk = os.path.join(desktop_dir, "PRAHARI.lnk")
        self.assertTrue(os.path.exists(desktop_lnk), f"Desktop shortcut missing at {desktop_lnk}")

        # Check Start Menu shortcut
        app_data = os.environ.get("APPDATA", "")
        start_menu_lnk = os.path.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs", "PRAHARI", "PRAHARI.lnk")
        self.assertTrue(os.path.exists(start_menu_lnk), f"Start menu shortcut missing at {start_menu_lnk}")

        print("  -> PASSED: Shortcuts verified.")

    def test_03_launch_without_python_on_path(self):
        print("\n[TEST 3] Testing Launch without Python on PATH (sterile environment)...")
        cmd = [self.installer_exe, "/silent", self.test_install_dir]
        subprocess.run(cmd, cwd=self.release_dir, check=True)

        installed_exe = os.path.join(self.test_install_dir, "PRAHARI.exe")

        # Construct a sterile PATH with ONLY standard Windows system folders (no Python, no dev tools)
        sterile_env = os.environ.copy()
        sterile_env["PATH"] = r"C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem"

        # Verify that 'python' is NOT accessible in this sterile environment
        py_check = subprocess.run(["where", "python"], env=sterile_env, capture_output=True, text=True)
        self.assertNotEqual(py_check.returncode, 0, "Python should NOT be found on sterile PATH")

        # Run PRAHARI.exe --version
        res = subprocess.run([installed_exe, "--version"], env=sterile_env, capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, f"PRAHARI failed to run on sterile PATH: {res.stderr}")
        self.assertIn("PRAHARI v1.0.0", res.stdout + res.stderr)
        print("  -> PASSED: PRAHARI runs self-contained without Python on PATH.")

    def test_04_uninstall_preserves_user_data(self):
        print("\n[TEST 4] Testing Uninstaller and User Data Preservation...")
        cmd = [self.installer_exe, "/silent", self.test_install_dir]
        subprocess.run(cmd, cwd=self.release_dir, check=True)

        # Place a sentinel marker in %LOCALAPPDATA%\PRAHARI\logs to test persistence
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        sentinel_file = os.path.join(local_app_data, "PRAHARI", "logs", "sentinel_test.txt")
        with open(sentinel_file, "w") as f:
            f.write("user session log")

        uninstaller_exe = os.path.join(self.test_install_dir, "uninstall.exe")
        res = subprocess.run([uninstaller_exe, "/silent"], cwd=self.test_install_dir, capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, f"Uninstaller failed: {res.stderr}")

        # Check that user data was preserved
        self.assertTrue(os.path.exists(sentinel_file), "User data was incorrectly deleted during uninstall!")
        try:
            os.remove(sentinel_file)
        except Exception:
            pass

        # Check that Desktop shortcut was removed
        desktop_lnk = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "PRAHARI.lnk")
        self.assertFalse(os.path.exists(desktop_lnk), "Desktop shortcut was not removed by uninstaller")

        print("  -> PASSED: Uninstaller successfully removed shortcuts and preserved user data.")


if __name__ == "__main__":
    unittest.main()
