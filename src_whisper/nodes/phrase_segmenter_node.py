"""
Phrase Segmenter Node - сегментация аудио на фразы с использованием Silero VAD
"""

import asyncio
import numpy as np
import torch
from typing import Optional
from dataclasses import dataclass

from .base_node import BaseNode


@dataclass
class PhraseSegment:
    """Сегмент фразы с аудио данными."""
    audio: np.ndarray  # float32, normalized [-1, 1]
    sample_rate: int
    start_time: float
    end_time: float
    duration: float


class PhraseSegmenterNode(BaseNode):
    """
    Нода для нарезки аудио на фразы с использованием Silero VAD.
    Простая и надежная детекция начала и конца речи.
    
    Вход: {"audio": bytes, "meta": dict}
    Выход: PhraseSegment (по callback на каждую фразу)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 500,
        max_speech_duration_s: float = 30.0,
        speech_pad_ms: int = 30,
        threshold: float = 0.8,
        buffer_check_interval_s: float = 1.0,
        name: str = "phrase_segmenter"
    ):
        """
        Args:
            sample_rate: частота для VAD (8000 или 16000)
            min_speech_duration_ms: минимальная длительность речи (мс)
            min_silence_duration_ms: минимальная пауза для конца фразы (мс)
            max_speech_duration_s: максимальная длительность фразы (сек)
            speech_pad_ms: отступ до/после речи (мс)
            threshold: порог VAD (0.0-1.0), меньше = чувствительнее
            buffer_check_interval_s: как часто проверять буфер (сек)
            name: имя ноды
        """
        super().__init__(name)
        
        self.target_sample_rate = sample_rate
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.max_speech_duration_s = max_speech_duration_s
        self.speech_pad_ms = speech_pad_ms
        self.threshold = threshold
        self.buffer_check_interval_s = buffer_check_interval_s
        
        # Буфер для накопления аудио
        self.buffer = []
        self.buffer_sample_rate = 48000
        
        # Silero VAD модель
        self.vad_model = None
        self.get_speech_timestamps = None
        
        # Флаг для предотвращения параллельных проверок
        self._check_in_progress = False
        
        self.logger.info(f"Initialized with Silero VAD: sample_rate={sample_rate}, "
                        f"threshold={threshold}, min_silence={min_silence_duration_ms}ms")

    async def start(self) -> None:
        """Загрузить Silero VAD модель."""
        try:
            self.logger.info("Loading Silero VAD model...")
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._load_silero_vad
            )
            
            self.logger.info("Silero VAD model loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to load Silero VAD: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Освободить ресурсы."""
        self.vad_model = None
        self.buffer.clear()
        self.logger.info("Phrase segmenter stopped")

    def _load_silero_vad(self) -> None:
        """Загрузить Silero VAD модель (синхронно)."""
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False
        )
        
        self.vad_model = model
        (get_speech_timestamps, _, _, _, _) = utils
        self.get_speech_timestamps = get_speech_timestamps

    async def process(self, data: dict) -> None:
        """
        Добавить аудио фрейм в буфер.
        
        Args:
            data: {"audio": bytes, "meta": dict}
        """
        try:
            audio_bytes = data["audio"]
            meta = data["meta"]
            
            if "sample_rate" in meta:
                self.buffer_sample_rate = meta["sample_rate"]
            
            sample_width = meta.get("sample_width", 2)
            if sample_width == 2:
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                audio_float = audio_array.astype(np.float32) / 32768.0
            else:
                audio_array = np.frombuffer(audio_bytes, dtype=np.int32)
                audio_float = audio_array.astype(np.float32) / 2147483648.0
            
            self.buffer.append(audio_float)
            
            # НЕ сбрасываем буфер, накапливаем до детекции речи
            buffer_duration = sum(len(x) for x in self.buffer) / self.buffer_sample_rate
            
            # Проверяем периодически в фоне (не блокируем прием фреймов)
            if buffer_duration >= self.buffer_check_interval_s and not self._check_in_progress:
                asyncio.create_task(self._check_buffer_async())
            
        except Exception as e:
            self.logger.error(f"Error processing audio frame: {e}", exc_info=True)

    async def _check_buffer_async(self) -> None:
        """Проверить буфер на наличие завершенных фраз (асинхронно)."""
        if self._check_in_progress:
            return
        
        self._check_in_progress = True
        
        try:
            await self._check_buffer()
        finally:
            self._check_in_progress = False
    
    async def _check_buffer(self) -> None:
        """Проверить буфер на наличие завершенных фраз."""
        if not self.buffer or not self.vad_model:
            return
        
        try:
            audio = np.concatenate(self.buffer)
            buffer_duration = len(audio) / self.buffer_sample_rate
            
            self.logger.debug(f"Checking buffer: {buffer_duration:.2f}s, {len(audio)} samples")
            
            if self.buffer_sample_rate != self.target_sample_rate:
                audio = self._resample(audio, self.buffer_sample_rate, self.target_sample_rate)
            
            vad_duration = len(audio) / self.target_sample_rate
            if vad_duration < 1.0:
                self.logger.debug(f"Buffer too short for VAD: {vad_duration:.2f}s, continuing...")
                return
            
            audio_tensor = torch.from_numpy(audio)
            
            rms = np.sqrt(np.mean(audio ** 2))
            max_amp = np.max(np.abs(audio))
            self.logger.debug(f"Audio stats: RMS={rms:.4f}, max_amp={max_amp:.4f}")
            
            # Получаем все speech timestamps
            speech_timestamps = await asyncio.get_event_loop().run_in_executor(
                None,
                self._get_timestamps,
                audio_tensor
            )
            
            self.logger.debug(f"VAD detected {len(speech_timestamps)} speech segments")
            
            if not speech_timestamps:
                # Нет речи в буфере
                # Если буфер слишком большой - очищаем
                if buffer_duration > 5.0:
                    self.logger.debug("No speech in 5+ seconds, clearing buffer")
                    self.buffer.clear()
                return
            
            # Проверяем последний сегмент - закончился ли он?
            last_segment = speech_timestamps[-1]
            last_end_sample = last_segment['end']
            samples_after_speech = len(audio) - last_end_sample
            silence_after = samples_after_speech / self.target_sample_rate
            
            self.logger.debug(f"Last segment ends at {last_end_sample}/{len(audio)}, "
                            f"silence after: {silence_after:.2f}s")
            
            # Если после последнего сегмента есть тишина >= min_silence_duration_ms
            min_silence_s = self.min_silence_duration_ms / 1000.0
            
            if silence_after >= min_silence_s:
                # Речь закончена, отправляем все завершенные сегменты
                self.logger.info(f"Speech ended (silence {silence_after:.2f}s), emitting {len(speech_timestamps)} segments")
                
                for ts in speech_timestamps:
                    start_sample = ts['start']
                    end_sample = ts['end']
                    
                    segment_audio = audio[start_sample:end_sample]
                    duration = len(segment_audio) / self.target_sample_rate
                    
                    phrase = PhraseSegment(
                        audio=segment_audio,
                        sample_rate=self.target_sample_rate,
                        start_time=start_sample / self.target_sample_rate,
                        end_time=end_sample / self.target_sample_rate,
                        duration=duration
                    )
                    
                    await self.emit(phrase)
                    self.logger.info(f"Phrase emitted: {duration:.2f}s")
                
                # Очищаем буфер
                self.buffer.clear()
            else:
                # Речь еще продолжается, ждем
                self.logger.debug(f"Speech still ongoing (silence only {silence_after:.2f}s), waiting...")
            
        except Exception as e:
            self.logger.error(f"Error checking buffer: {e}", exc_info=True)

    def _get_timestamps(self, audio_tensor):
        """Получить timestamps речи через Silero VAD."""
        try:
            timestamps = self.get_speech_timestamps(
                audio_tensor,
                self.vad_model,
                sampling_rate=self.target_sample_rate,
                min_speech_duration_ms=self.min_speech_duration_ms,
                min_silence_duration_ms=self.min_silence_duration_ms,
                max_speech_duration_s=self.max_speech_duration_s,
                speech_pad_ms=self.speech_pad_ms,
                threshold=self.threshold,
                return_seconds=False
            )
            
            if timestamps:
                self.logger.debug(f"Raw VAD timestamps: {timestamps}")
            
            return timestamps
        except Exception as e:
            self.logger.error(f"Error in VAD get_timestamps: {e}", exc_info=True)
            return []

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Ресемплировать аудио."""
        if orig_sr == target_sr:
            return audio
        
        duration = len(audio) / orig_sr
        target_length = int(duration * target_sr)
        
        indices = np.linspace(0, len(audio) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio)), audio)
        
        return resampled.astype(np.float32)
