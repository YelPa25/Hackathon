"""Main stream_windows generator and module exports for speech analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

import numpy as np

from speech.audio import AudioStreamer, load_audio, slice_windows
from speech.embedding import XLSRecorder
from speech.features import extract_egemaps, extract_timing_features, get_speech_segments
from speech.quality import compute_audio_quality


def process_window(
    audio: np.ndarray,
    mode: str,
    sr: int = 16000,
    layers: Sequence[int] = (6, 9, 12, 15, 18, 24),
    recorder: Optional[XLSRecorder] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Process a single audio window and return a contract-compliant record.

    Contract:
    {
      "modality": "speech",
      "t": "<ISO-8601 UTC timestamp of window end>",
      "mode": "checkin" | "continuous",
      "features": { ...interpretable and timing features, flat dict of floats... },
      "embedding": { "layers": [6, 9, ...], "vectors": { "6": [floats], "9": [floats], ... } },
      "quality": <float 0-1>,
      "valid": <bool>
    }
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    if recorder is None:
        recorder = XLSRecorder(device="cpu", sample_rate=sr)

    # 1. Silero VAD speech detection
    speech_segments = get_speech_segments(audio, sr=sr)

    # 2. Timing features (speech rate, pause ratio, syllables)
    timing_feats = extract_timing_features(audio, sr=sr, speech_segments=speech_segments)

    # 3. openSMILE eGeMAPSv02 functionals
    headline_feats, full_egemaps = extract_egemaps(audio, sr=sr)

    # Combine interpretable features into a flat dict of floats
    features: Dict[str, float] = {}
    features.update(headline_feats)
    features.update(timing_feats)
    features.update(full_egemaps)

    # 4. Audio Quality calculation
    quality, is_valid, _ = compute_audio_quality(
        audio,
        sr=sr,
        speech_segments=speech_segments,
        speech_ratio=timing_feats.get("speech_ratio", 0.0),
    )

    # 5. XLS-R per-layer embeddings
    embedding_vectors = recorder.extract_layers(audio, layers=layers)
    embedding_contract = {
        "layers": list(layers),
        "vectors": embedding_vectors,
    }

    return {
        "modality": "speech",
        "t": timestamp,
        "mode": mode,
        "features": features,
        "embedding": embedding_contract,
        "quality": quality,
        "valid": is_valid,
    }


def stream_windows(
    source: Union[str, int, np.ndarray],
    mode: str = "continuous",
    window_s: float = 30.0,
    layers: Sequence[int] = (6, 9, 12, 15, 18, 24),
    sr: int = 16000,
    device: str = "cpu",
) -> Iterator[Dict[str, Any]]:
    """Capture/load audio, process into windows, and yield contract-compliant records.

    Args:
        source: Audio filepath (str), 'mic' (or 0 for microphone), or 1D audio numpy array.
        mode: 'checkin' (whole recording treated as 1 window) or 'continuous'.
        window_s: Window size in seconds for continuous mode (default: 30.0).
        layers: XLS-R transformer layers to extract.
        sr: Sample rate (default: 16000).
        device: Device for PyTorch models ('cpu').

    Yields:
        Dict conforming to the speech output contract.
    """
    recorder = XLSRecorder(device=device, sample_rate=sr)

    # Check if microphone streaming
    is_mic = source == "mic" or source == 0 or (isinstance(source, str) and source.isdigit())

    if is_mic:
        if mode == "checkin":
            # For checkin with mic source, record one standardized duration (e.g., 30s)
            from speech.audio import record_microphone
            mic_dev = int(source) if (isinstance(source, str) and source.isdigit()) else None
            audio = record_microphone(duration_s=window_s, sample_rate=sr, device=mic_dev)
            record = process_window(audio, mode="checkin", sr=sr, layers=layers, recorder=recorder)
            yield record
        else:
            mic_dev = int(source) if (isinstance(source, str) and source.isdigit()) else None
            with AudioStreamer(window_s=window_s, sample_rate=sr, device=mic_dev) as streamer:
                for chunk in streamer.iter_windows():
                    yield process_window(chunk, mode="continuous", sr=sr, layers=layers, recorder=recorder)
    else:
        # File or array source
        audio, _ = load_audio(source, target_sr=sr)

        if mode == "checkin":
            # The whole clip is one window
            yield process_window(audio, mode="checkin", sr=sr, layers=layers, recorder=recorder)
        else:
            # Continuous mode: slice into non-overlapping windows of window_s
            window_samples = int(round(window_s * sr))
            for chunk in slice_windows(audio, window_samples=window_samples, discard_partial=True):
                yield process_window(chunk, mode="continuous", sr=sr, layers=layers, recorder=recorder)
