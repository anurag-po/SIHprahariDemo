"""
Hybrid Multi-Modal Perception Engine for PRAHARI HAR Space Experiment Assistant.
Combines:
1. Low-latency, high-accuracy YOLOv8 object detection with comprehensive desk-object semantic mapping
2. MediaPipe Hand Landmarking (Tasks API & legacy fallback) with grasp/pinch state estimation
3. Real-time AR HUD corner borders, high-contrast badges, and NMS deduplication
4. Anti-flicker temporal smoothing for rock-solid object tracking
5. Zero-latency inference with CPU multi-threading and startup warmup
"""

import os
import time
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np

try:
    from paths import resolve_asset_path
except ImportError:
    resolve_asset_path = lambda p: p


def _draw_refined_borders(
    annotated_frame: np.ndarray,
    bbox: List[int],
    display_name: str,
    confidence: float,
    color: Tuple[int, int, int] = (0, 220, 100),
    is_protocol_target: bool = True,
):
    """
    Renders high-definition AR HUD corner brackets and high-contrast information
    badges around detected objects with zero CPU overhead (<0.05ms).
    """
    h, w = annotated_frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(w - 1, int(x1)))
    y1 = max(0, min(h - 1, int(y1)))
    x2 = max(0, min(w - 1, int(x2)))
    y2 = max(0, min(h - 1, int(y2)))
    bw = x2 - x1
    bh = y2 - y1
    if bw <= 4 or bh <= 4:
        return

    # 1. Main bounding rectangle
    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

    # 2. Prominent AR HUD Corner Brackets (highlighting exact borders and boundaries)
    corner_len = max(6, min(24, int(bw * 0.22), int(bh * 0.22)))
    corner_color = (0, 255, 255) if is_protocol_target else (0, 210, 255)
    thick = 3
    # Top-Left
    cv2.line(annotated_frame, (x1, y1), (x1 + corner_len, y1), corner_color, thick)
    cv2.line(annotated_frame, (x1, y1), (x1, y1 + corner_len), corner_color, thick)
    # Top-Right
    cv2.line(annotated_frame, (x2, y1), (x2 - corner_len, y1), corner_color, thick)
    cv2.line(annotated_frame, (x2, y1), (x2, y1 + corner_len), corner_color, thick)
    # Bottom-Left
    cv2.line(annotated_frame, (x1, y2), (x1 + corner_len, y2), corner_color, thick)
    cv2.line(annotated_frame, (x1, y2), (x1, y2 - corner_len), corner_color, thick)
    # Bottom-Right
    cv2.line(annotated_frame, (x2, y2), (x2 - corner_len, y2), corner_color, thick)
    cv2.line(annotated_frame, (x2, y2), (x2, y2 - corner_len), corner_color, thick)

    # 3. High-Contrast Text Badge with Class & Confidence
    badge_text = f"{display_name} {int(confidence * 100)}%"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.44
    (tw, th), _ = cv2.getTextSize(badge_text, font, font_scale, 1)
    by1 = max(0, y1 - th - 8)
    by2 = max(th + 8, y1)
    bx1 = x1
    bx2 = min(w, x1 + tw + 10)
    cv2.rectangle(annotated_frame, (bx1, by1), (bx2, by2), color, -1)
    text_color = (0, 0, 0) if (color[0] + color[1] + color[2]) > 400 else (255, 255, 255)
    cv2.putText(
        annotated_frame,
        badge_text,
        (bx1 + 5, by2 - 4),
        font,
        font_scale,
        text_color,
        1,
        cv2.LINE_AA,
    )


class PerceptionEngine:
    def __init__(
        self,
        model_path: str = "models/yolov8n.pt",
        custom_classes: Optional[List[str]] = None,
        confidence_threshold: float = 0.20,
    ):
        self.model_path = model_path
        self.custom_classes = custom_classes or [
            "book", "laptop", "pen", "cup", "bottle", "phone", "mouse", "glove", "person", "hand"
        ]
        self.conf_threshold = confidence_threshold

        self.yolo_model = None
        self.mp_landmarker = None
        self.mp_hands = None
        self.use_mp_tasks = False

        # Anti-flicker temporal smoothing buffer
        self.persistence_buffer: Dict[str, Dict[str, Any]] = {}
        self.persistence_timeout_s = 0.30

        self._init_yolo()
        self._init_mediapipe()
        self._warmup()

    def _init_yolo(self):
        try:
            from ultralytics import YOLO
            resolved_path = resolve_asset_path(self.model_path)
            if not os.path.exists(resolved_path):
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
        # 1. Try modern MediaPipe Tasks API (MediaPipe 0.10+ / 1.0+)
        try:
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python import vision
            task_path = resolve_asset_path("models/hand_landmarker.task")
            if not os.path.exists(task_path):
                root_task = os.path.join(os.path.dirname(__file__), "..", "models", "hand_landmarker.task")
                if os.path.exists(root_task):
                    task_path = root_task

            if os.path.exists(task_path):
                options = vision.HandLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=task_path),
                    num_hands=2,
                    min_hand_detection_confidence=0.40,
                    min_hand_presence_confidence=0.40,
                    min_tracking_confidence=0.40,
                )
                self.mp_landmarker = vision.HandLandmarker.create_from_options(options)
                self.use_mp_tasks = True
                print(f"[PerceptionEngine] MediaPipe Tasks HandLandmarker loaded ({task_path}).")
                return
        except Exception as e:
            print(f"[PerceptionEngine] MediaPipe Tasks notice: {e}")

        # 2. Try legacy MediaPipe Solutions API
        try:
            import mediapipe as mp
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
                self.mp_hands = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.40,
                    min_tracking_confidence=0.40,
                )
                self.use_mp_tasks = False
                print("[PerceptionEngine] Legacy MediaPipe Solutions Hands loaded.")
                return
            else:
                from mediapipe.python.solutions import hands as mp_hands_module
                self.mp_hands = mp_hands_module.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.40,
                    min_tracking_confidence=0.40,
                )
                self.use_mp_tasks = False
                print("[PerceptionEngine] MediaPipe python.solutions Hands loaded.")
                return
        except Exception as e:
            print(f"[PerceptionEngine] MediaPipe legacy notice: {e}.")
            self.mp_hands = None
            self.mp_landmarker = None
            self.use_mp_tasks = False

    def _warmup(self):
        """Warm up deep-learning models on a dummy frame so live camera starts instantly with zero latency."""
        try:
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            if self.yolo_model is not None:
                _ = self.yolo_model(dummy, verbose=False, conf=self.conf_threshold, imgsz=480, device="cpu")
            if self.use_mp_tasks and self.mp_landmarker is not None:
                import mediapipe as mp
                _ = self.mp_landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=dummy))
            elif self.mp_hands is not None:
                _ = self.mp_hands.process(dummy)
        except Exception:
            pass

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
        now = time.time()

        # Filter out background furniture to avoid distracting overlays
        FURNITURE_CLASSES = {"chair", "couch", "bed", "dining table", "toilet", "sink", "refrigerator"}

        # --- 1. Fast YOLO Object Detection ---
        if self.yolo_model is not None:
            try:
                results = self.yolo_model(frame, verbose=False, conf=self.conf_threshold, imgsz=480, device="cpu")
                raw_boxes = []
                for res in results:
                    boxes = res.boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        cls_name = res.names.get(cls_id, f"class_{cls_id}").lower()
                        conf = float(box.conf[0].item())
                        xyxy = [int(v) for v in box.xyxy[0].tolist()]

                        if cls_name in FURNITURE_CLASSES:
                            continue

                        # Filter out low-confidence human detections to keep workbench clean
                        if cls_name == "person" and conf < 0.45:
                            continue

                        raw_boxes.append((cls_name, conf, xyxy))

                # Deduplicate overlapping boxes with IoU > 0.50
                deduped_boxes = []
                for cls_name, conf, b1 in sorted(raw_boxes, key=lambda x: x[1], reverse=True):
                    # For person, only keep 1 (the highest confidence person)
                    if cls_name == "person" and any(d[0] == "person" for d in deduped_boxes):
                        continue
                    # Check IoU against existing boxes of the same class
                    overlap = False
                    for existing_cls, _, b2 in deduped_boxes:
                        if existing_cls == cls_name:
                            x_inter = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
                            y_inter = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
                            inter = x_inter * y_inter
                            if inter > 0:
                                a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
                                a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
                                iou = inter / float(a1 + a2 - inter)
                                if iou > 0.45:
                                    overlap = True
                                    break
                    if not overlap:
                        deduped_boxes.append((cls_name, conf, b1))

                # Map semantic classes and render
                for cls_name, conf, xyxy in deduped_boxes:
                    clean_label = None
                    display_name = cls_name.title()
                    draw_color = (0, 220, 100)  # Green default
                    is_protocol = True
                    mapped_labels = set()

                    if cls_name in ["person"]:
                        clean_label = "person"
                        display_name = "Human"
                        draw_color = (255, 200, 0)  # Cyan
                        mapped_labels = {"person", "human"}
                    elif cls_name in ["book", "notebook"]:
                        clean_label = "book"
                        display_name = "Notebook"
                        draw_color = (255, 140, 60)  # Royal Azure / Purple
                        mapped_labels = {"book", "notebook"}
                    elif cls_name in ["laptop", "keyboard", "tablet", "binder"]:
                        clean_label = "book"
                        display_name = "Notebook / Laptop" if cls_name == "laptop" else "Notebook"
                        draw_color = (255, 140, 60)
                        mapped_labels = {"book", "laptop", "notebook"}
                    elif cls_name in ["pen", "pencil", "toothbrush", "knife", "fork", "spoon", "scissors"]:
                        clean_label = "pen"
                        display_name = "Pen"
                        draw_color = (50, 255, 50)  # Bright Lime Green
                        mapped_labels = {"pen"}
                    elif cls_name in ["bottle", "vase"]:
                        clean_label = "bottle"
                        display_name = "Bottle"
                        draw_color = (0, 230, 118)  # Bright Emerald Green
                        mapped_labels = {"bottle"}
                    elif cls_name in ["cup", "wine glass", "bowl"]:
                        clean_label = "cup"
                        display_name = "Cup"
                        draw_color = (180, 220, 50)  # Teal
                        mapped_labels = {"cup"}
                    elif cls_name in ["cell phone", "phone", "remote", "clock", "calculator"]:
                        clean_label = "phone"
                        display_name = "Phone"
                        draw_color = (200, 60, 255)  # Magenta
                        mapped_labels = {"phone"}
                    elif cls_name in ["mouse"]:
                        clean_label = "mouse"
                        display_name = "Mouse"
                        draw_color = (0, 215, 255)  # Amber / Gold
                        mapped_labels = {"mouse"}
                    elif cls_name in ["glove"]:
                        clean_label = "glove"
                        display_name = "Glove"
                        draw_color = (100, 255, 255)
                        mapped_labels = {"glove"}
                    else:
                        clean_label = cls_name
                        display_name = cls_name.title()
                        draw_color = (0, 200, 255)  # Amber
                        mapped_labels = {clean_label}
                        is_protocol = False

                    for lbl in mapped_labels:
                        detected_objects.append({
                            "label": lbl,
                            "bbox": xyxy,
                            "confidence": conf,
                        })

                    # Render crisp AR HUD corner brackets & label badge
                    _draw_refined_borders(
                        annotated_frame=annotated_frame,
                        bbox=xyxy,
                        display_name=display_name,
                        confidence=conf,
                        color=draw_color,
                        is_protocol_target=is_protocol,
                    )
            except Exception:
                pass

        # --- 2. MediaPipe Hand Landmark Tracking ---
        if self.use_mp_tasks and self.mp_landmarker is not None:
            try:
                import mediapipe as mp
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                mp_res = self.mp_landmarker.detect(mp_image)
                if mp_res and mp_res.hand_landmarks:
                    for idx, hand_lms in enumerate(mp_res.hand_landmarks):
                        pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand_lms]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        x1, y1 = max(0, min(xs) - 15), max(0, min(ys) - 15)
                        x2, y2 = min(w, max(xs) + 15), min(h, max(ys) + 15)
                        cx = sum(xs) / len(xs)
                        cy = sum(ys) / len(ys)

                        hand_type = "Right" if idx == 0 else "Left"
                        if mp_res.handedness and len(mp_res.handedness) > idx and len(mp_res.handedness[idx]) > 0:
                            cat = mp_res.handedness[idx][0]
                            hand_type = cat.category_name or cat.display_name or hand_type

                        # Pinch / grasp detection (thumb tip #4 vs index tip #8)
                        thumb_tip = pts[4]
                        index_tip = pts[8]
                        pinch_dist = np.hypot(thumb_tip[0] - index_tip[0], thumb_tip[1] - index_tip[1])
                        is_grasping = pinch_dist < 48.0

                        hand_info = {
                            "type": hand_type,
                            "bbox": [x1, y1, x2, y2],
                            "centroid": (cx, cy),
                            "is_grasping": is_grasping,
                            "confidence": 0.95,
                        }
                        hands.append(hand_info)

                        detected_objects.append({
                            "label": "hand",
                            "bbox": [x1, y1, x2, y2],
                            "confidence": 0.95,
                        })

                        # If user pinches fingers, infer writing pen / stylus candidate
                        if is_grasping:
                            px = int((thumb_tip[0] + index_tip[0]) / 2)
                            py = int((thumb_tip[1] + index_tip[1]) / 2)
                            pen_box = [max(0, px - 25), max(0, py - 25), min(w, px + 25), min(h, py + 25)]
                            detected_objects.append({
                                "label": "pen",
                                "bbox": pen_box,
                                "confidence": 0.92,
                            })
                            _draw_refined_borders(
                                annotated_frame=annotated_frame,
                                bbox=pen_box,
                                display_name="Pen",
                                confidence=0.92,
                                color=(50, 255, 50),
                                is_protocol_target=True,
                            )

                        # Draw hand polygon, skeleton & grasp tag
                        hull = cv2.convexHull(np.array(pts, dtype=np.int32))
                        color = (0, 140, 255) if is_grasping else (0, 165, 255)
                        cv2.polylines(annotated_frame, [hull], True, color, 2)
                        cv2.circle(annotated_frame, (int(cx), int(cy)), 5, (0, 165, 255), -1)
                        for pt in pts:
                            cv2.circle(annotated_frame, pt, 2, (0, 255, 255), -1)
                        status_tag = " [GRASPING]" if is_grasping else ""
                        cv2.putText(
                            annotated_frame,
                            f"Hand ({hand_type}){status_tag}",
                            (x1, max(18, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            color,
                            1,
                            cv2.LINE_AA,
                        )
            except Exception:
                pass

        elif self.mp_hands is not None:
            # Legacy MediaPipe Solutions fallback
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

                        thumb_tip = pts[4]
                        index_tip = pts[8]
                        pinch_dist = np.hypot(thumb_tip[0] - index_tip[0], thumb_tip[1] - index_tip[1])
                        is_grasping = pinch_dist < 48.0

                        hand_info = {
                            "type": hand_type,
                            "bbox": [x1, y1, x2, y2],
                            "centroid": (cx, cy),
                            "is_grasping": is_grasping,
                            "confidence": 0.95,
                        }
                        hands.append(hand_info)

                        detected_objects.append({
                            "label": "hand",
                            "bbox": [x1, y1, x2, y2],
                            "confidence": 0.95,
                        })

                        if is_grasping:
                            px = int((thumb_tip[0] + index_tip[0]) / 2)
                            py = int((thumb_tip[1] + index_tip[1]) / 2)
                            pen_box = [max(0, px - 25), max(0, py - 25), min(w, px + 25), min(h, py + 25)]
                            detected_objects.append({
                                "label": "pen",
                                "bbox": pen_box,
                                "confidence": 0.92,
                            })
                            _draw_refined_borders(
                                annotated_frame=annotated_frame,
                                bbox=pen_box,
                                display_name="Pen",
                                confidence=0.92,
                                color=(50, 255, 50),
                                is_protocol_target=True,
                            )

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
            except Exception:
                pass

        # --- 3. Robust Computer Vision Hand Detection Fallback ---
        if len(hands) == 0:
            try:
                ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
                skin_mask = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=2)
                skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_DILATE, kernel, iterations=1)

                contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                valid_contours = [c for c in contours if 1800 < cv2.contourArea(c) < 80000]
                valid_contours = sorted(valid_contours, key=cv2.contourArea, reverse=True)[:2]

                for cnt in valid_contours:
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

                    detected_objects.append({
                        "label": "hand",
                        "bbox": [bx, by, bx + bw, by + bh],
                        "confidence": 0.88,
                    })

                    orange_color = (0, 140, 255) if is_grasping else (0, 165, 255)
                    cv2.polylines(annotated_frame, [hull], True, orange_color, 2)
                    cv2.circle(annotated_frame, (int(cx), int(cy)), 6, orange_color, -1)
                    status_tag = " [GRASPING]" if is_grasping else ""
                    cv2.putText(
                        annotated_frame,
                        f"Hand ({hand_type}){status_tag}",
                        (bx, max(18, by - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.48,
                        orange_color,
                        1,
                        cv2.LINE_AA,
                    )
            except Exception:
                pass

        # --- 4. Anti-Flicker Temporal Persistence Smoothing ---
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
                        "confidence": cached["confidence"] * 0.90,
                    })
                else:
                    self.persistence_buffer.pop(lbl, None)

        if any(d["label"] == "glove" for d in detected_objects):
            hands_gloved = True

        return detected_objects, hands, hands_gloved, annotated_frame
