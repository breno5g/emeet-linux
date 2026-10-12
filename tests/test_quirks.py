import unittest

from emeet.quirks import zoom_has_no_effect


class ZoomQuirkTest(unittest.TestCase):
    def test_known_modes_on_s600(self):
        self.assertTrue(zoom_has_no_effect("EMEET SmartCam S600", "MJPG", 1920, 1080, 60))
        self.assertTrue(zoom_has_no_effect("EMEET SmartCam S600", "MJPG", 3840, 2160, 30.0))
        self.assertFalse(zoom_has_no_effect("EMEET SmartCam S600", "MJPG", 1920, 1080, 30))
        self.assertFalse(zoom_has_no_effect("EMEET SmartCam S600", "MJPG", 1280, 720, 60))

    def test_name_prefix_match(self):
        self.assertTrue(zoom_has_no_effect("EMEET SmartCam S600: EMEET Smar", "MJPG", 1920, 1080, 60))

    def test_unknown_camera_has_no_quirks(self):
        self.assertFalse(zoom_has_no_effect("Logitech BRIO", "MJPG", 1920, 1080, 60))
        self.assertFalse(zoom_has_no_effect("", "MJPG", 1920, 1080, 60))


if __name__ == "__main__":
    unittest.main()
