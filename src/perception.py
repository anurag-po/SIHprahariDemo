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
            resolved_path = self.model_path
            if not os.path.exists(resolved_path):
                # Check project root before letting Ultralytics auto-download
                root_path = os.path.join(os.path.dirname(__file__), "..", "yolov8n.pt")
                if os.path.exists(root_path):
                    resolved_path = root_path
                else:
                    resolved_path = "yolov8n.pt"
            self.yolo_model = YOLO(resolved_path)
            print(f"[PerceptionEngine] YOLO detector loaded ({resolved_path}).")
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

                        # Strict target whitelist to eliminate couch, chair, and other background noise
                        clean_label = None
                        display_name = None
                        draw_color = (0, 220, 100)  # Green for experiment objects

                        if cls_name in ["person"]:
                            clean_label = "person"
                            display_name = "Human"
                            draw_color = (255, 200, 0)  # Cyan/teal for human
                        elif cls_name in ["book", "laptop", "notebook"]:
                            clean_label = "book"
                            display_name = "Book" if cls_name == "book" else "Laptop"
                        elif cls_name in ["pen", "pencil", "toothbrush"]:
                            clean_label = "pen"
                            display_name = "Pen"
                        elif cls_name in ["bottle", "wine glass", "cup", "vase"]:
                            clean_label = "bottle"
                            display_name = "Bottle" if "bottle" in cls_name else "Cup"
                        elif cls_name in ["cell phone", "phone"]:
                            clean_label = "phone"
                            display_name = "Phone"
                        elif cls_name in ["mouse"]:
                            clean_label = "mouse"
                            display_name = "Mouse"
                        elif cls_name in ["glove"]:
                            clean_label = "glove"
                            display_name = "Glove"

                        # If not in our strict experiment whitelist, ignore completely (e.g. couch, chair, furniture)
                        if clean_label is None:
                            continue

                        mapped_labels = {clean_label}
                        if clean_label == "book" and cls_name == "laptop":
                            mapped_labels.add("laptop")
                        if clean_label == "bottle" and cls_name in ["cup", "wine glass"]:
                            mapped_labels.add("cup")

                        for lbl in mapped_labels:
                            detected_objects.append({
                                "label": lbl,
                                "bbox": xyxy,
                                "confidence": conf,
                            })

                        # Draw box only for permitted objects / human
                        cv2.rectangle(annotated_frame, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), draw_color, 2)
                        cv2.putText(
                            annotated_frame,
                            f"{display_name} {conf:.2f}",
                            (xyxy[0], max(15, xyxy[1] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            draw_color,
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
                        color = (0, 140, 255) if is_grasping else (0, 165, 255)
                        cv2.polylines(annotated_frame, [hull], True, color, 2)
                        cv2.circle(annotated_frame, (int(cx), int(cy)), 5, (0, 165, 255), -1)
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

        # --- 3. Robust Computer Vision Hand Detection Fallback (Orange Overlay) ---
        if len(hands) == 0:
            try:
                ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
                # Skin color range in YCrCb
                skin_mask = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=2)
                skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_DILATE, kernel, iterations=1)

                contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                valid_contours = [c for c in contours if 1800 < cv2.contourArea(c) < 80000]
                # Sort by area descending, take top 2 hands
                valid_contours = sorted(valid_contours, key=cv2.contourArea, reverse=True)[:2]

                for idx, cnt in enumerate(valid_contours):
                    bx, by, bw, bh = cv2.boundingRect(cnt)
                    hull = cv2.convexHull(cnt)
                    M = cv2.moments(cnt)
                    if M["m00"] > 0:
                        cx = M["m10"] / M["m00"]
                        cy = M["m01"] / M["m00"]
                    else:
                        cx, cy = bx + bw / 2.0, by + bh / 2.0

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

                    # Add to detected objects for tracking
                    detected_objects.append({
                        "label": "hand",
                        "bbox": [bx, by, bx + bw, by + bh],
                        "confidence": 0.88,
                    })

                    if is_grasping:
                        detected_objects.append({
                            "label": "pen",
                            "bbox": [int(cx - 20), int(cy - 20), int(cx + 20), int(cy + 20)],
                            "confidence": 0.80,
                        })

                    # Draw Hand in vibrant Orange (BGR: 0, 165, 255)
                    orange_color = (0, 140, 255) if is_grasping else (0, 165, 255)
                    cv2.polylines(annotated_frame, [hull], True, orange_color, 2)
                    cv2.circle(annotated_frame, (int(cx), int(cy)), 6, orange_color, -1)
                    status_tag = " [GRASPING]" if is_grasping else ""
                    cv2.putText(
                        annotated_frame,
                        f"Hand ({hand_type}){status_tag}",
                        (bx, max(18, by - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.50,
                        orange_color,
                        2,
                        cv2.LINE_AA,
                    )
            except Exception as e:
                pass

        if any(d["label"] == "glove" for d in detected_objects):
            hands_gloved = True

        return detected_objects, hands, hands_gloved, annotated_frame
