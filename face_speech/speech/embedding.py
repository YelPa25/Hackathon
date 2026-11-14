"""Wav2Vec2 XLS-R embedding extractor with per-layer mean pooling."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import torch
from transformers import Wav2Vec2Model


# Global cached model instance to ensure loading once
_XLS_R_MODEL: Optional[Wav2Vec2Model] = None


def get_xls_r_model(
    model_name: str = "facebook/wav2vec2-xls-r-300m",
    device: str = "cpu",
) -> Wav2Vec2Model:
    """Load and cache the XLS-R model once on the specified device."""
    global _XLS_R_MODEL
    if _XLS_R_MODEL is None:
        _XLS_R_MODEL = Wav2Vec2Model.from_pretrained(model_name)
        _XLS_R_MODEL.to(device)
        _XLS_R_MODEL.eval()
    return _XLS_R_MODEL


class XLSRecorder:
    """Extracts mean-pooled hidden-state representations from facebook/wav2vec2-xls-r-300m."""

    def __init__(
        self,
        model_name: str = "facebook/wav2vec2-xls-r-300m",
        device: str = "cpu",
        chunk_size_s: float = 30.0,
        sample_rate: int = 16000,
    ) -> None:
        self.device = device
        self.chunk_size_s = chunk_size_s
        self.sample_rate = sample_rate
        self.chunk_samples = int(round(chunk_size_s * sample_rate))
        self.model = get_xls_r_model(model_name=model_name, device=device)

    def extract_layers(
        self,
        audio: np.ndarray,
        layers: Sequence[int] = (6, 9, 12, 15, 18, 24),
    ) -> Dict[str, List[float]]:
        """Extract mean-pooled embedding vectors for specified layers.

        Args:
            audio: 1D float32 audio waveform resampled to 16 kHz.
            layers: Transformer layer indices (1 to 24) to extract.

        Returns:
            Dict mapping layer number string (e.g. "6") to 1024-dimensional float list.
        """
        if len(audio) == 0:
            return {str(l): [0.0] * 1024 for l in layers}

        total_samples = len(audio)
        # Process in chunks of chunk_samples to preserve memory
        chunk_embeddings: Dict[int, List[np.ndarray]] = {l: [] for l in layers}

        with torch.inference_mode():
            for start in range(0, total_samples, self.chunk_samples):
                chunk = audio[start : start + self.chunk_samples]
                if len(chunk) < 160:  # Less than 10ms, skip
                    continue

                input_tensor = (
                    torch.from_numpy(chunk).unsqueeze(0).to(self.device).float()
                )
                outputs = self.model(input_tensor, output_hidden_states=True)

                # outputs.hidden_states is a tuple of (initial_projection + 24 layers) -> length 25
                for l in layers:
                    if 0 <= l < len(outputs.hidden_states):
                        # Shape: (1, time_steps, hidden_dim)
                        hidden = outputs.hidden_states[l]
                        pooled = hidden.mean(dim=1).squeeze(0).cpu().numpy()
                        chunk_embeddings[l].append(pooled)

        # Average chunk pooled vectors over the full window
        result: Dict[str, List[float]] = {}
        for l in layers:
            if chunk_embeddings[l]:
                avg_vec = np.mean(chunk_embeddings[l], axis=0)
                # Round to 5 decimal places for clean storage
                result[str(l)] = [round(float(x), 5) for x in avg_vec]
            else:
                result[str(l)] = [0.0] * 1024

        return result
