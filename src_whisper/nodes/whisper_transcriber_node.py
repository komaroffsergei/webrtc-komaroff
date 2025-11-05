"""
Whisper Transcriber Node - распознавание речи через Whisper
"""

import asyncio
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

from .base_node import BaseNode
from .phrase_segmenter_node import PhraseSegment

try:
    from utils.audio_utils import resample_audio
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from utils.audio_utils import resample_audio


class WhisperTranscriberNode(BaseNode):
    """
    Нода для распознавания речи через faster-whisper.
    Вход: PhraseSegment
    Выход: {"text": str, "segments": list, "phrase": PhraseSegment} (callback на каждую транскрипцию)
    """

    def __init__(
            self,
            model_path: str = "models/whisper-medium-ru-fine-ct2",
            device: str = "cpu",
            compute_type: str = "int8",
            language: str = "ru",
            name: str = "whisper_transcriber"
    ):
        """
        Args:
            model_path: путь к модели CTranslate2
            device: 'cpu' или 'cuda'
            compute_type: 'int8', 'float16', 'float32'
            language: язык распознавания
            name: имя ноды
        """
        super().__init__(name)

        self.model_path = Path(model_path)
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.model: Optional[WhisperModel] = None

    async def start(self) -> None:
        """Загрузить модель Whisper."""
        try:
            self.logger.info(f"Loading Whisper model from {self.model_path}")

            # Загружаем модель в executor (блокирующая операция)
            self.model = await asyncio.get_event_loop().run_in_executor(
                None,
                self._load_model
            )

            self.logger.info("Whisper model loaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to load Whisper model: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Выгрузить модель."""
        self.model = None
        self.logger.info("Whisper model unloaded")

    def _load_model(self) -> WhisperModel:
        """Загрузить модель (синхронно)."""
        return WhisperModel(
            str(self.model_path),
            device=self.device,
            compute_type=self.compute_type
        )

    async def process(self, phrase: PhraseSegment) -> None:
        """
        Распознать речь в фразе.

        Args:
            phrase: сегмент фразы для распознавания
        """
        if not self.model:
            self.logger.error("Model not loaded")
            return

        try:
            import time
            from datetime import datetime
            
            start_time = time.time()
            start_timestamp = datetime.utcnow().isoformat() + "Z"
            self.logger.info(f"Transcribing phrase ({phrase.duration:.2f}s)")

            # Ресемплируем если нужно (Whisper ожидает 16kHz)
            audio = phrase.audio
            if phrase.sample_rate != 16000:
                audio = await asyncio.get_event_loop().run_in_executor(
                    None,
                    resample_audio,
                    audio,
                    phrase.sample_rate,
                    16000
                )

            # Транскрибируем в executor
            segments_list = await asyncio.get_event_loop().run_in_executor(
                None,
                self._transcribe,
                audio
            )

            # Объединяем текст
            full_text = " ".join(seg["text"] for seg in segments_list)
            if full_text.strip():
                transcription_time = time.time() - start_time
                rt_factor = transcription_time / phrase.duration if phrase.duration else 0.0
                self.logger.info(
                    f"Transcription completed: '{full_text}' "
                    f"(audio: {phrase.duration:.2f}s, transcription: {transcription_time:.2f}s, "
                    f"RTF: {rt_factor:.2f}x)"
                )

                await self.emit({
                    "text": full_text,
                    "segments": segments_list,
                    "phrase": phrase,
                    "transcription_time": transcription_time,
                    "audio_duration": phrase.duration,
                    "start_timestamp": start_timestamp
                })
            else:
                self.logger.debug("Empty transcription")

        except Exception as e:
            self.logger.error(f"Error transcribing phrase: {e}", exc_info=True)

    def _transcribe(self, audio) -> list:
        """
        Транскрибировать аудио (синхронно).
 
        Args:
            audio: numpy array (float32, 16kHz)
 
        Returns:
            list: список сегментов с текстом
        """
        segments, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            without_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False
        )
 
        results = []
        for segment in segments:
            results.append({
                "text": segment.text.strip(),
                "start": segment.start,
                "end": segment.end,
                "confidence": getattr(segment, 'avg_logprob', 0.0)
            })
 
        return results
 
