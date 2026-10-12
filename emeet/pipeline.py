"""GStreamer pipeline description for the live preview."""
from fractions import Fraction


def pipeline_desc(dev, fmt, w, h, fps, mirror=False):
    fr = Fraction(round(fps * 1001), 1001)  # 29.97 -> 30000/1001, 30 -> 30/1
    caps = f"width={w},height={h},framerate={fr.numerator}/{fr.denominator}"
    decode = f"image/jpeg,{caps} ! jpegdec" if fmt == "MJPG" else f"video/x-raw,{caps}"
    flip = " ! videoflip method=horizontal-flip" if mirror else ""
    return f"v4l2src device={dev} ! {decode} ! videoconvert{flip} ! queue ! gtk4paintablesink name=sink"


def default_size(sizes, preferred=(1280, 720)):
    """Index of the preferred resolution in a size list, else 0."""
    return sizes.index(preferred) if preferred in sizes else 0
