"""Unit tests for speech timing features and syllable nuclei detection."""

import unittest
import numpy as np

from speech.features import count_syllable_nuclei, extract_timing_features


class TestSpeechTiming(unittest.TestCase):
    """Test suite for syllable count, speech/pause ratios, and articulation rates."""

    def setUp(self):
        self.sr = 16000

    def test_pure_silence_timing(self):
        # 10s of zero amplitude
        audio = np.zeros(self.sr * 10, dtype=np.float32)
        speech_segments = []
        feats = extract_timing_features(audio, sr=self.sr, speech_segments=speech_segments)

        self.assertEqual(feats["speech_ratio"], 0.0)
        self.assertEqual(feats["pause_ratio"], 1.0)
        self.assertEqual(feats["speech_rate_syll_per_s"], 0.0)
        self.assertEqual(feats["articulation_rate_syll_per_s"], 0.0)
        self.assertGreater(feats["pause_count_per_min"], 0.0)

    def test_continuous_tone_timing(self):
        # 10s of continuous voice tone (no pauses)
        t = np.linspace(0, 10, self.sr * 10, endpoint=False)
        audio = (0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
        speech_segments = [{"start": 0, "end": self.sr * 10}]
        feats = extract_timing_features(audio, sr=self.sr, speech_segments=speech_segments)

        self.assertEqual(feats["speech_ratio"], 1.0)
        self.assertEqual(feats["pause_ratio"], 0.0)
        self.assertEqual(feats["mean_pause_s"], 0.0)

    def test_syllable_nuclei_synthetic_bursts(self):
        # Construct 4 distinct vowel-like acoustic bursts separated by silence dips
        # Each burst is 0.3s long with voiced pitch 220Hz
        duration = 3.0
        audio = np.zeros(int(duration * self.sr), dtype=np.float32)
        t = np.linspace(0, duration, len(audio), endpoint=False)

        burst_intervals = [(0.2, 0.5), (0.8, 1.1), (1.5, 1.8), (2.2, 2.5)]
        for s, e in burst_intervals:
            mask = (t >= s) & (t < e)
            sub_t = t[mask]
            audio[mask] = 0.5 * np.sin(2 * np.pi * 220 * sub_t)

        syllables = count_syllable_nuclei(audio, sr=self.sr, silence_threshold_db=-25, min_dip_db=2.0)
        self.assertEqual(syllables, 4)

    def test_speech_and_articulation_rates(self):
        # 4 bursts in 4 seconds: total duration 4s, speech duration 1.2s
        duration = 4.0
        audio = np.zeros(int(duration * self.sr), dtype=np.float32)
        t = np.linspace(0, duration, len(audio), endpoint=False)

        burst_intervals = [(0.2, 0.5), (1.0, 1.3), (2.0, 2.3), (3.0, 3.3)]
        speech_segments = []
        for s, e in burst_intervals:
            mask = (t >= s) & (t < e)
            sub_t = t[mask]
            audio[mask] = 0.5 * np.sin(2 * np.pi * 200 * sub_t)
            speech_segments.append({"start": int(s * self.sr), "end": int(e * self.sr)})

        feats = extract_timing_features(audio, sr=self.sr, speech_segments=speech_segments)

        # 4 syllables over 4 seconds -> speech_rate = 1.0 syll/s
        self.assertAlmostEqual(feats["speech_rate_syll_per_s"], 1.0, places=1)
        # 4 syllables over 1.2s speech duration -> articulation_rate = 3.33 syll/s
        self.assertGreater(feats["articulation_rate_syll_per_s"], 3.0)
        self.assertAlmostEqual(feats["speech_ratio"], 0.3, places=1)


if __name__ == "__main__":
    unittest.main()
