"""
Per-object micro-FSM tracker and hand-interaction tracker for PRAHARI.
Maintains state for each object (absent, in_hand, stationary, in_roi, spans_rois),
tracks rolling centroid trajectory history for hands and objects,
and emits discrete interaction events with confidence scores.
"""

from collections import deque
import math
import time
from typing import Dict, List, Tuple, Optional, Any


class ObjectMicroFSM:
    """Micro-state machine for a single tracked object class."""
    def __init__(self, label: str, history_len: int = 10):
        self.label = label
        self.state = "absent"  # absent, in_hand, stationary, in_roi
        self.current_bbox: Optional[List[int]] = None  # [x1, y1, x2, y2]
        self.current_centroid: Optional[Tuple[float, float]] = None
        self.confidence: float = 0.0
        self.trajectory_history = deque(maxlen=history_len)  # [(x, y, timestamp), ...]
        self.frames_stationary = 0
        self.frames_in_hand = 0
        self.current_rois: List[str] = []
        self.last_seen_time = 0.0
        self.dwell_start_time: Optional[float] = None
        self.last_emitted_event: Optional[str] = None


class ObjectTracker:
    def __init__(self, rois: Dict[str, List[int]], trajectory_window: int = 10):
        """
        rois: Dict mapping roi_name -> [x1, y1, x2, y2]
        trajectory_window: rolling history length in frames
        """
        self.rois = rois
        self.trajectory_window = trajectory_window
        self.objects: Dict[str, ObjectMicroFSM] = {}
        self.hand_trajectories: Dict[str, deque] = {
            "hand_left": deque(maxlen=trajectory_window),
            "hand_right": deque(maxlen=trajectory_window),
            "hand_any": deque(maxlen=trajectory_window),
        }
        self.hand_bboxes: Dict[str, List[int]] = {}
        self.hand_centroids: Dict[str, Tuple[float, float]] = {}
        self.stationary_movement_threshold = 6.0  # max centroid shift in pixels to be stationary
        self.in_hand_distance_threshold = 95.0    # pixel distance from hand centroid to object center

    def _get_or_create(self, label: str) -> ObjectMicroFSM:
        if label not in self.objects:
            self.objects[label] = ObjectMicroFSM(label, self.trajectory_window)
        return self.objects[label]

    def point_in_box(self, pt: Tuple[float, float], box: List[int]) -> bool:
        x, y = pt
        x1, y1, x2, y2 = box
        return x1 <= x <= x2 and y1 <= y <= y2

    def box_iou(self, b1: List[int], b2: List[int]) -> float:
        x1 = max(b1[0], b2[0])
        y1 = max(b1[1], b2[1])
        x2 = min(b1[2], b2[2])
        y2 = min(b1[3], b2[3])
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        if inter_area == 0:
            return 0.0
        b1_area = (b1[2] - b1[0]) * (b1[3] - b1[1])
        b2_area = (b2[2] - b2[0]) * (b2[3] - b2[1])
        union_area = b1_area + b2_area - inter_area
        return inter_area / union_area if union_area > 0 else 0.0

    def box_overlap_ratio(self, b1: List[int], b2: List[int]) -> float:
        x1 = max(b1[0], b2[0])
        y1 = max(b1[1], b2[1])
        x2 = min(b1[2], b2[2])
        y2 = min(b1[3], b2[3])
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        if inter_area == 0:
            return 0.0
        b1_area = max(1, (b1[2] - b1[0]) * (b1[3] - b1[1]))
        return inter_area / float(b1_area)

    def get_hand_trajectory(self, hand_id: str = "hand_any") -> List[Tuple[float, float, float]]:
        """Return rolling centroid trajectory list [(x, y, time), ...]"""
        return list(self.hand_trajectories.get(hand_id, []))

    def update_hands(self, hands_detected: List[Dict[str, Any]], now: Optional[float] = None):
        """
        hands_detected: list of dicts:
          [{"id": "hand_0", "type": "Left"|"Right", "bbox": [x1,y1,x2,y2], "centroid": (cx, cy), "confidence": float}]
        """
        now = now or time.time()
        self.hand_bboxes.clear()
        self.hand_centroids.clear()

        for idx, h in enumerate(hands_detected):
            hand_type = h.get("type", "any").lower()
            hand_key = f"hand_{hand_type}" if hand_type in ["left", "right"] else f"hand_{idx}"
            centroid = h.get("centroid", ((h["bbox"][0] + h["bbox"][2]) / 2, (h["bbox"][1] + h["bbox"][3]) / 2))
            
            self.hand_bboxes[hand_key] = h["bbox"]
            self.hand_centroids[hand_key] = centroid
            
            if hand_key not in self.hand_trajectories:
                self.hand_trajectories[hand_key] = deque(maxlen=self.trajectory_window)
            self.hand_trajectories[hand_key].append((centroid[0], centroid[1], now))
            self.hand_trajectories["hand_any"].append((centroid[0], centroid[1], now))

    def update_detections(
        self,
        detected_objects: List[Dict[str, Any]],
        hands_gloved: bool = False,
        now: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Update states for detected objects and emit discrete micro-events.
        detected_objects: list of dicts {"label": str, "bbox": [x1,y1,x2,y2], "confidence": float}
        Returns list of emitted event dictionaries.
        """
        now = now or time.time()
        emitted_events: List[Dict[str, Any]] = []

        if hands_gloved:
            emitted_events.append({
                "type": "hands_gloved",
                "object": "glove",
                "confidence": 0.95,
                "timestamp": now,
            })

        seen_labels = set()
        for det in detected_objects:
            label = det["label"]
            bbox = det["bbox"]
            conf = det.get("confidence", 0.9)
            seen_labels.add(label)

            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            centroid = (cx, cy)

            obj = self._get_or_create(label)
            obj.current_bbox = bbox
            obj.current_centroid = centroid
            obj.confidence = conf
            obj.last_seen_time = now
            obj.trajectory_history.append((cx, cy, now))

            # Determine ROIs containing centroid or having bounding box overlap
            rois_inside = []
            for r_name, r_box in self.rois.items():
                if self.point_in_box(centroid, r_box) or self.box_overlap_ratio(bbox, r_box) > 0.12:
                    rois_inside.append(r_name)
            obj.current_rois = rois_inside

            # Check if in hand (distance to any hand centroid or box overlap)
            is_in_hand = False
            for hand_id, h_center in self.hand_centroids.items():
                dist = math.hypot(cx - h_center[0], cy - h_center[1])
                if dist < self.in_hand_distance_threshold:
                    is_in_hand = True
                    break

            if not is_in_hand:
                for hand_id, h_bbox in self.hand_bboxes.items():
                    if self.box_iou(bbox, h_bbox) > 0.15:
                        is_in_hand = True
                        break

            # Calculate movement over recent frames
            if len(obj.trajectory_history) >= 3:
                p_old = obj.trajectory_history[-3]
                p_new = obj.trajectory_history[-1]
                movement = math.hypot(p_new[0] - p_old[0], p_new[1] - p_old[1])
            else:
                movement = 0.0

            if is_in_hand:
                obj.frames_in_hand += 1
                obj.frames_stationary = 0
                obj.state = "in_hand"
            else:
                obj.frames_in_hand = 0
                if movement < self.stationary_movement_threshold:
                    obj.frames_stationary += 1
                else:
                    obj.frames_stationary = 0

            # Emit in_hand event if held
            if obj.state == "in_hand" and obj.frames_in_hand >= 2:
                emitted_events.append({
                    "type": f"object_in_hand:{label}",
                    "object": label,
                    "state": "in_hand",
                    "confidence": conf,
                    "timestamp": now,
                    "centroid": centroid,
                })

            # Event generation logic
            for r_name in rois_inside:
                # 1. object_in_roi
                event_key = f"object_in_roi:{label}:{r_name}"
                emitted_events.append({
                    "type": event_key,
                    "object": label,
                    "roi": r_name,
                    "state": obj.state,
                    "confidence": conf,
                    "timestamp": now,
                    "centroid": centroid,
                })

                # 2. object_stationary_in_roi
                if obj.state == "stationary" and obj.frames_stationary >= 3:
                    stat_event_key = f"object_stationary_in_roi:{label}:{r_name}"
                    emitted_events.append({
                        "type": stat_event_key,
                        "object": label,
                        "roi": r_name,
                        "confidence": conf,
                        "timestamp": now,
                        "centroid": centroid,
                    })

                    # 3. Dwell check (e.g. 2s steady hold)
                    if obj.dwell_start_time is None:
                        obj.dwell_start_time = now
                    dwell_duration = now - obj.dwell_start_time
                    if dwell_duration >= 2.0:
                        emitted_events.append({
                            "type": f"dwell_object:{label}:{r_name}:2s",
                            "object": label,
                            "roi": r_name,
                            "confidence": conf,
                            "timestamp": now,
                            "centroid": centroid,
                        })
                        emitted_events.append({
                            "type": f"dwell_then_object_removed:{label}:{r_name}:2s",
                            "object": label,
                            "roi": r_name,
                            "confidence": conf,
                            "timestamp": now,
                            "centroid": centroid,
                        })
                else:
                    if obj.state != "stationary":
                        obj.dwell_start_time = None

            # Check spans_rois (e.g. wires connecting breadboard and battery_holder)
            if "wire" in label:
                # Approximate ends of wire using top-left and bottom-right or bbox corners
                p1 = (bbox[0], bbox[1])
                p2 = (bbox[2], bbox[3])
                spanned = []
                for r_name, r_box in self.rois.items():
                    if self.point_in_box(p1, r_box) or self.point_in_box(p2, r_box) or self.point_in_box(centroid, r_box):
                        spanned.append(r_name)
                
                # If spans across at least 2 distinct ROIs
                if len(set(spanned)) >= 2:
                    joined_rois = ",".join(sorted(list(set(spanned))))
                    spans_key = f"object_spans_rois:{label}:{joined_rois}"
                    emitted_events.append({
                        "type": spans_key,
                        "object": label,
                        "rois": list(set(spanned)),
                        "confidence": conf,
                        "timestamp": now,
                    })

        return emitted_events
