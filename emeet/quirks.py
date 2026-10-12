"""Per-camera firmware quirks that v4l2 does not report.

Measured by capturing frames straight from v4l2src and comparing them, see README.
Keys are the card name prefix as `v4l2-ctl --list-devices` prints it.
"""

ZOOM_NO_EFFECT = {
    "EMEET SmartCam S600": {("MJPG", 3840, 2160, 30.0), ("MJPG", 1920, 1080, 60.0), ("YUYV", 640, 480, 30.0)},
}
ZOOM_HINT = "Zoom has no effect in this mode on this camera. 1080p at 30 fps and 720p at 60 fps do zoom."


def zoom_has_no_effect(cam_name, fmt, w, h, fps):
    modes = next((m for name, m in ZOOM_NO_EFFECT.items() if cam_name.startswith(name)), set())
    return (fmt, w, h, float(fps)) in modes
