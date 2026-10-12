import json
import tempfile
import unittest
from pathlib import Path

from emeet.presets import PresetStore, Settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file(self):
        s = Settings(self.path)
        self.assertIsNone(s.stream())
        self.assertEqual(s.get("x", 7), 7)

    def test_stream_roundtrip(self):
        Settings(self.path).set("stream", ["MJPG", 1920, 1080, 60.0, True])
        self.assertEqual(Settings(self.path).stream(), ("MJPG", 1920, 1080, 60.0, True))
        self.assertEqual(json.loads(self.path.read_text())["stream"], ["MJPG", 1920, 1080, 60.0, True])

    def test_malformed_stream_is_none(self):
        for bad in ([], ["MJPG", "x", 1080, 60, False], "nope", None):
            self.path.write_text(json.dumps({"stream": bad}))
            self.assertIsNone(Settings(self.path).stream(), bad)


class PresetStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "nested" / "presets.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(PresetStore(self.path).names(), [])

    def test_save_creates_dirs_and_persists(self):
        PresetStore(self.path).save("Day", {"brightness": 1})
        self.assertEqual(json.loads(self.path.read_text()), {"Day": {"brightness": 1}})
        self.assertEqual(PresetStore(self.path).get("Day"), {"brightness": 1})

    def test_delete(self):
        s = PresetStore(self.path)
        s.save("A", {})
        s.save("B", {})
        s.delete("A")
        s.delete("missing")
        self.assertEqual(PresetStore(self.path).names(), ["B"])

    def test_corrupt_file_is_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        self.assertEqual(PresetStore(self.path).names(), [])
        self.path.write_text("[1, 2]")
        self.assertEqual(PresetStore(self.path).names(), [])

    def test_save_copies_values(self):
        s = PresetStore(self.path)
        values = {"a": 1}
        s.save("X", values)
        values["a"] = 2
        self.assertEqual(s.get("X"), {"a": 1})


if __name__ == "__main__":
    unittest.main()
