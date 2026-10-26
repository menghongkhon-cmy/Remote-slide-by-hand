
# 🖐️ HandSlide Controller
### Control Your Presentation With Your Hands & Smile 😊

**HandSlide Controller** is a Python desktop application that allows you to control PowerPoint presentations and PDF documents using hand gestures and facial expressions through your webcam.

No mouse. No keyboard. Just your hands and your smile!

Built with **Python, OpenCV, MediaPipe, Tkinter, PyAutoGUI, and PyMuPDF**.

> ⚠️ **Development note:** Hand gesture features are implemented in the existing project. Smile recognition is a proposed new feature and requires additional implementation before it can be used.

---

## 🌟 Features

### 🖐️ Hand Gesture Control
- ✋ Open palm → Next slide
- 👉 Point right → Next slide
- 👈 Point left → Previous slide
- ✊ Fist → Pause / no action
- 👍 Thumbs up → Enable gesture control
- Track 21 hand landmarks using MediaPipe
- Real-time gesture recognition
- Gesture confidence detection

### 😊 Smile Recognition (New Feature)
- 😊 Smile → Previous slide
- Detect facial landmarks using webcam
- Estimate smile confidence from mouth landmarks
- Adjustable smile detection sensitivity
- Hold-to-trigger to prevent accidental actions
- Cooldown protection after changing a slide
- Release-before-repeat so one smile cannot skip multiple slides

**Important:** The smile feature must be implemented with a MediaPipe face landmark detector or equivalent facial-expression classifier.

### 🖥️ Presentation Management
- Open `.pptx`, `.ppt`, and `.pdf` files
- Automatically start PowerPoint slideshow
- Built-in PDF viewer using PyMuPDF
- Next / Previous slide navigation
- Keyboard navigation
- Fullscreen presentation support
- Presentation files are never modified

### 📷 Smart Webcam
- Live webcam preview
- Hand landmark visualization
- Facial landmark visualization (when face tracking is implemented)
- Current gesture display
- Smile confidence indicator (planned)
- Current action and FPS overlay
- Camera connection status

### 🛡️ Safety & Stability
- Gesture cooldown
- Gesture stabilization
- Hold-to-trigger recognition
- Release-before-repeat protection
- ESC emergency stop
- Automatic camera release
- Error handling
- Debug mode

---

## 📂 Project Structure

```text
HandSlide-Controller/
│
├── main.py
├── gesture_detector.py
├── face_detector.py          # NEW: Smile detection
├── powerpoint_controller.py
├── pdf_viewer.py
├── ui.py
├── config.py
├── requirements.txt
├── README.md
│
├── assets/
│   └── icon.png
│
└── hand_landmarker.task
```

### File Responsibilities

| File | Description |
|------|-------------|
| `main.py` | Main application, webcam processing, gesture coordination |
| `gesture_detector.py` | Hand detection and gesture recognition |
| `face_detector.py` | New module for face landmarks and smile recognition |
| `powerpoint_controller.py` | PowerPoint keyboard controls |
| `pdf_viewer.py` | Built-in PDF viewer |
| `ui.py` | Modern Tkinter desktop interface |
| `config.py` | Application configuration |
| `requirements.txt` | Required Python libraries |
| `assets/icon.png` | Application icon |

---

## ⚙️ Installation

### 1. Requirements

- Windows 10 or Windows 11
- Python 3.10–3.12
- Working webcam
- Microsoft PowerPoint for PowerPoint presentations
- Internet connection for first-time hand model download

### 2. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/HandSlide-Controller.git

cd HandSlide-Controller
```

Replace `YOUR_USERNAME` with your actual GitHub username.

Alternatively, download the project ZIP and extract it.

### 3. Create a Virtual Environment

```bash
python -m venv venv
```

### 4. Activate the Environment

**Windows PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

**Windows Command Prompt:**

```cmd
venv\Scripts\activate
```

### 5. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

Typical libraries used by the project:

- `opencv-python`
- `mediapipe`
- `numpy`
- `Pillow`
- `pyautogui`
- `PyMuPDF`
- `pygetwindow`

The existing requirements file should remain the source of truth for compatible dependency versions.

### 6. Run the Application

```bash
python main.py
```

The HandSlide Controller interface should appear.

---

## 🚀 How to Use HandSlide Controller

### Step 1: Connect Your Camera 📷

Make sure your webcam is connected and working.

Open the application:

```bash
python main.py
```

The webcam preview should appear.

Look for:

```text
Camera: CONNECTED ✅
Hand Detection: READY ✅
Gesture Control: DISABLED
```

The exact labels depend on your UI implementation.

### Step 2: Choose Your Presentation 📂

Click:

**📂 CHOOSE PRESENTATION FILE**

Or press:

```text
Ctrl + O
```

Select a supported file:

```text
my_presentation.pptx
my_slides.ppt
my_document.pdf
```

PowerPoint files open in Microsoft PowerPoint.

PDF files open in the built-in PDF viewer.

### Step 3: Start Presentation ▶️

After choosing a file, the application displays a countdown:

```text
3...
2...
1...
GO! 🚀
```

The presentation begins and gesture control becomes active.

If you have already chosen a file, click **START / RESTART** to present it again.

### Step 4: Position Yourself Correctly

For reliable recognition:

1. Stand approximately 40–100 cm from the webcam.
2. Make sure your hand is fully visible.
3. Face the webcam when using smile control.
4. Use good lighting.
5. Avoid covering your mouth.
6. Keep your background reasonably clear.

### Step 5: Control Your Presentation

Use the following gestures.

| Gesture | Action | Instructions |
|---------|--------|--------------|
| ✋ Open palm | Next slide | Show all five fingers for about 1 second |
| 👉 Point right | Next slide | Point your index finger right for about 0.5 seconds |
| 👈 Point left | Previous slide | Point your index finger left for about 0.5 seconds |
| 😊 Smile | Previous slide | Smile clearly toward the webcam for about 1 second |
| ✊ Fist | No action | Make a fist to rest safely |
| 👍 Thumbs up | Enable control | Raise your thumb while other fingers remain folded |

> 😊 **Smile-to-Previous is a planned feature until the face detector and controller integration are implemented.**

### Step 6: Stop Presentation Control

Click:

**⏹ STOP CONTROL**

Or press:

```text
ESC
```

This disables gesture control.

The webcam preview can continue running.

Press `Q` while the HandSlide application window is focused to quit.

---

## 😊 How Smile Recognition Should Work

The new smile recognition feature will allow users to move backward through slides without raising their hands.

### Example

Imagine you are presenting Slide 5.

```text
Current Slide: 5

        😊
    You Smile
         |
         v
 Webcam Detects Face
         |
         v
 Smile Confidence Check
         |
         v
 Hold for 1 Second
         |
         v
 Cooldown Check
         |
         v
 Previous Slide
         |
         v
 Current Slide: 4
```

### Smile Recognition Logic

1. The webcam captures frames.
2. MediaPipe detects face landmarks.
3. The smile detector calculates a smile score.
4. The score must exceed the configured threshold.
5. The smile must remain stable for the required hold time.
6. Presentation control must be enabled.
7. The cooldown period must have expired.
8. The controller sends a previous-slide command.
9. A smile release is required before another smile action.

This prevents one continuous smile from repeatedly moving through slides.

### Example Configuration

Add settings like these to `config.py` when implementing smile recognition:

```python
# Smile recognition settings

ENABLE_SMILE_DETECTION = True

SMILE_ACTION = "PREVIOUS"

SMILE_CONFIDENCE_THRESHOLD = 0.75

SMILE_HOLD_TIME = 1.0

SMILE_COOLDOWN = 2.0

REQUIRE_SMILE_RELEASE = True
```

These are proposed configuration values, not existing settings.

The smile confidence threshold needs calibration against the scoring method implemented in `face_detector.py`.

### Recommended Detection Method

Use **MediaPipe Face Landmarker** to locate facial landmarks around the mouth.

Possible measurements include:

- Mouth width relative to face width
- Changes in the mouth corners
- Mouth curvature
- Smile-related facial blendshape scores, when supported

A combined score is generally more reliable than measuring mouth width alone.

For a better user experience, the smile detector should establish a neutral baseline for the presenter when possible.

---

## 🎮 Keyboard Controls

| Key | Action |
|-----|--------|
| `→` | Next slide |
| `←` | Previous slide |
| `Ctrl + O` | Choose presentation file |
| `ESC` | Emergency stop of gesture control |
| `Q` | Quit application when focused |
| `F` | Toggle PDF fullscreen |
| `F11` | Toggle PDF fullscreen |

**Note:** ESC is also commonly used by presentation viewers to exit fullscreen, so its exact behavior depends on which window receives the key.

---

## ⚙️ Configuration

Existing hand gesture configuration can be adjusted in `config.py`.

```python
GESTURE_COOLDOWN = 1.2

STABLE_TIME = 0.5

HOLD_TIMES = {
    "OPEN_PALM": 1.0
}

CONFIDENCE_THRESHOLD = 0.7

CAMERA_INDEX = 0

REQUIRE_RELEASE_BETWEEN_TRIGGERS = True

DEBUG = False
```

### Gesture Action Mapping

Example:

```python
GESTURE_ACTIONS = {
    "OPEN_PALM": "NEXT",
    "POINT_RIGHT": "NEXT",
    "POINT_LEFT": "PREVIOUS",
    "FIST": None,
    "THUMBS_UP": "ENABLE"
}
```

After adding a smile event to the controller, the intended mapping is:

```python
SMILE_ACTION = "PREVIOUS"
```

Smile detection requires a separate face recognition pipeline; adding `"SMILE"` to the hand classifier alone will not detect facial expressions.

---

## 🧠 How the System Works

### Hand Gesture Pipeline

```text
Webcam
  |
  v
OpenCV
  |
  v
MediaPipe Hand Landmarker
  |
  v
21 Hand Landmarks
  |
  v
Gesture Classification
  |
  v
Gesture Stabilizer
  |
  v
Action Controller
  |
  v
PowerPoint / PDF Viewer
```

### Smile Recognition Pipeline (Planned)

```text
Webcam
  |
  v
OpenCV
  |
  v
MediaPipe Face Landmarker
  |
  v
Facial Landmark Analysis
  |
  v
Smile Detection
  |
  v
Hold-Time Verification
  |
  v
Cooldown & Release Check
  |
  v
Previous Slide Command
  |
  v
PowerPoint / PDF Viewer
```

### Important Integration Rules

Hand and facial detectors should process the same camera frames to avoid opening the webcam twice.

The controller should:

- Prioritize emergency stop commands.
- Ignore smile events while control is disabled.
- Avoid duplicate actions when a hand gesture and a smile are detected together.
- Use an appropriate cooldown between slide changes.
- Handle failures without freezing the interface.
- Release webcam resources when the application closes.

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| Camera not available | Close other camera applications and check Windows permissions |
| No hand detected | Improve lighting and show your full hand |
| Hand model failed | Check the model file and internet connection |
| Gestures not responding | Check control status and confidence threshold |
| Slides move too quickly | Increase cooldown and enable release protection |
| PowerPoint not responding | Focus the slideshow window |
| PDF not opening | Verify PyMuPDF is installed |
| Low FPS | Reduce camera resolution and avoid expensive processing |
| Smile not detected | Confirm the face detector feature is implemented and enabled |
| Smile triggers accidentally | Increase smile threshold or hold time |
| Smile changes too many slides | Enable release-before-repeat and increase cooldown |
| Facial landmarks not visible | Face the webcam and improve lighting |
| Camera freezes | Check for competing webcam processes and worker thread errors |

---

## ✅ Testing Checklist

### Camera
- [ ] Webcam opens correctly
- [ ] Hand landmarks appear
- [ ] Camera status displays correctly
- [ ] Camera closes properly

### Hand Gestures
- [ ] Open palm detected
- [ ] Point right detected
- [ ] Point left detected
- [ ] Fist detected
- [ ] Thumbs up detected
- [ ] Gesture confidence works

### Smile Recognition (New)
- [ ] Face Landmarker initializes
- [ ] Facial landmarks detected
- [ ] Neutral face does not trigger
- [ ] Smile correctly detected
- [ ] Smile changes to previous slide
- [ ] Smile hold time works
- [ ] Smile cooldown works
- [ ] Smile release requirement works
- [ ] Smiling continuously does not skip slides
- [ ] Face disappearance resets the smile state
- [ ] Hand and smile events do not trigger duplicate actions

### PowerPoint
- [ ] PowerPoint file opens
- [ ] Slideshow starts
- [ ] Next slide works
- [ ] Previous slide works
- [ ] Stop control works

### PDF
- [ ] PDF file opens
- [ ] Next page works
- [ ] Previous page works
- [ ] Fullscreen works
- [ ] PDF navigation responds to gestures

### Safety
- [ ] ESC emergency stop works
- [ ] Cooldown prevents rapid actions
- [ ] Release-before-repeat works
- [ ] No unexpected slide changes
- [ ] Application exits cleanly

---

## 🚀 Future Improvements

- 😊 Smile gesture for previous slide
- 👀 Eye blink control
- ✌️ Two-finger gesture
- 🎤 Voice commands
- 📱 Mobile remote controller
- 🎯 Custom gesture mapping
- 📊 Gesture recognition statistics
- 🌐 Multilingual interface
- 🎨 More modern interface themes
- 🖥️ Multi-monitor presentation control
- ⚡ Improved recognition accuracy

---

## 💻 Technologies Used

| Technology | Purpose |
|------------|---------|
| Python | Main programming language |
| OpenCV | Webcam processing |
| MediaPipe Hands | Hand landmark tracking |
| MediaPipe Face Landmarker | Planned smile detection |
| PyAutoGUI | Keyboard automation |
| Tkinter | Desktop user interface |
| PyMuPDF | PDF rendering |
| NumPy | Numerical operations |
| Pillow | Image handling |

---

## 📌 Important Notes

- This application is designed primarily for Windows 10/11.
- PowerPoint control requires Microsoft PowerPoint.
- PDF presentation uses the application's built-in viewer.
- Internet may be required for first-time model downloads.
- Presentation files are not edited.
- Smile recognition requires implementation and testing before use.
- Gesture recognition accuracy depends on lighting, camera quality, and visibility.

---

## ❤️ Project Vision

HandSlide Controller aims to make presentations more natural, interactive, and accessible.

Instead of relying on a keyboard or mouse, presenters can interact with their slides using simple gestures and, with the proposed upgrade, facial expressions.

**Present smarter. Move freely. Control with a smile. 😊**
