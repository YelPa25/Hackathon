"""Two-sided Cumulative Sum (CUSUM) for detecting persistent subtle drift."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


class TwoSidedCUSUM:
    """Tracks positive and negative cumulative sum on robust z-scores."""

    def __init__(self, k: float = 0.5, h: float = 5.0) -> None:
        self.k = k  # Slack parameter (drift allowance)
        self.h = h  # Alarm threshold
        self.pos: float = 0.0
        self.neg: float = 0.0

    def update(self, z: float) -> Tuple[float, float, bool]:
        """Update CUSUM with current z-score.

        Returns:
            Tuple of (pos_cusum, neg_cusum, is_flagged).
        """
        # C+ = max(0, C+ + z - k)
        self.pos = max(0.0, self.pos + z - self.k)
        # C- = max(0, C- - z - k)
        self.neg = max(0.0, self.neg - z - self.k)

        flagged = (self.pos >= self.h) or (self.neg >= self.h)
        return self.pos, self.neg, flagged

    def max_cusum(self) -> float:
        """Maximum accumulation between positive and negative sides."""
        return max(self.pos, self.neg)

    def reset(self) -> None:
        """Reset accumulated deviations back to zero."""
        self.pos = 0.0
        self.neg = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Serialize state."""
        return {"pos": self.pos, "neg": self.neg, "k": self.k, "h": self.h}

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "TwoSidedCUSUM":
        """Deserialize state."""
        inst = cls(k=data.get("k", 0.5), h=data.get("h", 5.0))
        inst.pos = data.get("pos", 0.0)
        inst.neg = data.get("neg", 0.0)
        return inst
