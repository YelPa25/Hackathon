"""Unit tests for window aggregation and quality logic using synthetic frame dicts."""

import unittest
from facial.windows import (
    WindowAggregator,
    aggregate_window,
    compute_brightness_penalty,
)


def make_dummy_frame(
    detected: bool = True,
    brightness: float = 120.0,
    intensity_val: float = 1.0,
    detected_flag: int = 1,
    pitch: float = 0.0,
    yaw: float = 0.0,
    roll: float = 0.0,
) -> dict:
    """Helper to construct synthetic frame dict without running LibreFace."""
    if not detected:
        return {
            "face_detected": False,
            "mean_brightness": brightness,
            "au_intensities": {},
            "detected_aus": {},
            "head_pose": None,
            "expression": None,
        }
    return {
        "face_detected": True,
        "mean_brightness": brightness,
        "au_intensities": {
            "au_1_intensity": intensity_val,
            "au_2_intensity": intensity_val * 0.5,
            "au_4_intensity": intensity_val * 2.0,
        },
        "detected_aus": {
            "au_1": detected_flag,
            "au_2": detected_flag,
            "au_4": detected_flag,
        },
        "head_pose": {
            "pitch": pitch,
            "yaw": yaw,
            "roll": roll,
        },
        "expression": "Neutral",
    }


class TestWindowsAggregation(unittest.TestCase):
    """Test suite for aggregation, quality score, and contract compliance."""

    def test_brightness_penalty_curve(self):
        # Optimal middle range
        self.assertEqual(compute_brightness_penalty(128.0), 1.0)
        self.assertEqual(compute_brightness_penalty(40.0), 1.0)
        self.assertEqual(compute_brightness_penalty(215.0), 1.0)

        # Dark range
        self.assertEqual(compute_brightness_penalty(0.0), 0.0)
        self.assertAlmostEqual(compute_brightness_penalty(20.0), 0.5, places=2)

        # Overexposed range
        self.assertEqual(compute_brightness_penalty(255.0), 0.0)
        self.assertAlmostEqual(compute_brightness_penalty(235.0), 0.5, places=2)

    def test_empty_window(self):
        res = aggregate_window([], timestamp="2026-11-14T00:00:00Z")
        self.assertEqual(res["modality"], "facial")
        self.assertEqual(res["t"], "2026-11-14T00:00:00Z")
        self.assertEqual(res["quality"], 0.0)
        self.assertFalse(res["valid"])
        self.assertEqual(res["features"]["expressiveness"], 0.0)

    def test_high_quality_valid_window(self):
        # 10 frames with good lighting and clear face detections
        frames = [
            make_dummy_frame(
                detected=True,
                brightness=120.0,
                intensity_val=1.5,
                pitch=float(i),
                yaw=float(i * 2),
                roll=0.0,
            )
            for i in range(10)
        ]
        res = aggregate_window(frames, timestamp="2026-11-14T12:00:00Z")

        self.assertEqual(res["modality"], "facial")
        self.assertEqual(res["t"], "2026-11-14T12:00:00Z")
        self.assertAlmostEqual(res["quality"], 1.0, places=2)
        self.assertTrue(res["valid"])

        # Check AU statistics keys
        self.assertIn("au1_mean", res["features"])
        self.assertIn("au1_std", res["features"])
        self.assertAlmostEqual(res["features"]["au1_mean"], 1.5, places=3)
        self.assertAlmostEqual(res["features"]["au1_std"], 0.0, places=3)

        # Global features
        self.assertIn("expressiveness", res["features"])
        self.assertGreater(res["features"]["expressiveness"], 0.0)
        self.assertIn("head_pose_std", res["features"])
        self.assertGreater(res["features"]["head_pose_std"], 0.0)
        self.assertEqual(res["features"]["au_activation_rate"], 1.0)

    def test_low_quality_no_face_invalid(self):
        # 8 out of 10 frames have no face detected -> detection ratio 0.2 < 0.5
        frames = [make_dummy_frame(detected=False) for _ in range(8)] + [
            make_dummy_frame(detected=True) for _ in range(2)
        ]
        res = aggregate_window(frames)

        self.assertLess(res["quality"], 0.5)
        self.assertFalse(res["valid"])
        self.assertAlmostEqual(res["quality"], 0.2, places=2)

    def test_low_quality_poor_lighting_invalid(self):
        # Face detected in all frames, but pitch black (brightness = 5)
        frames = [
            make_dummy_frame(detected=True, brightness=5.0) for _ in range(10)
        ]
        res = aggregate_window(frames)
        # 5 / 40 = 0.125 penalty -> quality = 0.125 < 0.5
        self.assertLess(res["quality"], 0.5)
        self.assertFalse(res["valid"])

    def test_window_aggregator_buffer_and_flush(self):
        agg = WindowAggregator(window_size=3)
        w1 = agg.add_frame(make_dummy_frame(detected=True))
        self.assertIsNone(w1)
        w2 = agg.add_frame(make_dummy_frame(detected=True))
        self.assertIsNone(w2)
        w3 = agg.add_frame(make_dummy_frame(detected=True))
        self.assertIsNotNone(w3)
        self.assertEqual(len(agg.buffer), 0)

        # Test partial flush
        agg.add_frame(make_dummy_frame(detected=True))
        self.assertEqual(len(agg.buffer), 1)
        flushed = agg.flush()
        self.assertIsNotNone(flushed)
        self.assertEqual(len(agg.buffer), 0)
        self.assertIsNone(agg.flush())


if __name__ == "__main__":
    unittest.main()
