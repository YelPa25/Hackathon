"""Audio capture, loading, resampling, and windowing utilities."""

from __future__ import annotations

import math
import os
import queue
import time
from typing import Generator, Iterator, Optional, Tuple, Union

import numpy as np
import sounddevice as sd
import soundfile as sf
import torch


TARGET_SAMPLE_RATE = 16000


def load_audio(
    source: Union[str, np.ndarray],
    target_sr: int = TARGET_SAMPLE_RATE,
) -> Tuple[np.ndarray, int]:
    """Load an audio file or array, convert to mono, and resample to target_sr.

    Args:
        source: Filepath (str) or raw numpy array.
        target_sr: Target sample rate (default 16000 Hz).

    Returns:
        Tuple of (audio_1d_float32, sample_rate).
    """
    if isinstance(source, str):
        if not os.path.isfile(source):
            raise FileNotFoundError(f"Audio file not found: {source}")
        audio, sr = sf.read(source, dtype="float32")
    else:
        audio = np.asarray(source, dtype=np.float32)
        sr = target_sr

    # Convert to mono if multichannel
    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)

    # Resample if necessary using simple linear or sinc interpolation
    if sr != target_sr:
        num_samples = int(round(len(audio) * float(target_sr) / float(sr)))
        # Resample with numpy interpolation
        orig_indices = np.linspace(0, len(audio) - 1, len(audio))
        new_indices = np.linspace(0, len(audio) - 1, num_samples)
        audio = np.interp(new_indices, orig_indices, audio).astype(np.float32)
        sr = target_sr

    return audio.astype(np.float32), sr


def record_microphone(
    duration_s: float,
    sample_rate: int = TARGET_SAMPLE_RATE,
    device: Optional[int] = None,
) -> np.ndarray:
    """Record mono audio from the default or specified microphone for a duration.

    Args:
        duration_s: Duration in seconds to record.
        sample_rate: Sample rate (default: 16000).
        device: Audio device index.

    Returns:
        1D numpy float32 array.
    """
    num_samples = int(round(duration_s * sample_rate))
    recording = sd.rec(
        frames=num_samples,
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    return recording.squeeze().astype(np.float32)


def slice_windows(
    audio: np.ndarray,
    window_samples: int,
    discard_partial: bool = True,
) -> Generator[np.ndarray, None, None]:
    """Slice a 1D audio array into non-overlapping windows."""
    n = len(audio)
    for start in range(0, n, window_samples):
        chunk = audio[start : start + window_samples]
        if len(chunk) < window_samples:
            if not discard_partial and len(chunk) > 0:
                yield chunk
            break
        yield chunk


class AudioStreamer:
    """Microphone streaming queue yielding fixed-size non-overlapping windows."""

    def __init__(
        self,
        window_s: float = 30.0,
        sample_rate: int = TARGET_SAMPLE_RATE,
        device: Optional[int] = None,
    ) -> None:
        self.window_s = window_s
        self.sample_rate = sample_rate
        self.window_samples = int(round(window_s * sample_rate))
        self.device = device
        self.q: queue.Queue[np.ndarray] = queue.Queue()
        self.buffer = np.empty((0,), dtype=np.float32)
        self.stream: Optional[sd.InputStream] = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass
        self.q.put(indata.copy().squeeze())

    def __enter__(self) -> "AudioStreamer":
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self.stream.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()

    def iter_windows(self) -> Iterator[np.ndarray]:
        """Yield fixed-size audio windows from the live stream."""
        while self.stream and self.stream.active:
            try:
                block = self.q.get(timeout=1.0)
                self.buffer = np.concatenate([self.buffer, block])
                while len(self.buffer) >= self.window_samples:
                    win = self.buffer[: self.window_samples]
                    self.buffer = self.buffer[self.window_samples :]
                    yield win
            except queue.Empty:
                continue
