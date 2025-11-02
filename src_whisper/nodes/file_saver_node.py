"""
File Saver Node - сохранение фраз в WAV файлы
"""

import wave
import asyncio
from pathlib import Path
from datetime import datetime

from .base_node import BaseNode
from .phrase_segmenter_node import PhraseSegment


class FileSaverNode(BaseNode):
    """
    Нода для сохранения фраз в WAV файлы (асинхронно).
    Вход: PhraseSegment
    Выход: PhraseSegment (прокидывает дальше после сохранения)
    """

    def __init__(
        self,
        recordings_dir: str = "recordings",
        enabled: bool = True,
        name: str = "file_saver"
    ):
        """
        Args:
            recordings_dir: директория для сохранения
            enabled: включить/выключить сохранение
            name: имя ноды
        """
        super().__init__(name)
        
        self.recordings_dir = Path(recordings_dir)
        self.enabled = enabled
        self.phrase_counter = 0
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if self.enabled:
            self.recordings_dir.mkdir(exist_ok=True)
            self.logger.info(f"File saver enabled: {self.recordings_dir}")
        else:
            self.logger.info("File saver disabled")

    async def start(self) -> None:
        """Нода не требует фоновых задач."""
        pass

    async def stop(self) -> None:
        """Нода не требует очистки."""
        pass

    async def process(self, phrase: PhraseSegment) -> None:
        """
        Сохранить фразу в файл (асинхронно) и передать дальше.
        
        Args:
            phrase: сегмент фразы для сохранения
        """
        if not self.enabled:
            # Прокидываем дальше без сохранения
            await self.emit(phrase)
            return
        
        try:
            # Увеличиваем счетчик
            self.phrase_counter += 1
            
            # Формируем имя файла
            filename = f"phrase_{self.session_id}_{self.phrase_counter:04d}.wav"
            filepath = self.recordings_dir / filename
            
            # Сохраняем асинхронно в пуле потоков
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._save_wav,
                filepath,
                phrase
            )
            
            self.logger.info(f"Saved: {filename} ({phrase.duration:.2f}s)")
            
            # Прокидываем дальше
            await self.emit(phrase)
            
        except Exception as e:
            self.logger.error(f"Error saving file: {e}", exc_info=True)
            # Прокидываем дальше даже при ошибке
            await self.emit(phrase)

    def _save_wav(self, filepath: Path, phrase: PhraseSegment) -> None:
        """
        Сохранить WAV файл (синхронная функция для executor).
        
        Args:
            filepath: путь к файлу
            phrase: сегмент для сохранения
        """
        try:
            # Конвертируем float32 в int16
            import numpy as np
            audio_int16 = (phrase.audio * 32768.0).astype(np.int16)
            
            # Сохраняем WAV
            with wave.open(str(filepath), 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(phrase.sample_rate)
                wav_file.writeframes(audio_int16.tobytes())
                
        except Exception as e:
            self.logger.error(f"Error in _save_wav: {e}", exc_info=True)
