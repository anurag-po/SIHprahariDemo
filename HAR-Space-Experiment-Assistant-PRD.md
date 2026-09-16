# PRD — AI-Based Human Activity Recognition (HAR) System for On-Board Space Experiment Assistance

**Target readers:** coding agents (e.g. Gemini 3.8 Flash for fast scaffolding, Claude Opus 4.6 for architecture/logic). Read this whole document before writing code. Everything here is meant to be buildable inside a single hackathon (~24–36 hours) on a laptop with a webcam, no internet dependency at inference time, no cloud APIs, no paid GPU.

---

## 1. What we are actually building

An offline, edge-running desktop application that watches a fixed webcam feed of someone performing a pre-defined multi-step physical experiment, and:

1. Detects objects and hands in frame (pretrained/fine-tuned CV models).
2. Estimates body/hand pose to determine *what interaction is happening* (pick up, place, connect, press, pour, etc.).
3. Matches the detected interaction sequence against a pre-defined step graph for the experiment.
4. Announces (voice, via local TTS) the next expected step, and raises an immediate voice alert if a step is skipped or performed out of order.
5. Writes a timestamped, structured, lightweight log (JSON Lines or CSV) of every completed/skipped/out-of-order step with a status.
6. Simultaneously writes the raw video to local disk **and** streams it out over the network (UDP/RTSP) to a configurable IP:port — streaming failure must never block local recording.
7. Shows all of this live in a single-window GUI: video feed with overlays, current/next step, alert banner, running log.

No cloud calls, no internet lookups, no API keys at runtime. Training/dataset-prep can happen online beforehand; the shipped app must run fully offline.

The orientation-agnostic 3D Human Mesh Recovery (HMR) requirement (tracking astronaut relative to the payload rack instead of "the floor") is explicitly **optional/stretch** — build the MVP assuming a fixed camera and a person in a roughly-consistent orientation (which is exactly what a hackathon demo on Earth looks like), and only attempt HMR if the core pipeline is solid with time to spare. Section 12 describes how to fake this convincingly for a demo without a real gravity-invariant model.

---

## 2. Why this architecture (design rationale for the agent)

- **Do not train an object detector from nothing.** Fine-tune a small pretrained detector (YOLOv8n or YOLO11n, ~3–6MB) on a handful of custom classes captured in 15–20 minutes of labeling. Training a detector from scratch in a hackathon is a waste of time; transfer learning on 5–8 object classes with 60–100 images each converges in minutes on a laptop GPU or even CPU with a small nano model.
- **Do not build pose estimation from scratch.** Use MediaPipe Tasks (Pose Landmarker + Hand Landmarker), which run in real time on CPU with no GPU requirement — critical for an "offline standalone" deliverable that might be judged on a laptop with no dedicated GPU.
- **Sequence validation is a deterministic finite-state machine, not a learned model.** This is the part hackathon teams over-engineer and then run out of time on. The step logic should be a simple rule-based FSM driven by discrete "events" (object X entered hand-proximity, object X released, object Y and Z co-located, etc.) emitted by the perception layer. This is far more reliable, explainable, and debuggable live on stage than an end-to-end action-recognition network, and it is what makes "alert on skipped/out-of-order step" tractable at all.
- **Everything runs in one Python process** with a producer/consumer pattern: a capture+inference thread pushes frames/events into a queue; the FSM thread consumes events and drives voice/log/GUI. This avoids frame drops blocking inference and keeps the GUI responsive.

---

## 3. Tech stack (all free, all local, all pip-installable)

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.10+ | fastest to prototype, all needed libraries mature |
| Object detection | Ultralytics YOLOv8n / YOLO11n, fine-tuned | tiny, fast on CPU, easy to fine-tune with few images |
| Pose + hands | MediaPipe Tasks (PoseLandmarker, HandLandmarker) | real-time CPU inference, no training needed |
| Hand-object interaction | Custom rule: bounding-box IoU / centroid distance between hand landmark cluster and object boxes, tracked over frames | no ML needed, deterministic, explainable |
| Sequence/state logic | Custom FSM (plain Python, `transitions` library optional) | deterministic, testable, demo-safe |
| Voice alerts | `pyttsx3` (fully offline, cross-platform TTS) | no internet, no API key |
| Logging | Python `logging` + structured JSON Lines file | lightweight text file per the brief |
| Local video storage | OpenCV `VideoWriter` (MP4/H.264) | standard |
| Network streaming | `ffmpeg` subprocess piping frames out via UDP/RTSP to `--stream-ip` | works even if `ffmpeg` receiver is just VLC on another laptop for demo |
| GUI | PyQt6 (or Tkinter if PyQt install is flaky on demo machine) | single desktop window, embeds OpenCV frames as QImage |
| Dataset labeling | Roboflow free tier or `labelImg` locally | fast bounding-box labeling, exports YOLO format directly |
| Packaging | plain `venv` + `requirements.txt`; optional `pyinstaller` if a standalone binary is wanted for "deliverable: trained AI model that runs on offline standalone system" | keep it simple, a script + local model weights already satisfies "standalone" |

Do not introduce a web server, Docker, or cloud dependency anywhere in the MVP — every one of those is a way to lose hours you don't have and adds failure surface for an offline/edge demo.

---

## 4. The demo experiment: "LED Circuit Continuity Test"

This stands in for a real payload-rack science procedure (e.g. assembling and verifying a sensor package) but uses parts you can buy for under ₹300 / $5 and set up on a table in front of a webcam. It has clean, visually distinct objects, clear hand-object interactions, an unambiguous linear sequence, a natural "failure" step (LED doesn't light), and a natural "out of order" trap (connecting the battery before the LED is seated is a real, meaningful protocol violation, exactly like activating power before an instrument is seated in a real experiment).

**Materials (all cheap/home-brewable):**
- 1 small breadboard
- 1 LED (any color)
- 1 resistor (220Ω–330Ω, any color-banded resistor works, doesn't need to be exact for a demo)
- 2 jumper wires (different colors, e.g. red and black, to help the detector distinguish them)
- 1 coin-cell battery (CR2032) or a AA-battery-in-holder
- 1 pair of nitrile/latex gloves (also makes "hands" visually distinct from bare skin for the pose model, and mirrors real astronaut procedure of gloving up before an experiment)
- A plain, high-contrast table surface (e.g. dark cloth) so small components stand out for detection

**The 8-step protocol (this exact list is what the FSM encodes):**

1. **Glove-up** — operator puts on both gloves. (Detected via: hand landmark region color/texture change, or simplest MVP proxy: operator holds gloves up to camera briefly, detected as "glove" object near hand, then hands covered.)
2. **Pick up breadboard** — breadboard object detected, hand-object proximity triggers "picked up," then placed in the designated work zone (a taped rectangle on the table = a fixed ROI in frame).
3. **Insert resistor into breadboard** — resistor object transitions from "in hand" to "stationary inside breadboard ROI."
4. **Insert LED into breadboard, adjacent to resistor** — same detection pattern for the LED object, must occur *after* step 3 (an LED inserted before the resistor is flagged out-of-order — mirrors real "don't power/seat sequence" violations).
5. **Connect jumper wire A (e.g. red) from breadboard to battery holder positive rail** — wire object goes from "in hand" to "spanning two ROIs" (breadboard ROI and battery-holder ROI).
6. **Connect jumper wire B (black) from breadboard to battery holder negative rail** — same pattern, second wire, must be step 6 not step 5 (order between the two wires can be treated as flexible or strict depending on how strict you want the demo — recommend strict, since it's a better demo of "out-of-order" detection).
7. **Insert/seat the battery into the holder** — battery object transitions to "seated in holder ROI." This is the step most demo-worthy: seat it *before* both wires are connected and the FSM should immediately flag "step 7 performed early / step 5-6 skipped" with a voice alert.
8. **Observe and confirm LED state, then remove battery** — a short dwell time (e.g. 3 seconds) with battery seated and both wires connected is logged as "circuit test: PASS" (if you want a visual/optical confirmation the LED is lit, see the optional CV addendum below); operator then removes the battery, which is logged as "experiment concluded, powered down."

**Optional CV addendum (only if time remains):** detect LED "lit" state via a simple brightness/saturation threshold in the small ROI around the LED bounding box, comparing frame brightness before/after battery seating. This lets the system log an actual PASS/FAIL outcome, not just "steps completed," directly satisfying the brief's "structured text file of conducted steps with outcomes/status."

**Deliberate demo failure modes to rehearse on stage:**
- Skip step 3 (resistor) and go straight to LED → system voice-alerts "Step skipped: resistor insertion not detected before LED insertion."
- Seat the battery (step 7) right after step 4, before either wire is connected → system voice-alerts "Out-of-sequence: battery seated before required connections (steps 5, 6) are complete."

---

## 5. Step sequence definition (data-driven, not hardcoded)

The FSM must read the experiment definition from an external JSON file, not from hardcoded Python — this is what makes the system generalizable to other experiments, which is worth calling out explicitly to judges.

```json
{
  "experiment_id": "led_circuit_continuity_test",
  "display_name": "LED Circuit Continuity Test",
  "objects": ["glove", "breadboard", "resistor", "led", "wire_red", "wire_black", "battery"],
  "rois": {
    "work_zone": [x1, y1, x2, y2],
    "battery_holder": [x1, y1, x2, y2]
  },
  "steps": [
    {"id": 1, "name": "glove_up", "requires_objects": ["glove"], "event": "hands_gloved", "voice_prompt": "Step 1: put on gloves."},
    {"id": 2, "name": "place_breadboard", "requires_objects": ["breadboard"], "event": "object_in_roi:breadboard:work_zone", "voice_prompt": "Step 2: place the breadboard in the work zone."},
    {"id": 3, "name": "insert_resistor", "requires_objects": ["resistor"], "event": "object_stationary_in_roi:resistor:work_zone", "voice_prompt": "Step 3: insert the resistor."},
    {"id": 4, "name": "insert_led", "requires_objects": ["led"], "event": "object_stationary_in_roi:led:work_zone", "depends_on": [3], "voice_prompt": "Step 4: insert the LED."},
    {"id": 5, "name": "connect_wire_positive", "requires_objects": ["wire_red"], "event": "object_spans_rois:wire_red:work_zone,battery_holder", "depends_on": [4], "voice_prompt": "Step 5: connect the red wire."},
    {"id": 6, "name": "connect_wire_negative", "requires_objects": ["wire_black"], "event": "object_spans_rois:wire_black:work_zone,battery_holder", "depends_on": [5], "voice_prompt": "Step 6: connect the black wire."},
    {"id": 7, "name": "seat_battery", "requires_objects": ["battery"], "event": "object_stationary_in_roi:battery:battery_holder", "depends_on": [5, 6], "voice_prompt": "Step 7: seat the battery."},
    {"id": 8, "name": "confirm_and_power_down", "requires_objects": ["battery"], "event": "dwell_then_object_removed:battery:battery_holder:3s", "depends_on": [7], "voice_prompt": "Step 8: confirm LED state, then remove the battery."}
  ]
}
```

The coding agent should implement a generic `Event` schema (`object_in_roi`, `object_stationary_in_roi`, `object_spans_rois`, `dwell_then_object_removed`, plus a `hands_gloved` special case) emitted by the perception layer, so the FSM never needs to know about CV internals — clean separation of concerns.

---

## 6. Perception pipeline

1. **Capture:** OpenCV `VideoCapture(0)` at 640×480 @ 15–30fps (lower resolution = faster inference on CPU; upscale only for recording/streaming if needed).
2. **Object detection:** YOLOv8n/YOLO11n fine-tuned on the 7 custom classes above (`glove`, `breadboard`, `resistor`, `led`, `wire_red`, `wire_black`, `battery`). Run every frame or every 2nd frame if CPU-bound.
3. **Hand tracking:** MediaPipe HandLandmarker on the same frame, giving 21 landmarks per hand → compute a hand bounding region as the convex hull of landmarks, used for "in hand" proximity checks.
4. **Interaction inference (rule-based):**
   - `in_hand`: object bbox IoU with hand region > threshold, or centroid distance below threshold, for N consecutive frames.
   - `stationary`: object centroid movement below threshold for M consecutive frames *and* not currently `in_hand`.
   - `in_roi` / `spans_rois`: object bbox centroid (or both endpoints for wires) falls inside one or more of the pre-defined ROI polygons set up at experiment start (drawn once on the first frame via the GUI, saved to the experiment JSON).
5. **Event emission:** a small state tracker per object (a simple per-object FSM: `absent → in_hand → placed/stationary → (optionally) removed`) emits discrete events onto a queue consumed by the experiment-level FSM in section 7.

This two-layer FSM design (per-object micro-state + experiment-level macro-state) is what keeps the logic simple to write and simple to debug live.

---

## 7. Experiment-level sequence validation FSM

Pseudocode for the core logic the agent should implement:

```python
class ExperimentValidator:
    def __init__(self, step_definitions):
        self.steps = step_definitions        # ordered list from JSON
        self.completed = set()                # step ids completed
        self.expected_next = self._first_available_steps()
        self.log = []

    def on_event(self, event, timestamp):
        matched_step = self._match_event_to_step(event)
        if not matched_step:
            return  # noise / irrelevant event, ignore

        if matched_step.id in self.completed:
            return  # duplicate, ignore

        deps = matched_step.get("depends_on", [])
        if all(d in self.completed for d in deps):
            # correct, in-order step
            self.completed.add(matched_step.id)
            self._log(matched_step, status="OK", timestamp=timestamp)
            self._announce_next()
        else:
            missing = [d for d in deps if d not in self.completed]
            # out-of-order / skipped-prerequisite step
            self._log(matched_step, status="OUT_OF_SEQUENCE", timestamp=timestamp,
                       detail=f"missing prerequisite steps: {missing}")
            self._voice_alert(
                f"Alert. {matched_step['name']} attempted before required step(s) "
                f"{missing} were completed."
            )

    def _announce_next(self):
        nxt = self._first_available_steps() - self.completed
        if nxt:
            self._voice_say(self.steps_by_id[min(nxt)]["voice_prompt"])
        else:
            self._voice_say("Experiment sequence complete.")
```

A **skipped step** (as opposed to out-of-order) should be detected via a timeout: if `expected_next` step has not fired an event within a configurable window (e.g. 45s) while a *later* step's prerequisite object is being manipulated, flag "possible skip" — but the simplest, demo-safe version of "skip detection" is exactly what's shown above: any step whose dependencies aren't satisfied when it fires is, by definition, either out-of-order or has a skipped prerequisite, and the alert message should say which prerequisite(s) are missing. Don't over-build a separate skip-detector; this dependency-graph check already covers both required behaviors ("skipped" and "out of sequence") from the brief.

---

## 8. Voice alert module

- Use `pyttsx3.init()` once at startup, run `engine.say(text); engine.runAndWait()` on a **dedicated thread** with a queue, so voice never blocks the capture/inference loop.
- Two message classes:
  - **Guidance** (calm voice, normal priority): "Step 3: insert the resistor."
  - **Alert** (should be visually and audibly distinct — e.g. prefix "Alert." and also flash a red banner in the GUI): "Alert. Battery seated before required connections are complete."
- Rate-limit repeated alerts for the same condition (don't spam voice if the invalid state persists across many frames) — fire once per state transition into an alert condition, not once per frame.

---

## 9. Structured log output

Write one JSON object per line to `logs/<experiment_id>_<session_timestamp>.jsonl` — lightweight, human-readable, trivially parseable by any downstream tool (this satisfies "timestamped and structured lightweight text file of the conducted steps with outcomes/status").

```json
{"timestamp": "2026-09-16T10:22:41.203Z", "step_id": 3, "step_name": "insert_resistor", "status": "OK"}
{"timestamp": "2026-09-16T10:23:05.880Z", "step_id": 7, "step_name": "seat_battery", "status": "OUT_OF_SEQUENCE", "detail": "missing prerequisite steps: [5, 6]"}
{"timestamp": "2026-09-16T10:24:12.010Z", "step_id": 8, "step_name": "confirm_and_power_down", "status": "PASS", "detail": "LED brightness delta above threshold"}
```

At session end, also emit a one-line summary object: total steps expected, steps completed OK, steps flagged, overall PASS/FAIL, session duration.

---

## 10. Video: local storage + IP streaming

- **Local storage:** `cv2.VideoWriter` writing MP4 (`mp4v` or `avc1` fourcc) to `recordings/<experiment_id>_<timestamp>.mp4`, running on the capture thread so it never drops frames regardless of streaming status.
- **Network streaming:** spawn an `ffmpeg` subprocess at startup: read raw frames via stdin pipe, encode, and push out UDP to `--stream-ip`/`--stream-port` (e.g. `udp://<ip>:<port>`) or RTSP if a receiver supports it. Wrap the subprocess call in a try/except and a watchdog thread — if the stream target is unreachable, log a warning and continue local recording; streaming must be best-effort, never a blocking dependency. For the demo, a second laptop running VLC pointed at `udp://@:<port>` is a fully sufficient "receiving station" to prove the capability.
- Keep streaming resolution/bitrate low (e.g. 480p, 500kbps) to genuinely reflect "restricted bandwidth to Earth" framing from the brief — this is also a talking point for judges.

---

## 11. GUI

Single PyQt window, three panels:

1. **Left/main:** live video feed with overlays — bounding boxes for detected objects, hand skeleton, ROI rectangles, and a status ribbon (current step / next expected step).
2. **Top-right:** big current-status card — "Next: Step 5 — Connect red wire" in green, switching to a red "ALERT" banner with the alert text when a violation fires.
3. **Bottom-right:** scrolling log panel mirroring the JSONL file in human-readable form, plus PASS/FAIL/step counters.

Keep GUI updates on a `QTimer` pulling from the same event queue the FSM consumes, rather than the inference thread writing directly to Qt widgets (Qt widgets aren't thread-safe) — this is a real bug class the agent should avoid: **inference/logic threads only push to queues; only the main GUI thread touches Qt widgets.**

---

## 12. Optional stretch: orientation-agnostic 3D HMR

Real implementation (only attempt if steps 1–11 are done and rock-solid with hours to spare): use a pretrained 3D Human Mesh Recovery model such as HMR2.0 / 4D-Humans (open weights, runs offline) to estimate the operator's body mesh in a payload-rack-relative frame rather than a floor-relative frame, by calibrating the rack's ROI/plane at experiment start as the reference "up," and re-projecting the estimated mesh orientation against that plane instead of gravity.

**Realistic hackathon-demo fallback (recommended):** don't claim true orientation-agnostic HMR. Instead, calibrate the "up" vector once from the operator-defined `work_zone` ROI rectangle at experiment start (its top edge = reference "up" instead of the camera's vertical axis), and run all pose/ROI geometry relative to that calibrated frame. This honestly demonstrates the *concept* (tracking relative to the payload rack rather than the floor) without requiring a full zero-gravity mesh-recovery model, and is truthful to describe on stage as "the orientation-reference calibration layer that a full microgravity HMR model would plug into."

---

## 13. Dataset & training plan (do this first, it gates everything else)

1. Set up the physical rig (breadboard + components) on the demo table.
2. Record 3–5 minutes of video performing the full sequence 8–10 times, varying hand position, lighting, and slight camera angle changes.
3. Extract ~80–120 frames total (every ~2 seconds), label bounding boxes for the 7 object classes (`glove`, `breadboard`, `resistor`, `led`, `wire_red`, `wire_black`, `battery`) using Roboflow (free, exports directly to YOLO format) or `labelImg`.
4. Split 80/20 train/val, fine-tune `yolov8n.pt` for 50–100 epochs (a few minutes on a laptop GPU, ~15–30 min on CPU) — `yolo detect train data=data.yaml model=yolov8n.pt epochs=80 imgsz=640`.
5. Sanity-check the trained weights against a fresh 1-minute clip before wiring into the full app.
6. MediaPipe hand/pose models need no training — ship the pretrained task bundles directly.

Budget roughly a third of total hackathon time for this step; it's the one piece that can't be rushed at the very end.

---

## 14. Project structure

```
har-space-assistant/
├── config/
│   └── led_circuit_continuity_test.json      # step definition (section 5)
├── models/
│   └── yolo_custom.pt                        # fine-tuned weights
├── src/
│   ├── capture.py          # camera capture thread
│   ├── perception.py       # YOLO + MediaPipe inference, event emission
│   ├── object_tracker.py   # per-object micro-FSM (in_hand/stationary/in_roi)
│   ├── validator.py        # experiment-level FSM (section 7)
│   ├── voice.py            # pyttsx3 wrapper, threaded queue
│   ├── logger.py           # JSONL writer
│   ├── streamer.py         # ffmpeg subprocess wrapper + local VideoWriter
│   ├── gui.py               # PyQt main window
│   └── main.py              # wires everything together, CLI args
├── logs/
├── recordings/
├── requirements.txt
└── README.md
```

---

## 15. Suggested build order for the hackathon clock

1. Rig + dataset capture + labeling + YOLO fine-tune (do this in parallel with #2 below if team size allows).
2. `capture.py` + `perception.py` — get boxes and hand landmarks drawn on screen, verified visually, before anything else.
3. `object_tracker.py` — per-object in_hand/stationary/in_roi micro-states, verified by printing events to console.
4. `validator.py` against the JSON step file — verified by manually triggering events / running the experiment slowly and watching console output match expectations.
5. `voice.py` + `logger.py` — bolt onto the validator's `_log` / `_voice_alert` calls.
6. `streamer.py` — local recording first (must-have), network streaming second (nice-to-have, time-boxed).
7. `gui.py` — last, once the underlying pipeline is proven via console output; the GUI is a thin presentation layer over the same event queue.
8. Rehearse the two deliberate-failure demo beats from section 4 at least twice before presenting.

---

## 16. Success criteria for the demo

- Full 8-step sequence performed correctly → all steps logged `OK`, voice announces each next step, final summary shows PASS.
- Skipped-prerequisite run (e.g. resistor skipped) → immediate distinct voice alert naming the missing step, logged as `OUT_OF_SEQUENCE`.
- Out-of-order run (battery seated early) → immediate distinct voice alert, logged as `OUT_OF_SEQUENCE` with correct missing-dependency detail.
- Recording file exists on disk after the run, playable, matches the session.
- A second machine on the network can open the live UDP/RTSP stream during the run.
- GUI shows live overlays, current/next step, and the alert banner firing in sync with the voice alert.
- Entire app launched with zero network calls after model weights are loaded (verifiable by running with Wi-Fi off).
