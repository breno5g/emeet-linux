"""User state in the config dir: named presets of control values, and app settings."""
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "emeet-linux"


def read_json(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


class PresetStore:
    def __init__(self, path=CONFIG_DIR / "presets.json"):
        self.path = Path(path)
        self.presets = read_json(self.path)

    def names(self):
        return list(self.presets)

    def get(self, name):
        return self.presets[name]

    def save(self, name, values):
        self.presets[name] = dict(values)
        write_json(self.path, self.presets)

    def delete(self, name):
        self.presets.pop(name, None)
        write_json(self.path, self.presets)


class Settings:
    """Flat key/value settings, written on every change. `stream` holds the last chosen mode."""

    def __init__(self, path=CONFIG_DIR / "settings.json"):
        self.path = Path(path)
        self.data = read_json(self.path)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        write_json(self.path, self.data)

    def stream(self):
        """Saved (fmt, w, h, fps, mirror) or None."""
        s = self.data.get("stream")
        try:
            fmt, w, h, fps, mirror = s
            return str(fmt), int(w), int(h), float(fps), bool(mirror)
        except (TypeError, ValueError):
            return None
