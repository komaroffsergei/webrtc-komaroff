"""
VAD Processor - детекция голосовой активности для сегментации аудио
"""

import logging
import numpy as np
from typing import List, Tuple, Optional

logger = logging.getLogger("whisper.vad")


class VADProcessor:
    """
    Voice Activity Detection - определение сегментов с голосом.
    Разделяет аудио на отрывки, содержащие речь, исключая тишину.
    """

    def __init__(
        self,
        silence_threshold: float = 0.8,
        min_silence_duration: float = 1.0,
        min_speech_duration: float = 1.0,
        padding_duration: float = 0.3,
        sample_rate: int = 48000
    ):
        """
        Args:
            silence_threshold: порог амплитуды для определения тишины (0.0-1.0)
            min_silence_duration: минимальная длительность тишины между фразами (сек)
            min_speech_duration: минимальная длительность речевого сегмента (сек)
            padding_duration: отступ до/после речи (сек)
            sample_rate: частота дискретизации
        """
        self.silence_threshold = silence_threshold
        self.min_silence_duration = min_silence_duration
        self.min_speech_duration = min_speech_duration
        self.padding_duration = padding_duration
        self.sample_rate = sample_rate
        
        # Переводим длительности в сэмплы
        self.min_silence_samples = int(min_silence_duration * sample_rate)
        self.min_speech_samples = int(min_speech_duration * sample_rate)
        self.padding_samples = int(padding_duration * sample_rate)

    def detect_speech_segments(self, audio: np.ndarray) -> List[Tuple[int, int]]:
        """
        Найти сегменты с речью в аудио.
        
        Args:
            audio: аудио массив (normalized float32, [-1.0, 1.0])
        
        Returns:
            List[Tuple[start, end]]: список сегментов (индексы сэмплов)
        """
        if len(audio) == 0:
            return []
        
        # Вычисляем энергию (RMS) по окнам
        window_size = int(0.02 * self.sample_rate)  # 20ms окно
        hop_size = window_size // 2
        
        energy = []
        for i in range(0, len(audio) - window_size, hop_size):
            window = audio[i:i + window_size]
            rms = np.sqrt(np.mean(window ** 2))
            energy.append(rms)
        
        if not energy:
            return []
        
        energy = np.array(energy)
        
        # Определяем голосовую активность
        is_speech = energy > self.silence_threshold
        
        # Находим границы сегментов
        segments = []
        in_speech = False
        start_idx = 0
        silence_counter = 0
        
        for i, active in enumerate(is_speech):
            sample_idx = i * hop_size
            
            if active:
                if not in_speech:
                    # Начало речи
                    start_idx = max(0, sample_idx - self.padding_samples)
                    in_speech = True
                    silence_counter = 0
                else:
                    # Продолжение речи
                    silence_counter = 0
            else:
                if in_speech:
                    # Возможный конец речи
                    silence_counter += hop_size
                    
                    if silence_counter >= self.min_silence_samples:
                        # Достаточно тишины - конец сегмента
                        end_idx = min(len(audio), sample_idx + self.padding_samples)
                        
                        # Проверяем минимальную длительность
                        if end_idx - start_idx >= self.min_speech_samples:
                            segments.append((start_idx, end_idx))
                        
                        in_speech = False
                        silence_counter = 0
        
        # Обрабатываем последний сегмент
        if in_speech:
            end_idx = len(audio)
            if end_idx - start_idx >= self.min_speech_samples:
                segments.append((start_idx, end_idx))
        
        logger.debug(f"Detected {len(segments)} speech segments in {len(audio)} samples")
        
        return segments

    def split_audio_by_speech(self, audio: np.ndarray) -> List[np.ndarray]:
        """
        Разделить аудио на сегменты с речью.
        
        Args:
            audio: аудио массив (normalized float32)
        
        Returns:
            List[np.ndarray]: список аудио сегментов с речью
        """
        segments = self.detect_speech_segments(audio)
        
        audio_segments = []
        for start, end in segments:
            segment = audio[start:end]
            if len(segment) > 0:
                audio_segments.append(segment)
        
        logger.info(f"Split audio into {len(audio_segments)} speech segments")
        
        return audio_segments

    def get_speech_ratio(self, audio: np.ndarray) -> float:
        """
        Вычислить долю речи в аудио.
        
        Args:
            audio: аудио массив
        
        Returns:
            float: доля речи (0.0-1.0)
        """
        if len(audio) == 0:
            return 0.0
        
        segments = self.detect_speech_segments(audio)
        
        speech_samples = sum(end - start for start, end in segments)
        total_samples = len(audio)
        
        return speech_samples / total_samples if total_samples > 0 else 0.0

    def has_speech(self, audio: np.ndarray) -> bool:
        """
        Проверить, содержит ли аудио речь.
        
        Args:
            audio: аудио массив
        
        Returns:
            bool: True если есть речь
        """
        segments = self.detect_speech_segments(audio)
        return len(segments) > 0
