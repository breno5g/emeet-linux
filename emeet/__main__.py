"""Entry point: python -m emeet [/dev/videoN]"""
import sys

from .presets import PresetStore, Settings
from .v4l2 import Camera, find_uvc_device


def main(argv=sys.argv[1:]):
    if argv:
        name, dev = "Webcam", argv[0]
    elif found := find_uvc_device():
        name, dev = found
    else:
        sys.exit("no USB webcam found")
    from .ui import App

    App(Camera(dev), PresetStore(), name, Settings()).run([])


if __name__ == "__main__":
    main()
