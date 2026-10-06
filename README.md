# 🖐️ HandSlide Controller

**Control Your Presentation With Your Hands**

HandSlide Controller lets you control a PowerPoint presentation with hand gestures seen by your webcam. It tracks your hand with MediaPipe, recognises gestures, and presses the slide keys for you (→ next, ← previous). Nothing is ever changed inside your `.pptx` file.

## Features

- Hand tracking (21 landmarks, one hand) with live drawing on the webcam preview
- Gesture recognition: open palm, pointing left/right, fist, thumbs up
- **Choose a presentation file and present it automatically** (open file, start slideshow, enable gestures)
- Next slide / previous slide / start presentation
- Real-time webcam preview with gesture, confidence, action and FPS overlay
- Gesture history (latest 5 actions)
- Cooldown protection + hold-to-trigger, so one wave never skips five slides
- Modern dark UI with START / STOP buttons and a camera connection indicator
- Safety: ESC emergency stop, Q to quit, camera released on exit
- Debug mode (`DEBUG = True` in `config.py`)

## Project structure

| File | Responsibility |
|---|---|
| `main.py` | Starts everything. Runs the camera/gesture worker thread, applies cooldown, fires actions, draws the camera overlay. |
| `gesture_detector.py` | MediaPipe HandLandmarker (Tasks API) wrapper + model auto-download, finger-state logic, gesture classification, and the `GestureStabilizer` (hold time, cooldown gate, release-before-repeat). |
| `powerpoint_controller.py` | Sends `RIGHT` / `LEFT` / `F5` with PyAutoGUI; checks/focuses the PowerPoint window (Windows). |
| `ui.py` | The Tkinter window only. Draws a snapshot and calls callbacks. |
| `config.py` | All settings: cooldown, thresholds, gesture→action map, colours. |
| `requirements.txt` | Python packages. |
| `assets/icon.png` | Window icon. |

## Installation

Requires **Windows 10/11** and **Python 3.10 – 3.12**. Needs internet on the first run: the app downloads the ~8 MB hand model (`hand_landmarker.task`) next to `main.py` automatically (or download it yourself from the `MODEL_URL` in `config.py`).

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Install:

```bash
pip install -r requirements.txt
```

Run:

```bash
python main.py
```

## Usage

1. Connect your webcam.
2. Run the application (`python main.py`). The camera starts, but **nothing controls PowerPoint yet**.
3. Click **📂 CHOOSE PRESENTATION FILE** (or press `Ctrl+O`) and pick your `.pptx` file.
4. The app opens the file in PowerPoint, waits until it has loaded, shows a 3-2-1-GO countdown on the camera image, presses F5 to start the slideshow, and switches gesture control on. No other clicks needed.
5. Show one hand to the camera, palm facing it, roughly 40-100 cm away.
6. Use the gestures below. Click **⏹ STOP CONTROL** or press **ESC** to switch control off; the webcam preview keeps running.

To present a different file, just click **CHOOSE PRESENTATION FILE** again. **START / RESTART** re-opens the file you already chose. If you have not chosen a file, it works on a presentation you already opened yourself.

## Gestures

| Gesture | Action | How to do it |
|---|---|---|
| ✋ Open palm | Next slide | All five fingers spread. **Hold about 1 second.** |
| 👉 Point right | Next slide | Only the index finger out, aimed to the right. Hold ~0.5 s. |
| 👈 Point left | Previous slide | Only the index finger out, aimed to the left. Hold ~0.5 s. |
| ✊ Fist | Pause / no action | Use it to rest your hand safely. |
| 👍 Thumbs up | Enable control | Fist with thumb pointing up. |

The image is mirrored like a mirror, so pointing to **your** right moves right on screen. Pointing straight up or at the camera is deliberately ignored.

**How it stays stable:** gesture seen → held long enough → cooldown ready → action → cooldown (`GESTURE_COOLDOWN`) → must **release** (lower hand, or change gesture) before the same gesture can fire again. Low-confidence results are shown as `UNKNOWN` and do nothing.

## Keyboard

| Key | Action |
|---|---|
| `→` / `←` | Next / previous slide (brings PowerPoint forward first) |
| `ESC` | Emergency stop of gesture control (works globally on Windows, even while PowerPoint is focused) |
| `Q` | Quit (when the HandSlide window is focused) |

## Customising

All in `config.py`:

- **Cooldown:** `GESTURE_COOLDOWN = 1.2`
- **Hold time:** `STABLE_TIME = 0.5`, and `HOLD_TIMES = {"OPEN_PALM": 1.0}`
- **Change what a gesture does:** edit `GESTURE_ACTIONS`, e.g. `"FIST": "PREVIOUS"`
- **Confidence needed:** `CONFIDENCE_THRESHOLD = 0.7`
- **Other webcam:** `CAMERA_INDEX = 1`
- **Repeat while holding:** `REQUIRE_RELEASE_BETWEEN_TRIGGERS = False`
- **Console logs:** `DEBUG = True / False`
- **Model location / URL:** `MODEL_FILE`, `MODEL_URL`
- **Accuracy tuning:** `FINGER_OPEN_RATIO`, `THUMB_OPEN_DIST_RATIO`, `POINT_MIN_HORIZONTAL`

To add a *new* gesture, write an `is_...` function and add a branch in `detect_hand_gesture()` in `gesture_detector.py`, then add it to `GESTURE_INFO` and `GESTURE_ACTIONS` in `config.py`.

## Troubleshooting

| Problem | Fix |
|---|---|
| "❌ Camera not available" | Close Zoom/Teams/Camera app, check Windows camera privacy settings, try `CAMERA_INDEX = 1`. |
| "Hand tracking initialization failed" | The window now shows the real reason. Usually `hand_landmarker.task` is missing/damaged (delete it; it re-downloads) or no internet on first run. Otherwise use Python 3.10–3.12 and `pip install -U -r requirements.txt`. |
| "PowerPoint may not be the active window" | Click your presentation so it is in front, or use START, which focuses it. |
| Slides do not change | PowerPoint must be the front window. Also check the gesture shows in the panel and cooldown is READY. |
| Gestures flicker / UNKNOWN | Better light, plain background, hand fully in view, palm toward the camera. Tune the thresholds in `config.py`. |
| Thumbs up not recognised | Keep the hand upright, thumb clearly above the fist. |
| Missing package message | `pip install -r requirements.txt` inside the activated venv. |
| Low FPS | Keep `MP_MODEL_COMPLEXITY = 0`, close other camera apps, improve lighting. |

PyAutoGUI has a built-in fail-safe: slamming the mouse into a screen corner cancels key sending.

## Testing checklist

**Camera**
- [ ] Camera opens
- [ ] Hand appears
- [ ] Landmarks appear
- [ ] No-hand state works ("Waiting for hand...")

**Gestures**
- [ ] Open palm detected
- [ ] Fist detected
- [ ] Thumb up detected
- [ ] Pointing detected
- [ ] Left/right detection works

**PowerPoint**
- [ ] Next slide works
- [ ] Previous slide works
- [ ] Start presentation works
- [ ] Stop works
- [ ] ESC emergency stop works

**Stability**
- [ ] Cooldown works
- [ ] No repeated slide skipping
- [ ] Webcam closes correctly
- [ ] Application exits cleanly