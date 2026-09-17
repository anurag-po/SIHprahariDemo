"""
High-Reliability Multi-Backend Voice Assistant for PRAHARI HAR Assistant.
Uses native Windows SAPI / pyttsx3 on a dedicated worker thread with COM apartment initialization.
Guarantees continuous speech output across all procedure steps, warnings, and alerts without hanging.
"""

import os
import sys
import threading
import queue
import time
import subprocess
from typing import Optional, Dict, Any


class VoiceAssistant:
    def __init__(self, rate: int = 175, volume: float = 1.0, enabled: bool = True):
        self.enabled = enabled
        self.rate = rate
        self.volume = volume
        self.msg_queue: queue.Queue = queue.Queue()
        self.running = True
        self.last_warning_key: Optional[str] = None
        self.last_warning_time: float = 0.0
        self.warning_cooldown: float = 4.0

        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        sapi_voice = None
        has_com = False

        # Try initializing Windows Native SAPI voice with COM initialization on this worker thread
        if sys.platform == "win32" and self.enabled:
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                has_com = True
                sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
                # SAPI rate ranges from -10 to 10 (default 0). Map 175 wpm -> rate 0..1
                sapi_rate = max(-10, min(10, int((self.rate - 150) / 25)))
                sapi_voice.Rate = sapi_rate
                sapi_voice.Volume = int(self.volume * 100)
            except Exception as e:
                print(f"[VoiceAssistant] Native SAPI init note: {e}. Trying pyttsx3 fallback.")
                sapi_voice = None

        # Fallback to pyttsx3 if SAPI direct is not available
        pyttsx_engine = None
        if sapi_voice is None and self.enabled:
            try:
                import pyttsx3
                pyttsx_engine = pyttsx3.init()
                pyttsx_engine.setProperty("rate", self.rate)
                pyttsx_engine.setProperty("volume", self.volume)
            except Exception as e:
                print(f"[VoiceAssistant] pyttsx3 init note: {e}.")
                pyttsx_engine = None

        while self.running:
            try:
                msg_type, text = self.msg_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if not self.enabled or not text:
                self.msg_queue.task_done()
                continue

            print(f"[VOICE - {msg_type.upper()}]: {text}")

            spoken_success = False

            # 1. Try Windows SAPI Direct
            if sapi_voice is not None:
                try:
                    sapi_voice.Speak(text)
                    spoken_success = True
                except Exception as e:
                    print(f"[VoiceAssistant] SAPI Speak error: {e}")

            # 2. Try pyttsx3 Engine
            if not spoken_success and pyttsx_engine is not None:
                try:
                    pyttsx_engine.say(text)
                    pyttsx_engine.runAndWait()
                    spoken_success = True
                except Exception as e:
                    print(f"[VoiceAssistant] pyttsx3 Speak error: {e}")

            # 3. Try PowerShell System.Speech fallback on Windows
            if not spoken_success and sys.platform == "win32":
                try:
                    clean_text = text.replace("'", " ").replace('"', " ")
                    ps_cmd = (
                        f"Add-Type -AssemblyName System.Speech; "
                        f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$synth.Speak('{clean_text}')"
                    )
                    subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5.0,
                    )
                    spoken_success = True
                except Exception:
                    pass

            self.msg_queue.task_done()

        if has_com:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def say_guidance(self, text: str):
        """Standard procedural instruction (normal priority)."""
        self.msg_queue.put(("guidance", text))

    def say_alert(self, text_or_payload: Any):
        """Immediate out-of-sequence or sequence violation alert."""
        if isinstance(text_or_payload, dict):
            expected = text_or_payload.get("expected", "")
            detected = text_or_payload.get("detected", "")
            rec = text_or_payload.get("recommended_action", "")
            spoken = f"Alert. Detected: {detected}. Expected: {expected}. {rec}"
        else:
            spoken = f"Alert. {text_or_payload}"

        self.msg_queue.put(("alert", spoken))

    def say_predictive_warning(self, target_roi: str, step_name: str, episode_id: Optional[str] = None):
        """
        Predictive error warning before physical contact.
        Rate-limited to 1 per episode.
        """
        now = time.time()
        key = episode_id or f"{step_name}->{target_roi}"
        if key == self.last_warning_key and (now - self.last_warning_time) < self.warning_cooldown:
            return  # Rate-limited

        self.last_warning_key = key
        self.last_warning_time = now
        spoken = f"Caution. Hand approaching {target_roi.replace('_', ' ')}. Required step is {step_name.replace('_', ' ')}."
        self.msg_queue.put(("predictive_warning", spoken))

    def reset_warning_lock(self):
        self.last_warning_key = None

    def stop(self):
        self.running = False
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
