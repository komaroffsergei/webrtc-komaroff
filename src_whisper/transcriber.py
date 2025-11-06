"""
Обертка вокруг модели Whisper с асинхронной загрузкой и транскрипцией.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
from faster_whisper import WhisperModel

from utils.audio_utils import resample_audio
from utils.model_downloader import ensure_model_available

logger = logging.getLogger("whisper.transcriber")


@dataclass
class TranscriptionResult:
    text: str
    segments: Sequence[dict]
    audio_duration: float
    transcription_time: float


class WhisperTranscriber:
    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ru",
        target_sample_rate: int = 16000,
    ):
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.target_sample_rate = target_sample_rate
        self._model: WhisperModel | None = None

    async def load(self) -> None:
        if self._model is not None:
            return
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(None, self._load_model)

    def _load_model(self) -> WhisperModel:
        """
        Загрузить модель Whisper.
        Автоматически скачает модель если она отсутствует.
        """
        logger.info(f"Loading Whisper model from {self.model_path}")
        
        # Убедиться что модель доступна (скачать если нужно)
        actual_model_path = ensure_model_available(self.model_path)
        
        logger.info(f"Loading model from {actual_model_path}")
        model = WhisperModel(
            actual_model_path,
            device=self.device,
            compute_type=self.compute_type,
        )
        
        logger.info("Model loaded successfully")
        return model

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> TranscriptionResult:
        if self._model is None:
            raise RuntimeError("Whisper model is not loaded")

        loop = asyncio.get_event_loop()
        prepared_audio = audio
        if sample_rate != self.target_sample_rate:
            prepared_audio = await loop.run_in_executor(
                None,
                resample_audio,
                audio,
                sample_rate,
                self.target_sample_rate,
            )

        start_time = time.perf_counter()
        segments = await loop.run_in_executor(None, self._run_model, prepared_audio)
        transcription_time = time.perf_counter() - start_time

        text = " ".join(segment["text"] for segment in segments).strip()
        audio_duration = len(audio) / float(sample_rate) if sample_rate else 0.0

        return TranscriptionResult(
            text=text,
            segments=segments,
            audio_duration=audio_duration,
            transcription_time=transcription_time,
        )

    def _run_model(self, audio: np.ndarray) -> List[dict]:
        assert self._model is not None, "model must be loaded"
        segments, _ = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            without_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        result: List[dict] = []
        for segment in segments:
            result.append(
                {
                    "text": segment.text.strip(),
                    "start": segment.start,
                    "end": segment.end,
                    "confidence": getattr(segment, "avg_logprob", 0.0),
                }
            )
        return result
