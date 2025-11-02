"""
Whisper Processor - обработка аудио через faster-whisper
"""

import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from faster_whisper import WhisperModel

logger = logging.getLogger("whisper.processor")


class WhisperProcessor:
    """
    Процессор для распознавания речи через faster-whisper (CTranslate2).
    """

    def __init__(
        self,
        model_path: str = "models/whisper-medium-ru-fine-ct2",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ru"
    ):
        """
        Args:
            model_path: путь к модели CTranslate2
            device: устройство ('cpu' или 'cuda')
            compute_type: тип вычислений ('int8', 'float16', 'float32')
            language: язык распознавания
        """
        self.model_path = Path(model_path)
        self.device = device
        self.compute_type = compute_type
        self.language = language
        
        logger.info(f"Loading Whisper model from {self.model_path}")
        
        try:
            self.model = WhisperModel(
                str(self.model_path),
                device=device,
                compute_type=compute_type
            )
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 48000,
        channels: int = 1,
        sample_width: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Распознать речь из аудио данных.
        
        Args:
            audio_data: сырые аудио данные
            sample_rate: частота дискретизации
            channels: количество каналов
            sample_width: ширина сэмпла в байтах (2 для 16-bit)
        
        Returns:
            List[Dict]: список сегментов с транскрипцией
        """
        try:
            # Конвертируем байты в numpy array
            if sample_width == 2:
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
            elif sample_width == 4:
                audio_array = np.frombuffer(audio_data, dtype=np.int32)
            else:
                logger.error(f"Unsupported sample width: {sample_width}")
                return []
            
            # Нормализуем к float32 [-1.0, 1.0]
            if sample_width == 2:
                audio_float = audio_array.astype(np.float32) / 32768.0
            else:
                audio_float = audio_array.astype(np.float32) / 2147483648.0
            
            # Если стерео, берем первый канал
            if channels > 1:
                audio_float = audio_float[::channels]
            
            # Ресемплируем если нужно (Whisper ожидает 16kHz)
            if sample_rate != 16000:
                audio_float = self._resample(audio_float, sample_rate, 16000)
            
            # Транскрибируем
            segments, info = self.model.transcribe(
                audio_float,
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            results = []
            for segment in segments:
                results.append({
                    "text": segment.text.strip(),
                    "start": segment.start,
                    "end": segment.end,
                    "confidence": getattr(segment, 'avg_logprob', 0.0),
                    "language": info.language,
                    "language_probability": info.language_probability
                })
            
            logger.info(f"Transcribed {len(results)} segments")
            return results
            
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return []

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
        Простое ресемплирование аудио (линейная интерполяция).
        Для production лучше использовать librosa или scipy.
        """
        if orig_sr == target_sr:
            return audio
        
        duration = len(audio) / orig_sr
        target_length = int(duration * target_sr)
        
        # Линейная интерполяция
        indices = np.linspace(0, len(audio) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio)), audio)
        
        return resampled.astype(np.float32)

    def transcribe_file(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Распознать речь из WAV файла.
        
        Args:
            filepath: путь к WAV файлу
        
        Returns:
            List[Dict]: список сегментов с транскрипцией
        """
        try:
            segments, info = self.model.transcribe(
                filepath,
                language=self.language,
                beam_size=5,
                vad_filter=True
            )
            
            results = []
            for segment in segments:
                results.append({
                    "text": segment.text.strip(),
                    "start": segment.start,
                    "end": segment.end,
                    "confidence": getattr(segment, 'avg_logprob', 0.0),
                    "language": info.language,
                    "language_probability": info.language_probability
                })
            
            logger.info(f"Transcribed {len(results)} segments from {filepath}")
            return results
            
        except Exception as e:
            logger.error(f"Error transcribing file {filepath}: {e}")
            return []
