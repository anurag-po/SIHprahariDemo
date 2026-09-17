"""
Hybrid Multi-Modal Perception Engine for PRAHARI HAR Space Experiment Assistant.
Combines:
1. Low-latency YOLO object detection with comprehensive desk-object semantic mapping
2. MediaPipe Hand Landmarking with hand gesture & grasp/pinch state estimation
3. Direct Hand Activity Recognition (HAR) over workspace ROIs
"""

import os
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np


class PerceptionEngine:
    def __init__(
        self,
        model_path: str = "models/yolov8n.pt",
        custom_classes: Optional[List[str]] = None,
        confidence_threshold: float = 0.15,
    ):
        self.model_path = model_path
        self.custom_classes = custom_classes or [
            "glove", "breadboard", "resistor", "led", "wire_red", "wire_black", "battery",
            "book", "phone", "pen", "cup", "bottle", "person"
        ]
        self.conf_threshold = confidence_threshold

        self.yolo_model = None
        self.mp_hands = None
        self.mp_drawing = None

        self._init_yolo()
        self._init_mediapipe()

    def _init_yolo(self):
        try:
            from ultralytics import YOLO
            if os.path.exists(self.model_path):
                self.yolo_model = YOLO(self.model_path)
            else:
                self.yolo_model = YOLO("yolov8n.pt")
            print(f"[PerceptionEngine] YOLO detector loaded ({self.model_path}).")
        except Exception as e:
            print(f"[PerceptionEngine] YOLO initialization error ({e}). Using mock CV fallback.")
            self.yolo_model = None

    def _init_mediapipe(self):
        try:
            import mediapipe as mp
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
                self.mp_hands = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.4,
                    min_tracking_confidence=0.4,
                )
            else:
                from mediapipe.python.solutions import hands as mp_hands_module
                self.mp_hands = mp_hands_module.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.4,
                    min_tracking_confidence=0.4,
                )
            print("[PerceptionEngine] MediaPipe Hand tracking initialized.")
        except Exception as e:
            print(f"[PerceptionEngine] MediaPipe initialization error ({e}). Using bounding box proximity fallback.")
            self.mp_hands = None

    def process_frame(
        self, frame: np.ndarray
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool, np.ndarray]:
        """
        Process a single BGR frame.
        Returns:
          detected_objects: [{"label": str, "bbox": [x1,y1,x2,y2], "confidence": float}]
          hands: [{"type": "Left"|"Right", "bbox": [x1,y1,x2,y2], "centroid": (cx,cy), "confidence": float}]
          hands_gloved: bool
          annotated_frame: np.ndarray
        """
        if frame is None:
            return [], [], False, frame

        h, w, _ = frame.shape
        annotated_frame = frame.copy()
        detected_objects: List[Dict[str, Any]] = []
        hands: List[Dict[str, Any]] = []
        hands_gloved = False

        # --- 1. YOLO Object Detection with Broad Class Aliasing ---
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

                        # Map standard COCO names to experiment names
                        clean_label = cls_name
                        if cls_name in ["toothbrush", "pen", "fork", "knife", "scissors", "remote", "mouse"]:
                            clean_label = "pen"
                        elif cls_name in ["laptop", "keyboard", "book", "tv", "suitcase", "handbag", "backpack"]:
                            clean_label = "book"
                        elif cls_name in ["cell phone"]:
                            clean_label = "phone"
                        elif cls_name in ["bottle", "vase"]:
                            clean_label = "bottle"
                        elif cls_name in ["wine glass", "cup"]:
                            clean_label = "cup"

                        mapped_labels = {clean_label, cls_name}
                        if clean_label == "pen":
                            mapped_labels.add("pen")
                        if clean_label == "book":
                            mapped_labels.add("book")
                        if clean_label == "bottle":
                            mapped_labels.add("bottle")

                        for lbl in mapped_labels:
                            detected_objects.append({
                                "label": lbl,
                                "bbox": xyxy,
                                "confidence": conf,
                            })

                        # Draw box with clean human-readable name
                        cv2.rectangle(annotated_frame, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), (0, 220, 100), 2)
                        cv2.putText(
                            annotated_frame,
                            f"{clean_label} {conf:.2f}",
                            (xyxy[0], max(15, xyxy[1] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            (0, 255, 120),
                            1,
                            cv2.LINE_AA,
                        )
            except Exception as e:
                pass

        # --- 2. MediaPipe Hand Landmark Tracking & Hand-Object Inference ---
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

                        # Check pinch / writing grasp (thumb tip vs index tip distance)
                        thumb_tip = pts[4]
                        index_tip = pts[8]
                        pinch_dist = np.hypot(thumb_tip[0] - index_tip[0], thumb_tip[1] - index_tip[1])
                        is_grasping = pinch_dist < 45.0

                        hand_info = {
                            "type": hand_type,
                            "bbox": [x1, y1, x2, y2],
                            "centroid": (cx, cy),
                            "is_grasping": is_grasping,
                            "confidence": 0.95,
                        }
                        hands.append(hand_info)

                        # Emit hand as an interactive object for HAR
                        detected_objects.append({
                            "label": "hand",
                            "bbox": [x1, y1, x2, y2],
                            "confidence": 0.95,
                        })

                        # If grasping / pinch posture detected, register virtual pen tool candidate
                        if is_grasping:
                            detected_objects.append({
                                "label": "pen",
                                "bbox": [int(cx - 20), int(cy - 20), int(cx + 20), int(cy + 20)],
                                "confidence": 0.90,
                            })

                        # Draw hand landmarks & convex hull
                        hull = cv2.convexHull(np.array(pts, dtype=np.int32))
                        color = (0, 255, 255) if is_grasping else (0, 200, 255)
                        cv2.polylines(annotated_frame, [hull], True, color, 2)
                        cv2.circle(annotated_frame, (int(cx), int(cy)), 5, (0, 255, 255), -1)
                        status_tag = " [GRASPING]" if is_grasping else ""
                        cv2.putText(
                            annotated_frame,
                            f"Hand ({hand_type}){status_tag}",
                            (x1, max(15, y1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            color,
                            1,
                            cv2.LINE_AA,
                        )
            except Exception as e:
                pass

        if any(d["label"] == "glove" for d in detected_objects):
            hands_gloved = True

        return detected_objects, hands, hands_gloved, annotated_frame
