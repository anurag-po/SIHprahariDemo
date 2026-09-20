# -*- mode: python ; coding: utf-8 -*-
# PyInstaller Spec for PRAHARI HAR Space Experiment Assistant (Windows x64 onedir)

import sys
import os

block_cipher = None

repo_root = os.path.abspath(os.path.join(SPECPATH, ".."))
src_dir = os.path.join(repo_root, "src")
models_dir = os.path.join(repo_root, "models")
config_dir = os.path.join(repo_root, "config")

datas = []
if os.path.exists(models_dir):
    datas.append((models_dir, 'models'))
if os.path.exists(config_dir):
    datas.append((config_dir, 'config'))

hiddenimports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'cv2',
    'numpy',
    'ultralytics',
    'mediapipe',
    'pyttsx3',
    'pyttsx3.drivers',
    'pyttsx3.drivers.sapi5',
    'pythoncom',
    'win32com',
    'win32com.client',
    'paths',
    'version',
    'capture',
    'perception',
    'object_tracker',
    'risk_engine',
    'scorer',
    'verifier',
    'voice',
    'logger',
    'validator',
    'streamer',
    'gui',
]

a = Analysis(
    [os.path.join(src_dir, 'main.py')],
    pathex=[src_dir, repo_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PRAHARI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # Keeps terminal for live diagnostic/status streaming alongside GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PRAHARI',
)
