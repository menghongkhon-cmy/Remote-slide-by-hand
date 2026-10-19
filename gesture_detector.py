"""
gesture_detector.py - hand tracking and gesture classification.

Responsibilities
----------------
* Run MediaPipe HandLandmarker (Tasks API) on a camera frame.
* Work out which fingers are OPEN / CLOSED from the 21 landmarks.
* Classify the hand as OPEN_PALM, FIST, THUMBS_UP, POINT_LEFT, POINT_RIGHT
  (or UNKNOWN when unsure).
* Detect a SMILE with the MediaPipe FaceLandmarker (mouth-smile blendshapes).
* GestureStabilizer: turns the noisy per-frame result into ONE clean trigger
  (hold time + cooldown + "release before repeat").

All classification uses landmark geometry in PIXEL coordinates, and distances
are compared relative to the hand size, so it works whether your hand is close
to or far from the camera and when it is slightly rotated.
"""

from __future__ import annotations

import math
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import config

Point = Tuple[float, float]


class Gesture:
    """String constants for every gesture the detector can return."""

    OPEN_PALM = "OPEN_PALM"
    FIST = "FIST"
    THUMBS_UP = "THUMBS_UP"
    POINT_LEFT = "POINT_LEFT"
    POINT_RIGHT = "POINT_RIGHT"
    SMILE = "SMILE"       # face smiling (from the FaceLandmarker, not the hand)
    UNKNOWN = "UNKNOWN"   # hand visible but gesture unclear / low confidence
    NONE = "NONE"         # no hand visible


# Gestures that may trigger something (UNKNOWN / NONE never do).
ACTIONABLE_GESTURES = (
    Gesture.OPEN_PALM,
    Gesture.FIST,
    Gesture.THUMBS_UP,
    Gesture.POINT_LEFT,
    Gesture.POINT_RIGHT,
    Gesture.SMILE,
)

# --- MediaPipe landmark indices -------------------------------------------
WRIST = 0
THUMB_MCP, THUMB_IP, THUMB_TIP = 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20

# finger name -> (PIP joint, fingertip)
FOUR_FINGERS: Dict[str, Tuple[int, int]] = {
    "index": (INDEX_PIP, INDEX_TIP),
    "middle": (MIDDLE_PIP, MIDDLE_TIP),
    "ring": (RING_PIP, RING_TIP),
    "pinky": (PINKY_PIP, PINKY_TIP),
}
ALL_FINGERS = ("thumb",) + tuple(FOUR_FINGERS)


class GestureDetectorError(RuntimeError):
    """Raised when MediaPipe cannot be started."""


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_size(pts: Sequence[Point]) -> float:
    """Wrist -> middle-finger knuckle distance. Used to normalise everything."""
    return max(_dist(pts[WRIST], pts[MIDDLE_MCP]), 1e-6)


def _certainty(value: float, threshold: float, scale: float) -> float:
    """0.5 (right on the threshold) .. 1.0 (clearly on one side)."""
    return 0.5 + 0.5 * min(1.0, abs(value - threshold) / scale)


# ---------------------------------------------------------------------------
# Finger states
# ---------------------------------------------------------------------------
@dataclass
class FingerStates:
    """OPEN/CLOSED flag and a 0.5-1.0 certainty for each of the five fingers."""

    is_open: Dict[str, bool]
    certainty: Dict[str, float]

    def four_all_open(self) -> bool:
        return all(self.is_open[name] for name in FOUR_FINGERS)

    def four_all_closed(self) -> bool:
        return not any(self.is_open[name] for name in FOUR_FINGERS)

    def mean_certainty(self, names: Sequence[str]) -> float:
        return sum(self.certainty[n] for n in names) / len(names)


def get_finger_states(pts: Sequence[Point]) -> FingerStates:
    """Decide for each finger whether it is OPEN (extended) or CLOSED (curled)."""
    wrist = pts[WRIST]
    is_open: Dict[str, bool] = {}
    certainty: Dict[str, float] = {}

    # Index..pinky: an extended finger's tip is much farther from the wrist than
    # its middle (PIP) joint; a curled finger's tip folds back toward the palm.
    for name, (pip, tip) in FOUR_FINGERS.items():
        ratio = _dist(wrist, pts[tip]) / max(_dist(wrist, pts[pip]), 1e-6)
        is_open[name] = ratio > config.FINGER_OPEN_RATIO
        certainty[name] = _certainty(
            ratio, config.FINGER_OPEN_RATIO, config.FINGER_CERTAINTY_SCALE
        )

    # Thumb: it moves sideways, so wrist distance does not work. Instead measure
    # how far the thumb tip is from the base of the index finger.
    thumb_ratio = _dist(pts[THUMB_TIP], pts[INDEX_MCP]) / hand_size(pts)
    is_open["thumb"] = thumb_ratio > config.THUMB_OPEN_DIST_RATIO
    certainty["thumb"] = _certainty(
        thumb_ratio, config.THUMB_OPEN_DIST_RATIO, config.THUMB_CERTAINTY_SCALE
    )
    return FingerStates(is_open, certainty)


# ---------------------------------------------------------------------------
# Individual gesture tests (easy to read and modify)
# ---------------------------------------------------------------------------
def is_open_palm(fingers: FingerStates) -> bool:
    """OPEN OPEN OPEN OPEN OPEN."""
    return fingers.is_open["thumb"] and fingers.four_all_open()


def is_thumb_up(fingers: FingerStates, pts: Sequence[Point]) -> bool:
    """Thumb open and pointing upward, other four fingers curled."""
    if not fingers.is_open["thumb"] or not fingers.four_all_closed():
        return False
    # Image y grows downward, so "up" means a SMALLER y for the tip.
    rise = pts[THUMB_MCP][1] - pts[THUMB_TIP][1]
    sideways = abs(pts[THUMB_TIP][0] - pts[THUMB_MCP][0])
    return rise > config.THUMB_UP_MIN_RISE * hand_size(pts) and rise > sideways


def is_fist(fingers: FingerStates, pts: Sequence[Point]) -> bool:
    """All four fingers curled (thumb tucked or resting) and NOT a thumbs up."""
    return fingers.four_all_closed() and not is_thumb_up(fingers, pts)


def _pointing_info(
    fingers: FingerStates, pts: Sequence[Point]
) -> Optional[Tuple[str, float]]:
    """
    If only the index finger is extended and it points sideways, return
    ("LEFT" | "RIGHT", direction_certainty). Otherwise None.

    The direction comes from the real landmark coordinates: the vector from the
    index knuckle (MCP) to the index fingertip. The camera image is mirrored,
    so +x on screen is the user's right hand side.
    """
    others_closed = not (
        fingers.is_open["middle"] or fingers.is_open["ring"] or fingers.is_open["pinky"]
    )
    if not fingers.is_open["index"] or not others_closed:
        return None

    dx = pts[INDEX_TIP][0] - pts[INDEX_MCP][0]
    dy = pts[INDEX_TIP][1] - pts[INDEX_MCP][1]
    horizontal = abs(dx) / hand_size(pts)

    if horizontal < config.POINT_MIN_HORIZONTAL:
        return None  # pointing up/down/at the camera -> not a left/right point
    if abs(dx) < config.POINT_DIRECTION_RATIO * abs(dy):
        return None  # too diagonal to be sure

    direction = "RIGHT" if dx > 0 else "LEFT"
    return direction, _certainty(horizontal, config.POINT_MIN_HORIZONTAL, 0.4)


def pointing_direction(fingers: FingerStates, pts: Sequence[Point]) -> Optional[str]:
    info = _pointing_info(fingers, pts)
    return info[0] if info else None


def is_pointing_left(fingers: FingerStates, pts: Sequence[Point]) -> bool:
    return pointing_direction(fingers, pts) == "LEFT"


def is_pointing_right(fingers: FingerStates, pts: Sequence[Point]) -> bool:
    return pointing_direction(fingers, pts) == "RIGHT"


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------
def detect_hand_gesture(
    pts: Sequence[Point], detection_score: float = 1.0
) -> Tuple[str, float]:
    """
    Classify one hand. Returns (gesture, confidence 0..1).

    Confidence = average certainty of the fingers that decided the gesture,
    multiplied by MediaPipe's own score. If it is below CONFIDENCE_THRESHOLD
    (or nothing matches) the result is UNKNOWN and nothing should happen.
    """
    fingers = get_finger_states(pts)
    four = tuple(FOUR_FINGERS)

    if is_thumb_up(fingers, pts):
        gesture, certainty = Gesture.THUMBS_UP, fingers.mean_certainty(ALL_FINGERS)
    elif is_open_palm(fingers):
        gesture, certainty = Gesture.OPEN_PALM, fingers.mean_certainty(ALL_FINGERS)
    elif (info := _pointing_info(fingers, pts)) is not None:
        direction, dir_certainty = info
        gesture = Gesture.POINT_RIGHT if direction == "RIGHT" else Gesture.POINT_LEFT
        certainty = (fingers.mean_certainty(four) * 4 + dir_certainty) / 5
    elif is_fist(fingers, pts):
        gesture, certainty = Gesture.FIST, fingers.mean_certainty(four)
    else:
        return Gesture.UNKNOWN, 0.0

    confidence = certainty * max(0.0, min(1.0, detection_score))
    if confidence < config.CONFIDENCE_THRESHOLD:
        return Gesture.UNKNOWN, confidence
    return gesture, confidence


# ---------------------------------------------------------------------------
# MediaPipe wrapper (Tasks API - works on old and new MediaPipe versions)
# ---------------------------------------------------------------------------
# The 21 hand joints and which ones are joined by a line (for drawing).
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),            # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),            # index
    (5, 9), (9, 10), (10, 11), (11, 12),       # middle
    (9, 13), (13, 14), (14, 15), (15, 16),     # ring
    (13, 17), (17, 18), (18, 19), (19, 20),    # pinky
    (0, 17),                                   # palm edge
)

# A real hand_landmarker.task is ~7.8 MB. Anything far smaller is a broken file.
MIN_MODEL_BYTES = 1_000_000


def _model_path(filename: str = "") -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename or config.MODEL_FILE)


def _model_ok(path: str) -> bool:
    return os.path.isfile(path) and os.path.getsize(path) >= MIN_MODEL_BYTES


def _ensure_model(filename: str = "", url: str = "") -> str:
    """Return the path of a valid model file, downloading it if needed."""
    filename = filename or config.MODEL_FILE
    url = url or config.MODEL_URL
    path = _model_path(filename)
    if _model_ok(path):
        return path

    if os.path.exists(path):
        print(f"[INFO] {filename} is damaged or incomplete - downloading a fresh copy.", flush=True)
    else:
        print(f"[INFO] {filename} not found - downloading it (one time, ~8 MB)...", flush=True)

    tmp = path + ".part"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        if len(data) < MIN_MODEL_BYTES:
            raise ValueError("downloaded file is too small")
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)  # atomic: never leaves a half-written model behind
    except Exception as exc:  # noqa: BLE001
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise GestureDetectorError(
            f"Hand model file missing or invalid, and the download failed ({exc}).\n\n"
            f"Download it manually from:\n{url}\n"
            f"and save it as:\n{path}"
        ) from exc
    print("[INFO] Model downloaded.", flush=True)
    return path


@dataclass
class HandResult:
    hand_detected: bool
    gesture: str = Gesture.NONE
    confidence: float = 0.0
    landmarks: Optional[List[Point]] = None  # 21 (x, y) points in pixels
    smile_score: float = 0.0                 # 0..1 average of the two mouth-smile blendshapes


class GestureDetector:
    """Wraps MediaPipe HandLandmarker: frame in -> HandResult out."""

    def __init__(self) -> None:
        model_path = _ensure_model()  # raises GestureDetectorError with a clear message
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions, vision

            self._cv2 = cv2
            self._mp = mp
            # Load from bytes: avoids Windows problems with non-ASCII folder names.
            with open(model_path, "rb") as handle:
                model_bytes = handle.read()
            options = vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_buffer=model_bytes),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=config.MAX_HANDS,
                min_hand_detection_confidence=config.MP_DETECTION_CONFIDENCE,
                min_hand_presence_confidence=config.MP_DETECTION_CONFIDENCE,
                min_tracking_confidence=config.MP_TRACKING_CONFIDENCE,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
            self._last_ts_ms = 0
        except Exception as exc:  # noqa: BLE001 - we want to report anything
            raise GestureDetectorError(
                f"Hand tracking initialization failed.\n({type(exc).__name__}: {exc})"
            ) from exc
        self._face = self._create_face_landmarker()  # None if smile control is off / unavailable

    def process(self, frame_bgr) -> HandResult:
        """Detect the hand in a BGR frame and classify the gesture."""
        rgb = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        # VIDEO mode needs strictly increasing timestamps (milliseconds).
        ts_ms = int(time.monotonic() * 1000)
        if ts_ms <= self._last_ts_ms:
            ts_ms = self._last_ts_ms + 1
        self._last_ts_ms = ts_ms

        result = self._detect_hand(image, ts_ms, frame_bgr.shape)

        # A smile only counts when the hand is not making a real gesture, so a
        # fist / pointing / open palm always wins over the face.
        if self._face is not None and result.gesture in (Gesture.NONE, Gesture.UNKNOWN):
            result.smile_score = self._smile_score(image, ts_ms)
            if result.smile_score >= config.SMILE_THRESHOLD:
                result.gesture = Gesture.SMILE
                result.confidence = result.smile_score
        return result

    def _detect_hand(self, image, ts_ms: int, shape) -> HandResult:
        results = self._landmarker.detect_for_video(image, ts_ms)
        if not results.hand_landmarks:
            return HandResult(hand_detected=False)

        score = 1.0
        if results.handedness and results.handedness[0]:
            # Used as a rough "how sure is MediaPipe about this hand" signal.
            score = results.handedness[0][0].score

        height, width = shape[:2]
        pts = [(lm.x * width, lm.y * height) for lm in results.hand_landmarks[0]]
        gesture, confidence = detect_hand_gesture(pts, score)
        return HandResult(True, gesture, confidence, pts)

    # -- smile (FaceLandmarker blendshapes) ----------------------------------
    def _create_face_landmarker(self):
        """Create the face model used for smile detection. Never raises: on any
        problem smile control is simply disabled and the hand gestures still work."""
        if not getattr(config, "ENABLE_SMILE", True):
            return None
        try:
            from mediapipe.tasks.python import BaseOptions, vision

            path = _ensure_model(config.FACE_MODEL_FILE, config.FACE_MODEL_URL)
            with open(path, "rb") as handle:
                data = handle.read()
            options = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_buffer=data),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_face_blendshapes=True,
            )
            return vision.FaceLandmarker.create_from_options(options)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Smile control disabled: {exc}", flush=True)
            return None

    def _smile_score(self, image, ts_ms: int) -> float:
        try:
            result = self._face.detect_for_video(image, ts_ms)
        except Exception:  # noqa: BLE001
            return 0.0
        if not result.face_blendshapes:
            return 0.0
        scores = {c.category_name: c.score for c in result.face_blendshapes[0]}
        return (scores.get("mouthSmileLeft", 0.0) + scores.get("mouthSmileRight", 0.0)) / 2.0

    def draw(self, frame_bgr, result: HandResult) -> None:
        """Draw the 21 landmarks and connections onto the frame (in place)."""
        if not result.landmarks:
            return
        cv2 = self._cv2
        pixel = [(int(x), int(y)) for x, y in result.landmarks]
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame_bgr, pixel[a], pixel[b], (255, 255, 255), 2, cv2.LINE_AA)
        for point in pixel:
            cv2.circle(frame_bgr, point, 4, (0, 140, 255), -1, cv2.LINE_AA)

    def close(self) -> None:
        for model in (getattr(self, "_landmarker", None), getattr(self, "_face", None)):
            try:
                if model is not None:
                    model.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Stabiliser: per-frame gestures -> one deliberate trigger
# ---------------------------------------------------------------------------
class GestureStabilizer:
    """
    Fires a gesture only after it has been held steadily.

        gesture seen -> held long enough? -> cooldown ready? -> FIRE
                                                              -> release needed

    * Short dropouts (FLICKER_TOLERANCE) do not reset the hold timer.
    * With REQUIRE_RELEASE_BETWEEN_TRIGGERS the same gesture cannot fire twice
      in a row without being released first.
    """

    def __init__(self) -> None:
        self._candidate: Optional[str] = None
        self._since = 0.0
        self._lost_since: Optional[float] = None
        self._fired = False
        self.progress = 0.0  # 0..1 hold progress, for the UI

    @staticmethod
    def _hold_time(gesture: str) -> float:
        return config.HOLD_TIMES.get(gesture, config.STABLE_TIME)

    def reset(self) -> None:
        self._candidate = None
        self._lost_since = None
        self._fired = False
        self.progress = 0.0

    def update(self, gesture: Optional[str], now: float, ready: bool) -> Optional[str]:
        """Feed one frame's gesture. Returns the gesture to fire, or None."""
        valid = gesture in ACTIONABLE_GESTURES

        if valid and gesture == self._candidate:
            self._lost_since = None
        else:
            # Different gesture / nothing: tolerate a brief flicker first.
            if self._candidate is not None:
                if self._lost_since is None:
                    self._lost_since = now
                if now - self._lost_since < config.FLICKER_TOLERANCE:
                    return self._check(now, ready)
            self._candidate = gesture if valid else None
            self._since = now
            self._lost_since = None
            self._fired = False

        return self._check(now, ready)

    def _check(self, now: float, ready: bool) -> Optional[str]:
        if self._candidate is None:
            self.progress = 0.0
            return None

        hold = self._hold_time(self._candidate)
        held = now - self._since
        self.progress = 1.0 if self._fired else min(1.0, held / hold)

        if not self._fired and held >= hold and ready:
            fired_gesture = self._candidate
            if config.REQUIRE_RELEASE_BETWEEN_TRIGGERS:
                self._fired = True
            else:
                self._since = now  # hold again before the next trigger
            return fired_gesture
        return None