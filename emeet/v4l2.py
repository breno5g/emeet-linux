"""Talk to a UVC camera through v4l2-ctl: list controls and formats, set values."""
import re
import subprocess

CTRL_RE = re.compile(
    r"^\s*(?P<name>\w+) 0x[0-9a-f]+ \((?P<type>\w+)\)\s*:"
    r"(?: min=(?P<min>-?\d+))?(?: max=(?P<max>-?\d+))?(?: step=(?P<step>\d+))?"
    r" default=(?P<default>-?\d+) value=(?P<value>-?\d+)(?: \(.*?\))?(?: flags=(?P<flags>[\w, -]+))?",
    re.M,
)
MENU_RE = re.compile(r"^\t\t\t\t(?P<idx>\d+): (?P<label>.+)$")
FMT_RE = re.compile(r"^\t\[\d+\]: '(?P<fmt>\w+)'")
SIZE_RE = re.compile(r"^\t\tSize: Discrete (?P<w>\d+)x(?P<h>\d+)")
FPS_RE = re.compile(r"\((?P<fps>[\d.]+) fps\)")


def parse_controls(text):
    """Parse `v4l2-ctl --list-ctrls-menus` into a list of control dicts."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = CTRL_RE.match(line)
        if not m:
            continue
        c = m.groupdict()
        for k in ("min", "max", "step", "default", "value"):
            c[k] = int(c[k]) if c[k] is not None else None
        c["inactive"] = "inactive" in (c["flags"] or "")
        c["menu"] = {}
        for j in range(i + 1, len(lines)):
            mm = MENU_RE.match(lines[j])
            if not mm:
                break
            c["menu"][int(mm["idx"])] = mm["label"]
        out.append(c)
    return out


def parse_formats(text):
    """Parse `v4l2-ctl --list-formats-ext` into {fmt: {(w, h): [fps, ...]}}."""
    out, fmt, size = {}, None, None
    for line in text.splitlines():
        if m := FMT_RE.match(line):
            fmt = out.setdefault(m["fmt"], {})
        elif m := SIZE_RE.match(line):
            size = fmt.setdefault((int(m["w"]), int(m["h"])), [])
        elif m := FPS_RE.search(line):
            size.append(float(m["fps"]))
    return out


def parse_devices(text):
    """Parse `v4l2-ctl --list-devices` into [(card name, bus info, [paths])]."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith("\t"):
            name, _, bus = line.rstrip(":").rpartition(" (")
            out.append((name, bus.rstrip(")"), []))
        elif out:
            out[-1][2].append(line.strip())
    return out


def apply_order(values, controls):
    """Order a {name: value} dict so auto/menu controls come before ints.

    Setting a manual value while its auto mode is on gets rejected by the camera,
    so modes must land first.
    """
    by_name = {c["name"]: c for c in controls}
    return [(n, values[n]) for n in sorted(values, key=lambda n: by_name.get(n, {}).get("type") == "int") if n in by_name]


class Camera:
    def __init__(self, dev, run=subprocess.run):
        self.dev = dev
        self._run = run

    def _ctl(self, *args):
        return self._run(["v4l2-ctl", "-d", self.dev, *args], capture_output=True, text=True).stdout

    def controls(self):
        return parse_controls(self._ctl("--list-ctrls-menus"))

    def formats(self):
        return parse_formats(self._ctl("--list-formats-ext"))

    def set(self, name, value):
        self._ctl("--set-ctrl", f"{name}={int(value)}")

    def apply(self, values):
        for name, value in apply_order(values, self.controls()):
            self.set(name, value)

    def snapshot(self):
        """Current values of every control that is not locked by an auto mode."""
        return {c["name"]: c["value"] for c in self.controls() if not c["inactive"]}

    def defaults(self):
        return {c["name"]: c["default"] for c in self.controls() if not c["inactive"]}


def find_uvc_device(run=subprocess.run):
    """Return (card name, /dev/videoN) of the first USB camera, or None."""
    text = run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True).stdout
    for name, bus, paths in parse_devices(text):
        if bus.startswith("usb-") and paths:
            return name.split(":")[0], paths[0]
    return None
