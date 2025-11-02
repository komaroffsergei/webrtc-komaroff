"""
Audio Buffer - буферизация и сохранение аудио фреймов из NATS
"""

import wave
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger("whisper.audio_buffer")


class AudioBuffer:
    """
    Буфер для накопления аудио фреймов и их сохранения в WAV файл.
    """

    def __init__(self, recordings_dir: str = "recordings"):
        """
        Args:
            recordings_dir: директория для сохранения WAV файлов
        """
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(exist_ok=True)
        
        self.frames = []
        self.sample_rate = 48000  # по умолчанию
        self.channels = 1
        self.sample_width = 2  # 16-bit = 2 bytes
        
        self.current_session_id = None
        self.frame_count = 0

    def add_frame(self, audio_data: bytes, meta: dict) -> None:
        """
        Добавить аудио фрейм в буфер.
        
        Args:
            audio_data: сырые аудио данные
            meta: метаданные с информацией о формате
        """
        self.frames.append(audio_data)
        self.frame_count += 1
        
        # Обновляем параметры из метаданных
        if "sample_rate" in meta:
            self.sample_rate = meta["sample_rate"]
        if "channels" in meta:
            self.channels = meta["channels"]

    def get_audio_data(self) -> bytes:
        """
        Получить все накопленные аудио данные.
        
        Returns:
            bytes: объединенные аудио данные
        """
        return b"".join(self.frames)

    def get_duration(self) -> float:
        """
        Получить длительность накопленного аудио в секундах.
        
        Returns:
            float: длительность в секундах
        """
        total_bytes = sum(len(f) for f in self.frames)
        samples = total_bytes // self.sample_width // self.channels
        return samples / self.sample_rate

    def save_to_wav(self, filename: Optional[str] = None) -> str:
        """
        Сохранить накопленные фреймы в WAV файл.
        
        Args:
            filename: имя файла (без расширения), если None - генерируется автоматически
        
        Returns:
            str: путь к сохраненному файлу
        """
        if not self.frames:
            logger.warning("No frames to save")
            return ""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}_{self.frame_count}frames"
        
        filepath = self.recordings_dir / f"{filename}.wav"
        
        try:
            with wave.open(str(filepath), 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.sample_width)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(self.get_audio_data())
            
            duration = self.get_duration()
            logger.info(f"Saved {filepath} ({duration:.2f}s, {self.frame_count} frames)")
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error saving WAV file: {e}")
            return ""

    def clear(self) -> None:
        """Очистить буфер."""
        self.frames.clear()
        self.frame_count = 0

    def should_process(self, min_duration: float = 5.0, max_duration: float = 30.0) -> bool:
        """
        Проверить, накоплено ли достаточно аудио для обработки.
        
        Args:
            min_duration: минимальная длительность для обработки (секунды)
            max_duration: максимальная длительность (принудительная обработка)
        
        Returns:
            bool: True если нужно обработать
        """
        duration = self.get_duration()
        return min_duration <= duration <= max_duration or duration >= max_duration
