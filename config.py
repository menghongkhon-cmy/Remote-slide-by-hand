"""
config.py - central settings for HandSlide Controller.

Everything you might want to tweak lives here. Other modules only READ
these values, so you never have to hunt through the code to change behaviour.
"""

APP_NAME = "HandSlide Controller"
APP_SUBTITLE = "Control Your Presentation With Your Hands"

# ---------------------------------------------------------------------------
# Main settings (the ones you will change most often)
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0            # 0 = default webcam, 1 = second webcam, ...
GESTURE_COOLDOWN = 1.2      # seconds to wait after ANY action before the next one
CONFIDENCE_THRESHOLD = 0.7  # below this a gesture is reported as UNKNOWN (no action)
MAX_HANDS = 1               # only one hand is tracked
DEBUG = True                # True = print gesture/action info to the console

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 30

# ---------------------------------------------------------------------------
# MediaPipe
# ---------------------------------------------------------------------------
MP_DETECTION_CONFIDENCE = 0.7
MP_TRACKING_CONFIDENCE = 0.6
# The hand model file lives next to the scripts. If it is missing or damaged
# the app downloads it automatically (about 8 MB, first run only).
MODEL_FILE = "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

# ---------------------------------------------------------------------------
# Smile detection (smile = previous slide). Uses MediaPipe FaceLandmarker.
# The face model (~4 MB) is downloaded automatically the first time.
# ---------------------------------------------------------------------------
ENABLE_SMILE = True             # False = turn smile control off completely
SMILE_THRESHOLD = 0.5           # 0..1. Lower = triggers on smaller smiles, higher = needs a big smile
FACE_MODEL_FILE = "face_landmarker.task"
FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)

# ---------------------------------------------------------------------------
# Gesture stability / timing
# ---------------------------------------------------------------------------
STABLE_TIME = 0.5                   # a gesture must be held this long to trigger
HOLD_TIMES = {"OPEN_PALM": 1.0, "SMILE": 0.5}   # per-gesture override (open palm ~1 s, smile 0.5 s)
FLICKER_TOLERANCE = 0.2             # ignore very short detection dropouts (seconds)
# True  -> after an action fires, the gesture must be released (hand lowered or
#          gesture changed) before it can fire again. Safest for demos.
# False -> holding the gesture keeps firing once per (cooldown + hold time).
REQUIRE_RELEASE_BETWEEN_TRIGGERS = True
ALLOW_THUMBS_UP_ENABLE = True       # thumbs up can switch gesture control ON
COUNTDOWN_SECONDS = 3
WARNING_DISPLAY_SECONDS = 4.0

# ---------------------------------------------------------------------------
# Gesture -> action mapping. CHANGE GESTURES HERE.
# Available actions: NEXT, PREVIOUS, NONE, ENABLE
# Available gestures: OPEN_PALM, POINT_LEFT, POINT_RIGHT, FIST, THUMBS_UP, SMILE
# ---------------------------------------------------------------------------
GESTURE_ACTIONS = {
    "OPEN_PALM": "NEXT",
    "POINT_RIGHT": "NEXT",
    "POINT_LEFT": "PREVIOUS",
    "FIST": "NONE",
    "THUMBS_UP": "ENABLE",
    "SMILE": "PREVIOUS",       # smile = go back one slide
}

# (emoji, display name) for every gesture the UI can show
GESTURE_INFO = {
    "OPEN_PALM": ("✋", "OPEN PALM"),
    "POINT_LEFT": ("👈", "POINT LEFT"),
    "POINT_RIGHT": ("👉", "POINT RIGHT"),
    "FIST": ("✊", "FIST"),
    "THUMBS_UP": ("👍", "THUMBS UP"),
    "SMILE": ("😊", "SMILE"),
    "UNKNOWN": ("❔", "UNKNOWN"),
    "NONE": ("…", "NONE"),
}

ACTION_LABELS = {
    "NEXT": "NEXT SLIDE",
    "PREVIOUS": "PREVIOUS SLIDE",
    "NONE": "NO ACTION",
    "ENABLE": "ENABLE CONTROL",
}

# ---------------------------------------------------------------------------
# PowerPoint control
# ---------------------------------------------------------------------------
NEXT_KEY = "right"
PREVIOUS_KEY = "left"
START_SLIDESHOW_KEY = "f5"
# File picker ("Choose presentation" button)
PRESENTATION_FILE_TYPES = [
    ("PowerPoint & PDF", "*.pptx *.ppsx *.pptm *.ppt *.pps *.odp *.pdf"),
    ("PowerPoint presentations", "*.pptx *.ppsx *.pptm *.ppt *.pps *.odp"),
    ("PDF documents", "*.pdf"),
    ("All files", "*.*"),
]
# PDF files are shown in the built-in viewer window (see pdf_viewer.py).
PDF_START_FULLSCREEN = False        # False = open in a normal window (press F or F11 for fullscreen)
OPEN_FILE_TIMEOUT = 30.0            # seconds to wait for PowerPoint to open the file
# If True, slide keys are only sent when a presentation window is in front.
# This stops the arrow keys from landing in some other program.
REQUIRE_POWERPOINT_ACTIVE = True
# Window-title keywords that count as "a presentation window".
PRESENTATION_WINDOW_KEYWORDS = ("PowerPoint", "Slide Show", "Impress")

# ---------------------------------------------------------------------------
# Gesture geometry thresholds (tune these if detection feels off)
# ---------------------------------------------------------------------------
# Finger is OPEN when (wrist->tip distance) / (wrist->PIP distance) exceeds this.
FINGER_OPEN_RATIO = 1.1
FINGER_CERTAINTY_SCALE = 0.2
# Thumb is OPEN when (tip->index knuckle distance) / hand size exceeds this.
THUMB_OPEN_DIST_RATIO = 0.5
THUMB_CERTAINTY_SCALE = 0.2
# Thumbs up: thumb tip must be this far above its base (fraction of hand size).
THUMB_UP_MIN_RISE = 0.45
# Pointing: index direction must be mostly horizontal.
POINT_MIN_HORIZONTAL = 0.45         # index length shown sideways / hand size
POINT_DIRECTION_RATIO = 1.2         # |dx| must exceed |dy| * this

# ---------------------------------------------------------------------------
# UI colours
# ---------------------------------------------------------------------------
COLORS = {
    "bg": "#0b0d1a",                 # deep midnight
    "card": "#141831",               # indigo panel
    "card_border": "#262c52",
    "text": "#eef1ff",
    "muted": "#8b92b8",
    "accent": "#7c6cff",             # violet
    "accent_hover": "#9588ff",
    "accent2": "#27d3f5",            # cyan (used for gradients / highlights)
    "success": "#34e0a1",            # mint
    "success_hover": "#5cf0b8",
    "danger": "#ff5d7a",             # coral
    "danger_hover": "#ff8199",
    "warning": "#ffb547",            # amber
    "button_neutral": "#232a52",
    "button_neutral_hover": "#323b6e",
}
# ---------------------------------------------------------------------------
# Web version (app.py / `python main.py --web`)
# ---------------------------------------------------------------------------
WEB_HOST = "127.0.0.1"          # use "0.0.0.0" to open it to other devices on your network
WEB_PORT = 5000                 # the hosting platform's PORT variable overrides this
WEB_DATA_DIR = "data"           # converted slide images are stored here
WEB_MAX_UPLOAD_MB = 100
WEB_KEEP_HOURS = 2              # uploaded decks are deleted after this many hours
WEB_RENDER_SCALE = 1.6          # PDF -> image zoom (higher = sharper but slower)
WEB_PPT_EXPORT_SCALE = 2.0      # PowerPoint export: pixels per point (2.0 = sharp text)
WEB_CONVERT_TIMEOUT = 180       # seconds before a LibreOffice conversion is cancelled
# ---------------------------------------------------------------------------
# Remote helper (`python main.py --remote`): hosted web page -> PowerPoint on this PC
# ---------------------------------------------------------------------------
REMOTE_PORT = 5001              # the web page talks to http://127.0.0.1:<this port>
REMOTE_TOKEN = ""               # "" = a new random 6-digit code every start; or set your own fixed code