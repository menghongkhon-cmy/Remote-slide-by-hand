"""
app.py - HandSlide Web (the browser version of HandSlide Controller).

Run it either way:
    python main.py --web      (same entry point as the desktop app)
    python app.py             (directly)
    gunicorn -w 1 --threads 4 -t 300 app:app     (hosting)

What it does
------------
The browser reads the webcam and detects gestures itself (index.html, MediaPipe
in JavaScript). This server only turns an uploaded presentation into one PNG
image per slide:

    .pptx/.ppt/.ppsx/.pps/.odp  ->  1) Microsoft PowerPoint, slide by slide to PNG
                                       (Windows + pywin32): exact layout and fonts
                                    2) LibreOffice -> PDF -> PNG (any OS): fallback
    .pdf                        ->  PNG directly (no converter needed)

Settings live in config.py (WEB_* values); every value has a default here, so
this file also works if config.py is not deployed next to it.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import List, Optional, Tuple

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:  # older PyMuPDF versions
    import fitz

from flask import Flask, jsonify, render_template, request, send_from_directory

try:
    import config
except ImportError:  # config.py not deployed: use the defaults below
    config = None  # type: ignore[assignment]


def _setting(name: str, default):
    """Read WEB_* settings from config.py, falling back to a default."""
    return getattr(config, name, default)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, _setting("WEB_DATA_DIR", "data"))
ALLOWED_EXTENSIONS = {".pptx", ".ppt", ".ppsx", ".pps", ".odp", ".pdf"}
MAX_UPLOAD_MB = _setting("WEB_MAX_UPLOAD_MB", 100)
KEEP_HOURS = _setting("WEB_KEEP_HOURS", 2)          # uploads older than this are deleted
RENDER_SCALE = _setting("WEB_RENDER_SCALE", 1.6)    # PDF -> PNG zoom (higher = sharper, slower)
PPT_EXPORT_SCALE = _setting("WEB_PPT_EXPORT_SCALE", 2.0)  # PowerPoint export: pixels per point
LIBREOFFICE_TIMEOUT = _setting("WEB_CONVERT_TIMEOUT", 180)  # seconds
DEBUG = _setting("DEBUG", True)

IS_WINDOWS = sys.platform == "win32"
HAS_POWERPOINT = False
if IS_WINDOWS:
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]

        HAS_POWERPOINT = True
    except ImportError:
        HAS_POWERPOINT = False

log = logging.getLogger("handslide.web")


class ConversionError(RuntimeError):
    """A presentation could not be turned into slide images (message is user-friendly)."""


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------
def find_libreoffice() -> Optional[str]:
    candidates = (
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    )
    return next((p for p in candidates if p and os.path.exists(p)), None)


class SlideConverter:
    """Turns an uploaded file into <folder>/1.png, 2.png, ... and returns (count, converter name)."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.soffice = find_libreoffice()
        self.has_powerpoint = HAS_POWERPOINT
        self._lock = threading.Lock()  # PowerPoint/LibreOffice cannot run two conversions at once

    @property
    def available(self) -> bool:
        return self.has_powerpoint or bool(self.soffice)

    def convert(self, src: str, folder: str, ext: str) -> Tuple[int, str]:
        if ext == ".pdf":
            return self._render_pdf(src, folder), "PDF"

        errors: List[str] = []
        with self._lock:
            if self.has_powerpoint:
                try:
                    return self._powerpoint_to_png(src, folder), "PowerPoint"
                except Exception as exc:  # noqa: BLE001 - COM errors are varied
                    errors.append(f"PowerPoint: {exc}")
                    log.warning("PowerPoint conversion failed: %s", exc)
            if self.soffice:
                try:
                    return self._render_pdf(self._libreoffice_to_pdf(src, folder), folder), "LibreOffice"
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"LibreOffice: {exc}")
                    log.warning("LibreOffice conversion failed: %s", exc)

        if not self.available:
            raise ConversionError(
                "No converter found. Install LibreOffice (libreoffice.org), or on Windows run "
                "'python -m pip install pywin32' (needs Microsoft PowerPoint), "
                "or upload your slides as a PDF."
            )
        raise ConversionError(
            "Could not convert the file (" + "; ".join(errors) + "). "
            "Close any open PowerPoint/LibreOffice window and try again, or upload a PDF."
        )

    # -- PowerPoint (exact layout) -------------------------------------------
    def _powerpoint_to_png(self, src: str, folder: str) -> int:
        pythoncom.CoInitialize()
        presentation = None
        try:
            powerpoint = win32com.client.Dispatch("PowerPoint.Application")
            # Open(FileName, ReadOnly, Untitled, WithWindow)
            presentation = powerpoint.Presentations.Open(os.path.abspath(src), True, False, False)
            width = int(presentation.PageSetup.SlideWidth * PPT_EXPORT_SCALE)
            height = int(presentation.PageSetup.SlideHeight * PPT_EXPORT_SCALE)
            count = presentation.Slides.Count
            for index in range(1, count + 1):
                out = os.path.abspath(os.path.join(folder, f"{index}.png"))
                presentation.Slides(index).Export(out, "PNG", width, height)
            if count < 1 or not os.path.exists(os.path.join(folder, "1.png")):
                raise ConversionError("PowerPoint exported no slides")
            return count
        finally:
            try:
                if presentation is not None:
                    presentation.Close()
            except Exception:  # noqa: BLE001
                pass
            pythoncom.CoUninitialize()

    # -- LibreOffice (fallback) ----------------------------------------------
    def _libreoffice_to_pdf(self, src: str, folder: str) -> str:
        profile = "file:///" + os.path.join(self.data_dir, "lo_profile").replace("\\", "/")  # avoids lock-ups
        subprocess.run(
            [self.soffice, f"-env:UserInstallation={profile}", "--headless",
             "--convert-to", "pdf", "--outdir", folder, src],
            check=True, timeout=LIBREOFFICE_TIMEOUT, capture_output=True,
        )
        pdf = os.path.join(folder, "source.pdf")
        if not os.path.exists(pdf):
            raise ConversionError("LibreOffice produced no PDF")
        return pdf

    # -- PDF -> PNG -------------------------------------------------------------
    @staticmethod
    def _render_pdf(pdf: str, folder: str) -> int:
        document = fitz.open(pdf)
        try:
            matrix = fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
            for index, page in enumerate(document, 1):
                page.get_pixmap(matrix=matrix).save(os.path.join(folder, f"{index}.png"))
            return len(document)
        finally:
            document.close()


def cleanup_old_uploads(data_dir: str, keep_hours: float) -> None:
    """Delete decks older than keep_hours so the disk never fills up."""
    if not os.path.isdir(data_dir):
        return
    limit = time.time() - keep_hours * 3600
    for name in os.listdir(data_dir):
        path = os.path.join(data_dir, name)
        if name == "lo_profile" or not os.path.isdir(path):
            continue
        try:
            if os.path.getmtime(path) < limit:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
def create_app() -> Flask:
    os.makedirs(DATA_DIR, exist_ok=True)
    app = Flask(__name__, template_folder=BASE_DIR)  # index.html sits next to this file
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
    converter = SlideConverter(DATA_DIR)

    @app.after_request
    def add_cors(response):
        """Let the page reach this server even when opened from another local origin."""
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    @app.errorhandler(Exception)
    def on_error(exc):
        code = getattr(exc, "code", 500)
        if code == 413:
            message = f"File is too large (max {MAX_UPLOAD_MB} MB)."
        else:
            message = getattr(exc, "description", None) or str(exc)
        if not isinstance(code, int):
            code = 500
        if code >= 500:
            log.exception("Unhandled error")
        return jsonify(error=message), code

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.route("/api/health", methods=["GET", "OPTIONS"])
    def health():
        if request.method == "OPTIONS":
            return "", 200
        # index.html shows its "converter missing" warning when "libreoffice" is false,
        # so that flag means "any PowerPoint converter is available".
        return jsonify(
            ok=True,
            libreoffice=converter.available,
            powerpoint=converter.has_powerpoint,
            soffice=bool(converter.soffice),
        )

    @app.route("/api/upload", methods=["POST", "OPTIONS"])
    def upload():
        if request.method == "OPTIONS":
            return "", 200

        file = request.files.get("file")
        ext = os.path.splitext(file.filename or "")[1].lower() if file else ""
        if not file or ext not in ALLOWED_EXTENSIONS:
            return jsonify(error="Please choose a PowerPoint (.pptx), .odp or .pdf file."), 400

        cleanup_old_uploads(DATA_DIR, KEEP_HOURS)
        deck_id = uuid.uuid4().hex[:10]
        folder = os.path.join(DATA_DIR, deck_id)
        os.makedirs(folder, exist_ok=True)
        src = os.path.join(folder, "source" + ext)
        file.save(src)

        started = time.monotonic()
        try:
            count, used = converter.convert(src, folder, ext)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(folder, ignore_errors=True)
            message = str(exc) if isinstance(exc, ConversionError) else f"Could not read the file ({exc})."
            return jsonify(error=message), 500

        log.info("Converted %s: %d slides with %s in %.1fs", file.filename, count, used, time.monotonic() - started)
        return jsonify(id=deck_id, name=file.filename, count=count, converter=used)

    @app.get("/slides/<deck_id>/<int:number>.png")
    def slide(deck_id: str, number: int):
        return send_from_directory(os.path.join(DATA_DIR, os.path.basename(deck_id)), f"{number}.png")

    log.info("PowerPoint converter: %s | LibreOffice: %s",
             "yes" if converter.has_powerpoint else "no", converter.soffice or "no")
    return app


logging.basicConfig(level=logging.INFO if DEBUG else logging.WARNING,
                    format="[%(levelname)s] %(message)s")
app = create_app()  # module-level so `gunicorn app:app` works


def main() -> None:
    port = int(os.environ.get("PORT", _setting("WEB_PORT", 5000)))
    # Locally stay on this PC; on a host (PORT is set) listen on all interfaces.
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else _setting("WEB_HOST", "127.0.0.1"))
    print(f"HandSlide Web running at http://localhost:{port}  (Ctrl+C to stop)")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()