"""Pure functions and generator logic for window aggregation and quality scoring."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, Iterator, List, Optional, Union
import cv2
import numpy as np



def compute_brightness_penalty(mean_brightness: float) -> float:
    """Compute a brightness quality multiplier in [0.0, 1.0].

    Heuristic:
    - Grayscale pixel values range from 0 (pitch black) to 255 (overexposed).
    - Optimal range: [40, 215] -> multiplier = 1.0.
    - Too dark: [0, 40) -> linearly scales from 0.0 to 1.0.
    - Too bright: (215, 255] -> linearly scales from 1.0 to 0.0.
    """
    if math.isnan(mean_brightness):
        return 0.0
    if mean_brightness <= 0.0:
        return 0.0
    if mean_brightness >= 255.0:
        return 0.0
    if 40.0 <= mean_brightness <= 215.0:
        return 1.0
    if mean_brightness < 40.0:
        return float(mean_brightness / 40.0)
    # mean_brightness > 215.0
    return float(max(0.0, (255.0 - mean_brightness) / (255.0 - 215.0)))


def aggregate_window(
    frames: List[Dict[str, Any]],
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate a list of per-frame feature dicts into a single contract record.

    Output contract:
    {
      "modality": "facial",
      "t": <ISO-8601 UTC timestamp of window end>,
      "features": {
        "au1_mean": ..., "au1_std": ..., ...,
        "expressiveness": ..., "head_pose_std": ..., "au_activation_rate": ...
      },
      "quality": <float 0-1>,
      "valid": <bool>
    }
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    total_frames = len(frames)
    if total_frames == 0:
        return {
            "modality": "facial",
            "t": timestamp,
            "features": {
                "expressiveness": 0.0,
                "head_pose_std": 0.0,
                "au_activation_rate": 0.0,
            },
            "quality": 0.0,
            "valid": False,
        }

    # Identify frames where face was detected
    detected_frames = [f for f in frames if f.get("face_detected", False)]
    face_detection_ratio = len(detected_frames) / float(total_frames)

    # Frame brightness penalty across all frames in window
    brightnesses = [
        f.get("mean_brightness", 0.0) for f in frames if "mean_brightness" in f
    ]
    if brightnesses:
        avg_brightness = float(np.mean(brightnesses))
        brightness_penalty = compute_brightness_penalty(avg_brightness)
    else:
        brightness_penalty = 1.0

    quality = round(face_detection_ratio * brightness_penalty, 4)
    is_valid = bool(quality >= 0.5)

    # Collect AU intensities from valid detection frames
    au_keys_seen: List[str] = []
    for f in detected_frames:
        for k in f.get("au_intensities", {}).keys():
            if k not in au_keys_seen:
                au_keys_seen.append(k)

    features: Dict[str, float] = {}

    all_intensities_flat: List[float] = []
    for key in sorted(au_keys_seen):
        # Normalize key name: e.g. "au_1_intensity" -> "au1", "au1" -> "au1"
        cleaned_key = key.replace("_intensity", "").replace("_", "")
        vals = [
            f["au_intensities"][key]
            for f in detected_frames
            if key in f.get("au_intensities", {})
        ]
        if vals:
            m = float(np.mean(vals))
            s = float(np.std(vals))
            features[f"{cleaned_key}_mean"] = round(m, 4)
            features[f"{cleaned_key}_std"] = round(s, 4)
            all_intensities_flat.extend(vals)
        else:
            features[f"{cleaned_key}_mean"] = 0.0
            features[f"{cleaned_key}_std"] = 0.0

    # Global feature: expressiveness (mean of all AU intensities across window)
    if all_intensities_flat:
        features["expressiveness"] = round(float(np.mean(all_intensities_flat)), 4)
    else:
        features["expressiveness"] = 0.0

    # Global feature: head_pose_std (std of pitch, yaw, roll angles)
    pitches = []
    yaws = []
    rolls = []
    for f in detected_frames:
        pose = f.get("head_pose")
        if pose and isinstance(pose, dict):
            if "pitch" in pose and pose["pitch"] is not None:
                pitches.append(pose["pitch"])
            if "yaw" in pose and pose["yaw"] is not None:
                yaws.append(pose["yaw"])
            if "roll" in pose and pose["roll"] is not None:
                rolls.append(pose["roll"])

    if len(pitches) >= 2:
        std_p = float(np.std(pitches))
        std_y = float(np.std(yaws))
        std_r = float(np.std(rolls))
        # Overall head pose variation as mean standard deviation across axes
        features["head_pose_std"] = round(float((std_p + std_y + std_r) / 3.0), 4)
    else:
        features["head_pose_std"] = 0.0

    # Global feature: au_activation_rate (fraction of frames with any AU detected)
    active_frames_count = 0
    for f in detected_frames:
        aus = f.get("detected_aus", {})
        if any(v == 1 for v in aus.values()):
            active_frames_count += 1
    au_activation_rate = (
        (active_frames_count / float(total_frames)) if total_frames > 0 else 0.0
    )
    features["au_activation_rate"] = round(au_activation_rate, 4)

    return {
        "modality": "facial",
        "t": timestamp,
        "features": features,
        "quality": quality,
        "valid": is_valid,
    }


class WindowAggregator:
    """Buffers incoming frames and emits aggregated windows of fixed size."""

    def __init__(self, window_size: int) -> None:
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        self.window_size = window_size
        self.buffer: List[Dict[str, Any]] = []

    def add_frame(self, frame_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a frame dict. If window size is reached, return aggregated window."""
        self.buffer.append(frame_data)
        if len(self.buffer) >= self.window_size:
            window = aggregate_window(self.buffer)
            self.buffer = []
            return window
        return None

    def flush(self) -> Optional[Dict[str, Any]]:
        """Flush remaining buffered frames if any."""
        if not self.buffer:
            return None
        window = aggregate_window(self.buffer)
        self.buffer = []
        return window


def stream_windows(
    source: Union[int, str],
    window_sec: float = 30.0,
    fps: float = 5.0,
    device: str = "cpu",
    weights_download_dir: str = "./weights_libreface",
    flush_on_end: bool = False,
) -> Iterator[Dict[str, Any]]:
    """Capture frames from video/webcam source, aggregate into windows, and yield records.

    Args:
        source: Camera index (int) or path to video file (str).
        window_sec: Length of aggregation window in seconds.
        fps: Sampling rate in frames per second.
        device: Device for inference ('cpu' or 'cuda').
        weights_download_dir: Directory where LibreFace weights are stored.
        flush_on_end: Whether to emit any partial window when video ends or loop finishes.
    """
    from facial.extractor import LibreFaceExtractor

    extractor = LibreFaceExtractor(
        device=device, weights_download_dir=weights_download_dir
    )

    cap_source = int(source) if isinstance(source, str) and source.isdigit() else source
    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video source: {source}")

    frames_per_window = max(1, int(round(window_sec * fps)))
    aggregator = WindowAggregator(window_size=frames_per_window)

    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if not source_fps or source_fps <= 0 or math.isnan(source_fps):
        source_fps = 30.0

    frame_interval = max(1, int(round(source_fps / fps)))
    frame_idx = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                # Video ended or camera disconnected
                break

            if frame_idx % frame_interval == 0:
                frame_data = extractor.extract_frame(frame)
                window = aggregator.add_frame(frame_data)
                if window is not None:
                    yield window

            frame_idx += 1

        if flush_on_end:
            partial_window = aggregator.flush()
            if partial_window is not None:
                yield partial_window

    finally:
        cap.release()
