# emeet-linux

Control panel for EMEET (and any other UVC) webcams on Linux, with a live preview.
EMEET only ships eMeetLink for Windows and macOS; this covers what the camera
exposes over standard UVC controls without opening OBS.

## Run

```
python -m emeet              # auto-detects the first USB camera
python -m emeet /dev/video2  # or pick one
```

Needs `v4l2-ctl` (v4l-utils), GTK 4, libadwaita, GStreamer with the
`gtk4paintablesink` plugin (gst-plugin-gtk4), and PyGObject. All are in the
Manjaro/Arch repos.

## Test

```
python -m unittest discover -s tests
```

The UI tests build real widgets with a fake camera and are skipped when there is
no display.

## Layout

| Path | Role |
|---|---|
| `emeet/v4l2.py` | Parse `v4l2-ctl` output, `Camera` wrapper, device discovery |
| `emeet/pipeline.py` | GStreamer pipeline description for the preview |
| `emeet/quirks.py` | Per-camera firmware quirks (zoom modes) |
| `emeet/presets.py` | Presets and settings, JSON in `~/.config/emeet-linux/` |
| `emeet/ui.py` | GTK4 + libadwaita window: preview, controls, presets |
| `emeet/__main__.py` | Entry point |

## Not covered

Firmware effects from eMeetLink (BlackWhite, Cartoon, HDR, AI framing) live behind
EMEET's proprietary UVC extension unit and are not exposed as v4l2 controls.

## Camera quirks (SmartCam S600, firmware as of 2026-10)

Digital zoom is accepted in every mode but only changes the image in some.
Measured by capturing frames at zoom 100 and 150 straight from `v4l2src`:

| Mode | Zoom |
|---|---|
| MJPG 1920×1080 @ 30 | works |
| MJPG 1280×720 @ 60 | works |
| MJPG 640×360 @ 30 | works |
| MJPG 1920×1080 @ 60 | no effect |
| MJPG 3840×2160 @ 30 | no effect |
| YUYV 640×480 @ 30 | no effect |

The app greys out the zoom slider in those modes with a hint. The table lives in
`emeet/quirks.py`; add a line for another camera after measuring it the same way.
