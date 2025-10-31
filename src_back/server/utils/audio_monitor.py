"""
Audio Monitor - мониторинг уровня звука и детекция проблем
"""

import asyncio
import logging
import time
from typing import Optional

import numpy as np
from av import AudioFrame

from ..handlers.sse import sse_broadcast

logger = logging.getLogger("audio.AudioMonitor")


class AudioMonitor:
    """
    Мониторинг аудио для детекции проблем:
    - Слишком громкий сигнал (clipping)
    - Слишком тихий сигнал
    - Высокий уровень шума
    
    Отправляет предупреждения через SSE.
    """

    def __init__(
        self,
        app,
        check_interval: float = 2.0,
        loud_threshold: float = 0.9,
        quiet_threshold: float = 0.02,
        noise_threshold: float = 0.15,
        min_frames_for_check: int = 10
    ):
        """
        Args:
            app: aiohttp application для отправки SSE
            check_interval: интервал проверки в секундах
            loud_threshold: порог для определения слишком громкого сигнала (0.0-1.0)
            quiet_threshold: порог для определения тихого сигнала (0.0-1.0)
            noise_threshold: порог RMS для определения шума при отсутствии речи
            min_frames_for_check: минимальное количество фреймов для анализа
        """
        self.app = app
        self.check_interval = check_interval
        self.loud_threshold = loud_threshold
        self.quiet_threshold = quiet_threshold
        self.noise_threshold = noise_threshold
        self.min_frames_for_check = min_frames_for_check

        self.samples_buffer = []
        self.last_check_time = time.time()
        self.last_warning_type = None
        self.last_warning_time = 0
        self.warning_cooldown = 10.0  # не спамить предупреждениями чаще раз в N секунд

    def add_frame(self, frame: AudioFrame) -> None:
        """Добавить фрейм для анализа."""
        try:
            pcm = frame.to_ndarray()
            if pcm.ndim == 1:
                pcm = pcm[np.newaxis, :]
            elif pcm.ndim == 2 and pcm.shape[0] == frame.samples:
                pcm = pcm.T
            
            # Нормализуем к диапазону [-1.0, 1.0]
            if pcm.dtype == np.int16:
                normalized = pcm.astype(np.float32) / 32768.0
            elif pcm.dtype == np.int32:
                normalized = pcm.astype(np.float32) / 2147483648.0
            else:
                normalized = pcm.astype(np.float32)
            
            self.samples_buffer.append(normalized)
            
            # Ограничиваем размер буфера
            if len(self.samples_buffer) > 100:
                self.samples_buffer = self.samples_buffer[-100:]
                
        except Exception as e:
            logger.debug(f"Error adding frame to monitor: {e}")

    async def check_and_warn(self) -> None:
        """Проверить накопленные данные и отправить предупреждение если нужно."""
        current_time = time.time()
        
        # Проверяем только с заданным интервалом
        if current_time - self.last_check_time < self.check_interval:
            return
        
        self.last_check_time = current_time
        
        if len(self.samples_buffer) < self.min_frames_for_check:
            return
        
        try:
            # Объединяем все сэмплы в один массив
            all_samples = np.concatenate(self.samples_buffer, axis=1)
            
            # Вычисляем метрики
            max_amplitude = np.max(np.abs(all_samples))
            rms = np.sqrt(np.mean(all_samples ** 2))
            
            warning_type = None
            
            # Проверка на клиппинг (слишком громко)
            if max_amplitude > self.loud_threshold:
                warning_type = "mic_too_loud"
            
            # Проверка на тихий сигнал
            elif max_amplitude < self.quiet_threshold:
                warning_type = "mic_too_quiet"
            
            # Проверка на шум (высокий RMS при низкой амплитуде)
            elif rms > self.noise_threshold and max_amplitude < 0.3:
                warning_type = "mic_too_noise"
            
            # Отправляем предупреждение если нужно
            if warning_type:
                await self._send_warning(warning_type, current_time)
            
            # Очищаем буфер после проверки
            self.samples_buffer.clear()
            
        except Exception as e:
            logger.error(f"Error in audio monitoring: {e}")

    async def _send_warning(self, warning_type: str, current_time: float) -> None:
        """Отправить предупреждение через SSE с учетом cooldown."""
        # Проверяем cooldown чтобы не спамить
        if (self.last_warning_type == warning_type and 
            current_time - self.last_warning_time < self.warning_cooldown):
            return
        
        self.last_warning_type = warning_type
        self.last_warning_time = current_time
        
        await sse_broadcast(self.app, {
            "type": "warning",
            "descr": warning_type
        })
        
        logger.info(f"Audio warning sent: {warning_type}")
