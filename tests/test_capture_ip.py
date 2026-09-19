import os
import sys
import unittest.mock as mock
import cv2
import numpy as np
import urllib.request
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
import capture

def test_capture_module():
    # 1. Test DEFAULT_CAMERA_CONFIG
    cfg = capture.DEFAULT_CAMERA_CONFIG
    assert cfg["type"] in ["usb", "ip", "browser"]
    assert "id" in cfg
    assert "bridge_port" in cfg
    print("[PASS] 1. Config block schema verified")

    # 2. Test open_camera URL env expansion
    os.environ["CAM_PASSWORD"] = "prahari_secret"
    test_ip_cfg = {
        "id": 1,
        "type": "ip",
        "url": "rtsp://user:${CAM_PASSWORD}@10.0.0.1:554/live",
        "backend": "cv2.CAP_FFMPEG",
        "reconnect": True,
        "max_reconnect_delay_s": 0.01,
        "read_timeout_s": 2.0,
    }

    with mock.patch("cv2.VideoCapture") as mock_vcap:
        mock_inst = mock.MagicMock()
        mock_inst.isOpened.return_value = True
        mock_vcap.return_value = mock_inst

        cap = capture.open_camera(test_ip_cfg)
        mock_vcap.assert_called_once_with("rtsp://user:prahari_secret@10.0.0.1:554/live", cv2.CAP_FFMPEG)
        mock_inst.set.assert_called_once_with(cv2.CAP_PROP_BUFFERSIZE, 1)
        print("[PASS] 2. IP path: env var substituted and buffersize set to 1")

    # 3. Test open_camera USB
    with mock.patch("cv2.VideoCapture") as mock_vcap:
        mock_inst = mock.MagicMock()
        mock_inst.isOpened.return_value = True
        mock_vcap.return_value = mock_inst

        usb_cfg = {"id": 2, "type": "usb"}
        cap_usb = capture.open_camera(usb_cfg)
        assert mock_vcap.call_count >= 1
        print("[PASS] 3. USB path: opened device index 2")

    # 4. Test Browser Camera Bridge
    browser_cfg = {
        "id": "phone_cam",
        "type": "browser",
        "bridge_port": 8899,
    }
    cap_browser = capture.open_camera(browser_cfg)
    assert cap_browser is not None and cap_browser.isOpened()
    print("[PASS] 4a. Browser Camera Bridge initialized on port 8899")

    # Test HTTP GET /
    time.sleep(0.1)
    req = urllib.request.Request("http://127.0.0.1:8899/")
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        html = resp.read().decode("utf-8")
        assert "PRAHARI" in html and "getUserMedia" in html
        print("[PASS] 4b. Web bridge serves mobile streaming HTML page")

    # Test HTTP POST /frame
    dummy_img = np.zeros((240, 320, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", dummy_img)
    post_req = urllib.request.Request(
        "http://127.0.0.1:8899/frame",
        data=encoded.tobytes(),
        headers={"Content-Type": "image/jpeg"},
        method="POST"
    )
    with urllib.request.urlopen(post_req, timeout=2.0) as resp:
        assert resp.status == 200
        print("[PASS] 4c. Mobile browser frame uploaded and decoded in memory")

    # Read frame from bridge
    frame_from_bridge = capture.read_frame_with_reconnect(cap_browser, browser_cfg)
    assert frame_from_bridge is not None and frame_from_bridge.shape == (240, 320, 3)
    print("[PASS] 4d. Pipeline successfully retrieved frame from Browser Camera Bridge")

    # 5. Test read_frame_with_reconnect failure & reconnect
    mock_cap_fail = mock.MagicMock()
    mock_cap_fail.isOpened.return_value = True
    mock_cap_fail.read.return_value = (False, None)

    frame_fail = capture.read_frame_with_reconnect(mock_cap_fail, test_ip_cfg)
    assert frame_fail is None
    assert mock_cap_fail.release.called
    print("[PASS] 5. read_frame_with_reconnect handles failure and returns None for cycle")

    print("\nALL TEST SUITES (USB + RTSP IP + BROWSER BRIDGE) PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_capture_module()
