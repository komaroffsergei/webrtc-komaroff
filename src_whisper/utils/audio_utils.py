"""
Audio helpers for the src_whisper service.
"""

from __future__ import annotations

import numpy as np


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample 1D audio with linear interpolation (fast and dependency-free)."""
    if orig_sr == target_sr:
        return audio

    duration = len(audio) / orig_sr
    target_length = int(duration * target_sr)
    if target_length <= 0:
        return np.zeros((0,), dtype=np.float32)

    indices = np.linspace(0, len(audio) - 1, target_length)
    resampled = np.interp(indices, np.arange(len(audio)), audio)
    return resampled.astype(np.float32)

