import unittest

from emeet.pipeline import default_size, pipeline_desc


class PipelineDescTest(unittest.TestCase):
    def test_mjpg_decodes_jpeg(self):
        d = pipeline_desc("/dev/video2", "MJPG", 1920, 1080, 60.0)
        self.assertIn("v4l2src device=/dev/video2", d)
        self.assertIn("image/jpeg,width=1920,height=1080,framerate=60/1 ! jpegdec", d)
        self.assertTrue(d.endswith("gtk4paintablesink name=sink"))

    def test_raw_format(self):
        self.assertIn("video/x-raw,width=640,height=480,framerate=30/1 ! videoconvert", pipeline_desc("/dev/v", "YUYV", 640, 480, 30.0))

    def test_ntsc_fraction(self):
        self.assertIn("framerate=30000/1001", pipeline_desc("/dev/v", "YUYV", 640, 480, 29.97))

    def test_mirror_inserts_flip(self):
        self.assertIn("videoconvert ! videoflip method=horizontal-flip ! queue", pipeline_desc("/dev/v", "MJPG", 1, 1, 30, mirror=True))
        self.assertNotIn("videoflip", pipeline_desc("/dev/v", "MJPG", 1, 1, 30))


class DefaultSizeTest(unittest.TestCase):
    def test_prefers_720p(self):
        self.assertEqual(default_size([(1920, 1080), (1280, 720), (640, 480)]), 1)

    def test_falls_back_to_first(self):
        self.assertEqual(default_size([(640, 480)]), 0)


if __name__ == "__main__":
    unittest.main()
