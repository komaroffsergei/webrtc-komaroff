"""
Audio Utils - общие утилиты для работы с аудио
"""

import numpy as np


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """
    Ресемплировать аудио с использованием линейной интерполяции.
    
    Args:
        audio: numpy array с аудио данными
        orig_sr: исходная частота дискретизации
        target_sr: целевая частота дискретизации
    
    Returns:
        numpy array: ресемплированное аудио
    """
    if orig_sr == target_sr:
        return audio
    
    duration = len(audio) / orig_sr
    target_length = int(duration * target_sr)
    
    indices = np.linspace(0, len(audio) - 1, target_length)
    resampled = np.interp(indices, np.arange(len(audio)), audio)
    
    return resampled.astype(np.float32)
