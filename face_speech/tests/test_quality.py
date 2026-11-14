"""Unit tests for audio quality assessment module."""

import unittest
import numpy as np

from speech.quality import (
    compute_audio_quality,
    compute_clipping_fraction,
    estimate_snr_db,
)


class TestAudioQuality(unittest.TestCase):
    """Test suite for SNR calculation, clipping detection, and quality metric."""

    def setUp(self):
        self.sr = 16000

    def test_clipping_fraction(self):
        # Clean audio with max amplitude 0.8 -> 0% clipping
        clean = np.sin(np.linspace(0, 100, 1000)) * 0.8
        self.assertEqual(compute_clipping_fraction(clean, threshold=0.99), 0.0)

        # 50% clipped audio
        clipped = np.array([1.0, 1.0, 0.2, 0.2], dtype=np.float32)
        self.assertEqual(compute_clipping_fraction(clipped, threshold=0.99), 0.5)

    def test_snr_pure_tone_vs_silence(self):
        # 16000 samples (1s). Speech from 0 to 8000, silence/noise from 8000 to 16000
        audio = np.zeros(16000, dtype=np.float32)
        t = np.linspace(0, 0.5, 8000, endpoint=False)
        audio[:8000] = 0.5 * np.sin(2 * np.pi * 440 * t)  # high energy speech
        audio[8000:] = 0.001 * np.random.randn(8000)      # low energy noise

        speech_segments = [{"start": 0, "end": 8000}]
        snr = estimate_snr_db(audio, speech_segments)
        self.assertGreater(snr, 15.0)

    def test_high_quality_valid_speech(self):
        # 30 seconds of speech: 20 seconds speech, 10 seconds low noise
        audio = np.zeros(self.sr * 30, dtype=np.float32)
        # 20 seconds speech (0 to 20s)
        t_speech = np.linspace(0, 20, self.sr * 20, endpoint=False)
        audio[: self.sr * 20] = 0.5 * np.sin(2 * np.pi * 300 * t_speech)
        # 10s noise
        audio[self.sr * 20 :] = 0.002 * np.random.randn(self.sr * 10)

        speech_segments = [{"start": 0, "end": self.sr * 20}]
        quality, is_valid, metrics = compute_audio_quality(
            audio, sr=self.sr, speech_segments=speech_segments
        )
        self.assertGreaterEqual(quality, 0.5)
        self.assertTrue(is_valid)
        self.assertEqual(metrics["clipping_fraction"], 0.0)
        self.assertAlmostEqual(metrics["speech_duration_s"], 20.0, places=1)

    def test_silence_or_no_speech_invalid(self):
        # 30 seconds of pure silence
        audio = np.zeros(self.sr * 30, dtype=np.float32)
        speech_segments = []  # No speech detected
        quality, is_valid, metrics = compute_audio_quality(
            audio, sr=self.sr, speech_segments=speech_segments
        )
        self.assertEqual(quality, 0.0)
        self.assertFalse(is_valid)

    def test_short_speech_duration_invalid(self):
        # 30 second audio with only 2 seconds of speech (< 5s requirement)
        audio = np.zeros(self.sr * 30, dtype=np.float32)
        audio[: self.sr * 2] = 0.5 * np.sin(np.linspace(0, 100, self.sr * 2))
        speech_segments = [{"start": 0, "end": self.sr * 2}]

        quality, is_valid, metrics = compute_audio_quality(
            audio, sr=self.sr, speech_segments=speech_segments
        )
        # Regardless of quality score, speech_duration_s < 5.0 marks valid: False
        self.assertFalse(is_valid)
        self.assertAlmostEqual(metrics["speech_duration_s"], 2.0, places=1)

    def test_heavy_clipping_degrades_quality(self):
        # 10 seconds of speech with severe clipping (> 10% clipped samples)
        audio = np.zeros(self.sr * 10, dtype=np.float32)
        audio[: self.sr * 8] = 1.0  # severely clipped square wave
        speech_segments = [{"start": 0, "end": self.sr * 8}]

        quality, is_valid, metrics = compute_audio_quality(
            audio, sr=self.sr, speech_segments=speech_segments
        )
        self.assertGreater(metrics["clipping_fraction"], 0.5)
        self.assertEqual(quality, 0.0)
        self.assertFalse(is_valid)


if __name__ == "__main__":
    unittest.main()
