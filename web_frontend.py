from __future__ import annotations

import cv2
from flask import Flask, Response, jsonify, render_template

from main import Application

app = Flask(__name__, template_folder=".")
controller = Application(headless=True)
controller.start_worker()


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    snap = controller._get_snapshot()
    return jsonify(
        {
            "camera_ok": snap.camera_ok,
            "camera_message": snap.camera_message,
            "fatal_error": snap.fatal_error,
            "gesture": snap.gesture,
            "confidence": snap.confidence,
            "action": snap.action,
            "fps": snap.fps,
            "control_enabled": snap.control_enabled,
            "cooldown_remaining": snap.cooldown_remaining,
            "hold_progress": snap.hold_progress,
            "status": snap.status,
            "warning": snap.warning,
            "history": [
                {"time": stamp, "gesture": gesture_text, "action": action_text}
                for stamp, gesture_text, action_text in snap.history
            ],
        }
    )


@app.route("/api/frame")
def api_frame():
    snap = controller._get_snapshot()
    if not snap.camera_ok or snap.frame_bgr is None:
        return Response(status=204)

    ok, buffer = cv2.imencode(".jpg", snap.frame_bgr)
    if not ok:
        return Response(status=500)

    response = Response(buffer.tobytes(), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/start", methods=["POST"])
def api_start():
    controller.start_presentation()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    controller.stop_control()
    return jsonify({"ok": True})


@app.route("/api/next", methods=["POST"])
def api_next():
    controller.manual_next()
    return jsonify({"ok": True})


@app.route("/api/previous", methods=["POST"])
def api_previous():
    controller.manual_previous()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
