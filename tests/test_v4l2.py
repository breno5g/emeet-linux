import unittest
from unittest.mock import Mock

from emeet.v4l2 import Camera, apply_order, find_uvc_device, parse_controls, parse_devices, parse_formats

CTRLS = """
User Controls

                     brightness 0x00980900 (int)    : min=0 max=255 step=1 default=128 value=97 flags=has-min-max
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1
           power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=2 value=2 (60 Hz)
\t\t\t\t0: Disabled
\t\t\t\t1: 50 Hz
\t\t\t\t2: 60 Hz
      white_balance_temperature 0x0098091a (int)    : min=2300 max=7500 step=1 default=5000 value=5000 flags=inactive, has-min-max

Camera Controls

                  auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=3 value=3 (Aperture Priority Mode)
\t\t\t\t1: Manual Mode
\t\t\t\t3: Aperture Priority Mode
                zoom_continuous 0x009a090f (int)    : min=0 max=0 step=0 default=0 value=0 flags=has-min-max
"""

FORMATS = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.017s (60.000 fps)
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
"""

DEVICES = """Droidcam (platform:v4l2loopback_dc-000):
\t/dev/video0

EMEET SmartCam S600: EMEET Smar (usb-0000:06:00.3-2.2):
\t/dev/video2
\t/dev/video3
\t/dev/media0
"""


class ParseControlsTest(unittest.TestCase):
    def setUp(self):
        self.cs = {c["name"]: c for c in parse_controls(CTRLS)}

    def test_int_control(self):
        b = self.cs["brightness"]
        self.assertEqual((b["type"], b["min"], b["max"], b["default"], b["value"]), ("int", 0, 255, 128, 97))
        self.assertFalse(b["inactive"])

    def test_bool_has_no_range(self):
        self.assertEqual(self.cs["white_balance_automatic"]["type"], "bool")
        self.assertIsNone(self.cs["white_balance_automatic"]["min"])

    def test_menu_entries(self):
        self.assertEqual(self.cs["power_line_frequency"]["menu"], {0: "Disabled", 1: "50 Hz", 2: "60 Hz"})
        self.assertEqual(self.cs["auto_exposure"]["menu"], {1: "Manual Mode", 3: "Aperture Priority Mode"})

    def test_inactive_flag(self):
        self.assertTrue(self.cs["white_balance_temperature"]["inactive"])

    def test_keeps_source_order(self):
        self.assertEqual([c["name"] for c in parse_controls(CTRLS)][:3], ["brightness", "white_balance_automatic", "power_line_frequency"])


class ParseFormatsTest(unittest.TestCase):
    def test_nested_structure(self):
        self.assertEqual(parse_formats(FORMATS), {
            "MJPG": {(1920, 1080): [60.0, 30.0], (1280, 720): [30.0]},
            "YUYV": {(640, 480): [30.0]},
        })


class ParseDevicesTest(unittest.TestCase):
    def test_groups_paths_under_cards(self):
        self.assertEqual(parse_devices(DEVICES), [
            ("Droidcam", "platform:v4l2loopback_dc-000", ["/dev/video0"]),
            ("EMEET SmartCam S600: EMEET Smar", "usb-0000:06:00.3-2.2", ["/dev/video2", "/dev/video3", "/dev/media0"]),
        ])

    def test_find_uvc_device_skips_loopbacks(self):
        run = Mock(return_value=Mock(stdout=DEVICES))
        self.assertEqual(find_uvc_device(run), ("EMEET SmartCam S600", "/dev/video2"))

    def test_find_uvc_device_none(self):
        run = Mock(return_value=Mock(stdout="Droidcam (platform:x):\n\t/dev/video0\n"))
        self.assertIsNone(find_uvc_device(run))


class ApplyOrderTest(unittest.TestCase):
    def test_modes_before_ints_and_unknown_dropped(self):
        controls = parse_controls(CTRLS)
        values = {"brightness": 10, "white_balance_automatic": 0, "white_balance_temperature": 3000, "auto_exposure": 1, "bogus": 1}
        ordered = apply_order(values, controls)
        names = [n for n, _ in ordered]
        self.assertNotIn("bogus", names)
        self.assertLess(names.index("white_balance_automatic"), names.index("white_balance_temperature"))
        self.assertLess(names.index("auto_exposure"), names.index("brightness"))


class CameraTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def run(cmd, **_):
            self.calls.append(cmd)
            out = {"--list-ctrls-menus": CTRLS, "--list-formats-ext": FORMATS}.get(cmd[-1], "")
            return Mock(stdout=out)

        self.cam = Camera("/dev/video9", run)

    def test_set_formats_command(self):
        self.cam.set("brightness", 42.7)
        self.assertEqual(self.calls[-1], ["v4l2-ctl", "-d", "/dev/video9", "--set-ctrl", "brightness=42"])

    def test_snapshot_skips_inactive(self):
        snap = self.cam.snapshot()
        self.assertIn("brightness", snap)
        self.assertNotIn("white_balance_temperature", snap)

    def test_defaults(self):
        self.assertEqual(self.cam.defaults()["brightness"], 128)

    def test_apply_sets_in_order(self):
        self.cam.apply({"white_balance_temperature": 3000, "white_balance_automatic": 0})
        sets = [c[-1] for c in self.calls if "--set-ctrl" in c]
        self.assertEqual(sets, ["white_balance_automatic=0", "white_balance_temperature=3000"])

    def test_formats(self):
        self.assertIn("MJPG", self.cam.formats())


if __name__ == "__main__":
    unittest.main()
