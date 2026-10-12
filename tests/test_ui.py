"""Widget tests with a fake camera. Skipped when no display is available."""
import copy
import tempfile
import unittest
from pathlib import Path

from emeet.presets import PresetStore
from emeet.v4l2 import apply_order

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, GLib, Gtk

    Gtk.init()
    HAVE_DISPLAY = Gdk.Display.get_default() is not None
except Exception:  # no gi, or no display
    HAVE_DISPLAY = False

if HAVE_DISPLAY:
    Adw.init()
    from emeet.ui import AUTO_EXPOSURE_OFF, ControlPanel, PresetPanel, StreamBar, fmt_value, group_controls


def ctrl(name, type_, value, default=None, lo=None, hi=None, menu=None, inactive=False):
    return {"name": name, "type": type_, "value": value, "default": value if default is None else default,
            "min": lo, "max": hi, "step": 1 if type_ == "int" else None, "menu": menu or {}, "inactive": inactive, "flags": ""}


BASE = [
    ctrl("brightness", "int", 97, 128, 0, 255),
    ctrl("white_balance_automatic", "bool", 1),
    ctrl("white_balance_temperature", "int", 5000, 5000, 2300, 7500, inactive=True),
    ctrl("auto_exposure", "menu", 3, menu={1: "Manual Mode", 3: "Aperture Priority Mode"}),
    ctrl("power_line_frequency", "menu", 2, menu={0: "Disabled", 1: "50 Hz", 2: "60 Hz"}),
    ctrl("zoom_absolute", "int", 100, 100, 100, 150),
    ctrl("zoom_continuous", "int", 0, 0, 0, 0),
    ctrl("weird_vendor_thing", "int", 1, 1, 0, 3),
]
FORMATS = {"MJPG": {(1920, 1080): [60.0, 30.0], (1280, 720): [30.0]}, "YUYV": {(640, 480): [30.0]}}


class FakeCamera:
    """Same surface as emeet.v4l2.Camera, backed by dicts. Mirrors the UVC rule that
    white balance temperature is locked while automatic white balance is on."""

    dev = "/dev/fake"

    def __init__(self):
        self.state = copy.deepcopy(BASE)
        self.sets = []

    def controls(self):
        auto = next(c for c in self.state if c["name"] == "white_balance_automatic")["value"]
        next(c for c in self.state if c["name"] == "white_balance_temperature")["inactive"] = bool(auto)
        return copy.deepcopy(self.state)

    def formats(self):
        return FORMATS

    def set(self, name, value):
        self.sets.append((name, int(value)))
        next(c for c in self.state if c["name"] == name)["value"] = int(value)

    def apply(self, values):
        for n, v in apply_order(values, self.controls()):
            self.set(n, v)

    def snapshot(self):
        return {c["name"]: c["value"] for c in self.controls() if not c["inactive"]}

    def defaults(self):
        return {c["name"]: c["default"] for c in self.controls() if not c["inactive"]}


def pump():
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


class PureHelpersTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_DISPLAY, "needs a display to import emeet.ui")
    def test_fmt_value(self):
        self.assertEqual(fmt_value(BASE[0], 0), "0%")
        self.assertEqual(fmt_value(BASE[0], 255), "100%")
        self.assertEqual(fmt_value(BASE[0], 128), "50%")
        self.assertEqual(fmt_value(BASE[5], 125), "1.25×")

    @unittest.skipUnless(HAVE_DISPLAY, "needs a display to import emeet.ui")
    def test_group_controls_puts_unknown_last(self):
        groups = list(group_controls(BASE))
        self.assertEqual([t for t, _ in groups], ["Image", "Color and light", "Focus and zoom", "Other"])
        self.assertEqual([c["name"] for c in groups[-1][1]], ["zoom_continuous", "weird_vendor_thing"])


@unittest.skipUnless(HAVE_DISPLAY, "needs a display")
class ControlPanelTest(unittest.TestCase):
    def setUp(self):
        self.cam = FakeCamera()
        self.panel = ControlPanel(self.cam)

    def test_builds_rows_and_skips_empty_range(self):
        self.assertIn("brightness", self.panel.widgets)
        self.assertNotIn("zoom_continuous", self.panel.widgets)

    def test_inactive_row_is_insensitive(self):
        self.assertFalse(self.panel.widgets["white_balance_temperature"][0].get_sensitive())
        self.assertTrue(self.panel.widgets["brightness"][0].get_sensitive())

    def test_initial_refresh_does_not_write(self):
        self.assertEqual(self.cam.sets, [])

    def test_slider_writes_to_camera(self):
        row, _ = self.panel.widgets["brightness"]
        scale = row.get_child().get_last_child()
        scale.set_value(200)
        self.assertEqual(self.cam.sets, [("brightness", 200)])

    def test_switch_unlocks_dependent_slider(self):
        row, _ = self.panel.widgets["white_balance_automatic"]
        row.set_active(False)
        pump()
        self.assertEqual(self.cam.sets, [("white_balance_automatic", 0)])
        self.assertTrue(self.panel.widgets["white_balance_temperature"][0].get_sensitive())

    def test_auto_exposure_switch_maps_to_menu_values(self):
        row, _ = self.panel.widgets["auto_exposure"]
        self.assertTrue(row.get_active())
        row.set_active(False)
        self.assertEqual(self.cam.sets, [("auto_exposure", AUTO_EXPOSURE_OFF)])

    def test_combo_writes_menu_key(self):
        row, _ = self.panel.widgets["power_line_frequency"]
        self.assertEqual(row.get_selected(), 2)
        row.set_selected(1)
        self.assertEqual(self.cam.sets, [("power_line_frequency", 1)])

    def test_stream_quirk_blocks_zoom_with_hint(self):
        panel = ControlPanel(self.cam, "EMEET SmartCam S600")
        row, _ = panel.widgets["zoom_absolute"]
        panel.set_stream("MJPG", 1920, 1080, 60.0)
        self.assertFalse(row.get_sensitive())
        self.assertTrue(panel.hints["zoom_absolute"].get_visible())
        panel.refresh()  # a control refresh must not re-enable it
        self.assertFalse(row.get_sensitive())
        panel.set_stream("MJPG", 1920, 1080, 30.0)
        self.assertTrue(row.get_sensitive())
        self.assertFalse(panel.hints["zoom_absolute"].get_visible())
        self.assertEqual(self.cam.sets, [])

    def test_unknown_camera_never_blocks(self):
        self.panel.set_stream("MJPG", 1920, 1080, 60.0)
        self.assertTrue(self.panel.widgets["zoom_absolute"][0].get_sensitive())

    def test_apply_refreshes_widgets(self):
        self.panel.apply({"brightness": 10})
        row, _ = self.panel.widgets["brightness"]
        self.assertEqual(row.get_child().get_last_child().get_value(), 10)
        self.assertEqual(self.cam.sets, [("brightness", 10)])


@unittest.skipUnless(HAVE_DISPLAY, "needs a display")
class PreviewLayoutTest(unittest.TestCase):
    def test_frame_size_does_not_drive_layout(self):
        try:
            from emeet.ui import Preview
            preview = Preview("/dev/fake")  # inits GStreamer, starts nothing
        except Exception as e:  # no GStreamer on this box
            self.skipTest(f"GStreamer unavailable: {e}")
        texture = Gdk.MemoryTexture.new(1920, 1080, Gdk.MemoryFormat.R8G8B8A8, GLib.Bytes.new(bytes(1920 * 1080 * 4)), 1920 * 4)
        preview.picture.set_paintable(texture)
        _, pic_nat, _, _ = preview.picture.measure(Gtk.Orientation.HORIZONTAL, -1)
        _, widget_nat, _, _ = preview.widget.measure(Gtk.Orientation.HORIZONTAL, -1)
        self.assertEqual(pic_nat, 1920)
        self.assertEqual(widget_nat, 0)
        preview.picture.set_paintable(None)
        self.assertEqual(preview.widget.measure(Gtk.Orientation.HORIZONTAL, -1)[1], 0)


@unittest.skipUnless(HAVE_DISPLAY, "needs a display")
class StreamBarTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.bar = StreamBar(FORMATS, lambda *a: self.calls.append(a))

    def test_starts_at_720p_first_fps(self):
        self.assertEqual(self.calls, [("MJPG", 1280, 720, 30.0, False)])

    def test_resolution_change_rebuilds_fps(self):
        self.bar.res.set_selected(0)
        self.assertEqual(self.calls[-1], ("MJPG", 1920, 1080, 60.0, False))
        self.assertEqual(self.bar.fps.get_model().get_n_items(), 2)
        self.bar.fps.set_selected(1)
        self.assertEqual(self.calls[-1], ("MJPG", 1920, 1080, 30.0, False))

    def test_format_change(self):
        self.bar.fmt.set_selected(1)
        self.assertEqual(self.calls[-1], ("YUYV", 640, 480, 30.0, False))

    def test_mirror(self):
        self.bar.mirror.set_active(True)
        self.assertEqual(self.calls[-1], ("MJPG", 1280, 720, 30.0, True))

    def test_resolution_change_keeps_mirror(self):
        self.bar.mirror.set_active(True)
        self.bar.res.set_selected(0)
        self.assertEqual(self.calls[-1], ("MJPG", 1920, 1080, 60.0, True))

    def test_initial_saved_mode_is_restored(self):
        calls = []
        bar = StreamBar(FORMATS, lambda *a: calls.append(a), initial=("MJPG", 1920, 1080, 30.0, True))
        self.assertEqual(calls, [("MJPG", 1920, 1080, 30.0, True)])
        self.assertEqual((bar.fmt.get_selected(), bar.res.get_selected(), bar.fps.get_selected()), (0, 0, 1))
        self.assertTrue(bar.mirror.get_active())

    def test_initial_mode_not_offered_falls_back(self):
        calls = []
        StreamBar(FORMATS, lambda *a: calls.append(a), initial=("MJPG", 3840, 2160, 30.0, False))
        self.assertEqual(calls, [("MJPG", 1280, 720, 30.0, False)])
        calls.clear()
        StreamBar(FORMATS, lambda *a: calls.append(a), initial=("YUYV", 640, 480, 60.0, False))
        self.assertEqual(calls, [("MJPG", 1280, 720, 30.0, False)])


@unittest.skipUnless(HAVE_DISPLAY, "needs a display")
class PresetPanelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PresetStore(Path(self.tmp.name) / "p.json")
        self.cam = FakeCamera()
        self.controls = ControlPanel(self.cam)
        self.panel = PresetPanel(self.store, self.controls, lambda: None)

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        out, child = [], self.panel.list.get_first_child()
        while child:
            out.append(child)
            child = child.get_next_sibling()
        return out

    def test_empty_store_hides_group(self):
        self.assertFalse(self.panel.group.get_visible())

    def test_save_snapshots_active_controls(self):
        self.panel.save("Day")
        self.assertEqual(self.store.get("Day")["brightness"], 97)
        self.assertNotIn("white_balance_temperature", self.store.get("Day"))
        self.assertEqual([r.get_title() for r in self.rows()], ["Day"])
        self.assertTrue(self.panel.group.get_visible())

    def test_activate_row_applies(self):
        self.store.save("Dim", {"brightness": 5})
        self.panel.reload()
        self.rows()[0].activate()
        self.assertEqual(self.cam.sets, [("brightness", 5)])

    def test_delete(self):
        self.panel.save("A")
        self.panel.delete("A")
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.store.names(), [])


if __name__ == "__main__":
    unittest.main()
