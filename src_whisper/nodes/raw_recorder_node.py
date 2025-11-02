"""
Raw Recorder Node - запись сырого аудио из NATS для диагностики
"""

import wave
import asyncio
from pathlib import Path
from datetime import datetime
from collections import deque

from .base_node import BaseNode


class RawRecorderNode(BaseNode):
    """
    Нода для записи сырого аудио из NATS без обработки.
    Диагностика задержек и качества передачи.
    
    Вход: {"audio": bytes, "meta": dict}
    Выход: {"audio": bytes, "meta": dict} (прокидывает дальше)
    """

    def __init__(
        self,
        recordings_dir: str = "recordings_raw",
        max_duration_s: float = 10.0,
        enabled: bool = True,
        name: str = "raw_recorder"
    ):
        """
        Args:
            recordings_dir: директория для сохранения
            max_duration_s: максимальная длительность записи (сек)
            enabled: включить/выключить запись
            name: имя ноды
        """
        super().__init__(name)
        
        self.recordings_dir = Path(recordings_dir)
        self.max_duration_s = max_duration_s
        self.enabled = enabled
        
        # Буфер для накопления фреймов
        self.frames_buffer = deque()
        self.sample_rate = 48000
        self.channels = 1
        self.sample_width = 2
        self.total_samples = 0
        
        # Временные метки
        self.first_frame_time = None
        self.last_frame_time = None
        self.frame_count = 0
        
        if self.enabled:
            self.recordings_dir.mkdir(exist_ok=True)
            self.logger.info(f"Raw recorder enabled: {self.recordings_dir}")
        else:
            self.logger.info("Raw recorder disabled")

    async def start(self) -> None:
        """Инициализация."""
        self.first_frame_time = None
        self.frame_count = 0
        self.total_samples = 0

    async def stop(self) -> None:
        """Сохранить последнюю запись если есть."""
        if self.enabled and self.frames_buffer:
            await self._save_recording()

    async def process(self, data: dict) -> None:
        """
        Накопить фрейм и прокинуть дальше.
        
        Args:
            data: {"audio": bytes, "meta": dict}
        """
        # Прокидываем дальше немедленно
        await self.emit(data)
        
        if not self.enabled:
            return
        
        try:
            audio_bytes = data["audio"]
            meta = data["meta"]
            
            # Обновляем метаданные
            if "sample_rate" in meta:
                self.sample_rate = meta["sample_rate"]
            if "channels" in meta:
                self.channels = meta["channels"]
            
            # Отметка времени
            current_time = asyncio.get_event_loop().time()
            
            if self.first_frame_time is None:
                self.first_frame_time = current_time
                self.logger.info("Started raw recording")
            
            # Добавляем фрейм
            self.frames_buffer.append(audio_bytes)
            self.frame_count += 1
            
            # Вычисляем длительность
            sample_width = meta.get("sample_width", 2)
            samples_in_frame = len(audio_bytes) // sample_width // self.channels
            self.total_samples += samples_in_frame
            
            duration = self.total_samples / self.sample_rate
            
            # Логируем каждые 100 фреймов
            if self.frame_count % 100 == 0:
                elapsed = current_time - self.first_frame_time
                self.logger.info(f"Recording: {duration:.2f}s audio, {elapsed:.2f}s elapsed, "
                               f"{self.frame_count} frames (avg {self.frame_count/elapsed:.1f} fps)")
            
            # Сохраняем если достигли максимума
            if duration >= self.max_duration_s:
                await self._save_recording()
                
        except Exception as e:
            self.logger.error(f"Error in raw recorder: {e}", exc_info=True)

    async def _save_recording(self) -> None:
        """Сохранить накопленное аудио."""
        if not self.frames_buffer:
            return
        
        try:
            # Формируем имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_{timestamp}_{self.frame_count}frames.wav"
            filepath = self.recordings_dir / filename
            
            # Объединяем все фреймы
            audio_data = b"".join(self.frames_buffer)
            
            # Сохраняем в executor
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._save_wav,
                filepath,
                audio_data
            )
            
            duration = self.total_samples / self.sample_rate
            elapsed = asyncio.get_event_loop().time() - self.first_frame_time
            
            self.logger.info(f"Saved raw recording: {filename}")
            self.logger.info(f"  Duration: {duration:.2f}s, Elapsed: {elapsed:.2f}s, "
                           f"Delay: {elapsed-duration:.2f}s, Frames: {self.frame_count}")
            
            # Очищаем буфер
            self.frames_buffer.clear()
            self.first_frame_time = None
            self.frame_count = 0
            self.total_samples = 0
            
        except Exception as e:
            self.logger.error(f"Error saving raw recording: {e}", exc_info=True)

    def _save_wav(self, filepath: Path, audio_data: bytes) -> None:
        """Сохранить WAV (синхронно)."""
        try:
            with wave.open(str(filepath), 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.sample_width)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_data)
        except Exception as e:
            self.logger.error(f"Error in _save_wav: {e}", exc_info=True)
