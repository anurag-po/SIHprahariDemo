"""
Pure Desk Objects Perception Engine for PRAHARI HAR Assistant.
Focuses exclusively on Everyday Desk Objects Protocol:
- Book / Notebook / Logging Journal
- Pen / Pencil / Stylus / Marker
- Bottle / Sample Bottle
- Cup / Mug / Container
- Phone / Mobile Device
- Laptop / Computer Screen
- Mouse / Input Device
- Human Hand (MediaPipe Landmark Tracking & Pinch Grasp Estimation)
- Human Operator (Person)
"""

import os
import math
import time
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np

try:
    from paths import resolve_asset_path
except ImportError:
    resolve_asset_path = lambda p: p


class PerceptionEngine:
    def __init__(
        self,
        model_path: str = "models/yolov8n.pt",
        confidence_threshold: float = 0.15,
    ):
        self.model_path = model_path
        self.conf_threshold = confidence_threshold

        self.yolo_model = None
        self.mp_hands = None
        self.mp_drawing = None

        # Anti-flicker temporal persistence buffer
        self.persistence_buffer: Dict[str, Dict[str, Any]] = {}
        self.persistence_timeout_s = 0.40

        self._init_yolo()
        self._init_mediapipe()

    def _init_yolo(self):
        try:
            from ultralytics import YOLO
            resolved_path = resolve_asset_path(self.model_path)
            if not os.path.exists(resolved_path):
                if os.path.exists("yolov8n.pt"):
                    resolved_path = os.path.abspath("yolov8n.pt")
                else:
                    alt = resolve_asset_path("yolov8n.pt")
                    if os.path.exists(alt):
                        resolved_path = alt
            self.yolo_model = YOLO(resolved_path)
            print(f"[PerceptionEngine] YOLO detector loaded ({resolved_path})")
        except Exception as e:
            print(f"[PerceptionEngine] YOLO initialization note ({e}). Using CV tracking fallback.")
            self.yolo_model = None

    def _init_mediapipe(self):
        try:
            import mediapipe as mp
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
                self.mp_hands = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.35,
                    min_tracking_confidence=0.35,
                )
            else:
                from mediapipe.python.solutions import hands as mp_hands_module
                self.mp_hands = mp_hands_module.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.35,
                    min_tracking_confidence=0.35,
                )
            print("[PerceptionEngine] MediaPipe Hand Tracking initialized successfully.")
        except Exception as e:
            print(f"[PerceptionEngine] MediaPipe note ({e}). Using skin-contour fallback.")
            self.mp_hands = None

    def process_frame(
        self, frame: np.ndarray
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool, np.ndarray]:
        """
        Process frame for Everyday Desk Objects and Hands only.
        """
        if frame is None or frame.size == 0:
            return [], [], False, frame

        h, w, _ = frame.shape
        annotated_frame = frame.copy()
        detected_objects: List[Dict[str, Any]] = []
        hands: List[Dict[str, Any]] = []
        now = time.time()

        # --- 1. YOLO Object Detection (Desk Objects Whitelist Only) ---
        if self.yolo_model is not None:
            try:
                results = self.yolo_model(frame, verbose=False, conf=self.conf_threshold)
                for res in results:
                    boxes = res.boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        cls_name = res.names.get(cls_id, f"class_{cls_id}").lower()
                        conf = float(box.conf[0].item())
                        xyxy = [int(v) for v in box.xyxy[0].tolist()]

                        clean_label = None
                        display_name = None
                        box_color = (0, 220, 100)

                        if cls_name in ["book", "notebook"]:
                            clean_label = "book"
                            display_name = "Notebook"
                            box_color = (0, 220, 100)
                        elif cls_name in ["laptop", "keyboard", "tv", "monitor"]:
                            clean_label = "laptop"
                            display_name = "Laptop"
                            box_color = (0, 200, 150)
                        elif cls_name in ["pen", "pencil", "toothbrush", "scissors", "fork", "knife"]:
                            clean_label = "pen"
                            display_name = "Pen"
                            box_color = (0, 255, 128)
                        elif cls_name in ["bottle", "wine glass", "vase"]:
                            clean_label = "bottle"
                            display_name = "Bottle"
                            box_color = (0, 220, 100)
                        elif cls_name in ["cup", "bowl"]:
                            clean_label = "cup"
                            display_name = "Cup"
                            box_color = (0, 220, 160)
                        elif cls_name in ["cell phone", "phone", "remote"]:
                            clean_label = "phone"
                            display_name = "Phone"
                            box_color = (0, 200, 255)
                        elif cls_name in ["mouse"]:
                            clean_label = "mouse"
                            display_name = "Mouse"
                            box_color = (0, 200, 255)
                        elif cls_name in ["person"]:
                            clean_label = "person"
                            display_name = "Human"
                            box_color = (255, 200, 0)

                        # Filter out any non-desk items
                        if clean_label is None:
                            continue

                        detected_objects.append({
                            "label": clean_label,
                            "bbox": xyxy,
                            "confidence": conf,
                        })

                        # Draw bounding box and label badge
                        cv2.rectangle(annotated_frame, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), box_color, 2)
                        tag_text = f"{display_name} {conf:.2f}"
                        t_sz = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
                        cv2.rectangle(
                            annotated_frame,
                            (xyxy[0], xyxy[1] - 18),
                            (xyxy[0] + t_sz[0] + 6, xyxy[1]),
                            (0, 0, 0),
                            -1,
                        )
                        cv2.putText(
                            annotated_frame,
                            tag_text,
                            (xyxy[0] + 3, max(12, xyxy[1] - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            box_color,
                            1,
                            cv2.LINE_AA,
                        )
            except Exception:
                pass

        # --- 2. MediaPipe Hand Landmark Tracking & Pinch Grasp Estimation ---
        if self.mp_hands is not None:
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_results = self.mp_hands.process(rgb_frame)
                if mp_results.multi_hand_landmarks:
                    for idx, hand_lms in enumerate(mp_results.multi_hand_landmarks):
                        pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand_lms.landmark]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        x1, y1 = max(0, min(xs) - 15), max(0, min(ys) - 15)
                        x2, y2 = min(w, max(xs) + 15), min(h, max(ys) + 15)
                        cx = sum(xs) / len(xs)
                        cy = sum(ys) / len(ys)

                        hand_type = "Right" if idx == 0 else "Left"
                        if mp_results.multi_handedness and len(mp_results.multi_handedness) > idx:
                            hand_type = mp_results.multi_handedness[idx].classification[0].label

                        # Pinch distance between thumb tip (4) and index finger tip (8)
                        thumb_tip = pts[4]
                        index_tip = pts[8]
                        pinch_dist = math.hypot(thumb_tip[0] - index_tip[0], thumb_tip[1] - index_tip[1])
                        is_grasping = pinch_dist < 50.0

                        hand_info = {
                            "type": hand_type,
                            "bbox": [x1, y1, x2, y2],
                            "centroid": (cx, cy),
                            "is_grasping": is_grasping,
                            "confidence": 0.96,
                        }
                        hands.append(hand_info)

                        detected_objects.append({
                            "label": "hand",
                            "bbox": [x1, y1, x2, y2],
                            "confidence": 0.96,
                        })

                        # If user holds pen or pinches fingers, infer writing pen candidate
                        if is_grasping:
                            fx = int((thumb_tip[0] + index_tip[0]) / 2)
                            fy = int((thumb_tip[1] + index_tip[1]) / 2)
                            detected_objects.append({
                                "label": "pen",
                                "bbox": [fx - 25, fy - 25, fx + 25, fy + 25],
                                "confidence": 0.92,
                            })

                        # Draw hand polygon
                        hull = cv2.convexHull(np.array(pts, dtype=np.int32))
                        hand_color = (0, 140, 255) if is_grasping else (0, 180, 255)
                        cv2.polylines(annotated_frame, [hull], True, hand_color, 2)
                        for pt in pts:
                            cv2.circle(annotated_frame, pt, 2, (0, 255, 255), -1)
                        cv2.circle(annotated_frame, (int(cx), int(cy)), 5, (0, 140, 255), -1)

                        status_tag = " [HOLDING/PINCH]" if is_grasping else ""
                        cv2.putText(
                            annotated_frame,
                            f"Hand ({hand_type}){status_tag}",
                            (x1, max(15, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            hand_color,
                            1,
                            cv2.LINE_AA,
                        )
            except Exception:
                pass

        # --- 3. Skin-Color Contour Fallback Hand Detector ---
        if len(hands) == 0:
            try:
                ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
                skin_mask = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=2)
                skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_DILATE, kernel, iterations=1)

                contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                valid_contours = [c for c in contours if 1800 < cv2.contourArea(c) < 90000]
                valid_contours = sorted(valid_contours, key=cv2.contourArea, reverse=True)[:2]

                for cnt in valid_contours:
                    bx, by, bw, bh = cv2.boundingRect(cnt)
                    hull = cv2.convexHull(cnt)
                    M = cv2.moments(cnt)
                    cx = M["m10"] / M["m00"] if M["m00"] > 0 else (bx + bw / 2.0)
                    cy = M["m01"] / M["m00"] if M["m00"] > 0 else (by + bh / 2.0)
                    hand_type = "Right" if cx > w / 2 else "Left"
                    aspect = float(bw) / max(1, bh)
                    is_grasping = (aspect < 0.65 or aspect > 1.55)

                    hand_info = {
                        "type": hand_type,
                        "bbox": [bx, by, bx + bw, by + bh],
                        "centroid": (cx, cy),
                        "is_grasping": is_grasping,
                        "confidence": 0.88,
                    }
                    hands.append(hand_info)
                    detected_objects.append({
                        "label": "hand",
                        "bbox": [bx, by, bx + bw, by + bh],
                        "confidence": 0.88,
                    })

                    if is_grasping:
                        detected_objects.append({
                            "label": "pen",
                            "bbox": [int(cx - 20), int(cy - 20), int(cx + 20), int(cy + 20)],
                            "confidence": 0.82,
                        })

                    orange_color = (0, 140, 255) if is_grasping else (0, 165, 255)
                    cv2.polylines(annotated_frame, [hull], True, orange_color, 2)
                    cv2.circle(annotated_frame, (int(cx), int(cy)), 5, orange_color, -1)
            except Exception:
                pass

        # --- 4. Anti-Flicker Temporal Persistence Buffer ---
        current_labels = set()
        for det in detected_objects:
            lbl = det["label"]
            current_labels.add(lbl)
            self.persistence_buffer[lbl] = {
                "bbox": det["bbox"],
                "confidence": det.get("confidence", 0.9),
                "last_seen": now,
            }

        for lbl, cached in list(self.persistence_buffer.items()):
            if lbl not in current_labels:
                if (now - cached["last_seen"]) <= self.persistence_timeout_s:
                    detected_objects.append({
                        "label": lbl,
                        "bbox": cached["bbox"],
                        "confidence": cached["confidence"] * 0.92,
                    })
                else:
                    self.persistence_buffer.pop(lbl, None)

        return detected_objects, hands, False, annotated_frame
