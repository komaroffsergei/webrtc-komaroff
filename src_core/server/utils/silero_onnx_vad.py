"""Utility helpers for running Silero VAD with ONNX Runtime."""

from __future__ import annotations

import logging
import math
import os
import shutil
import warnings
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)


def ensure_model_path(model_path: str) -> str:
    """Return the absolute path to the Silero model and ensure that it exists."""

    resolved = Path(model_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Silero VAD model not found at '{resolved}'. "
            "Set VAD_MODEL_PATH or mount the model file."
        )
    return str(resolved)


def download_model_file(model_path: str, url: Optional[str] = None) -> str:
    """Download the Silero ONNX model to the given path."""

    target = Path(model_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")

    download_url = url
    logger.info("Downloading Silero VAD model from %s", download_url)
    with urlopen(download_url) as response, open(tmp_path, "wb") as dst:
        shutil.copyfileobj(response, dst)
    tmp_path.replace(target)
    logger.info("Silero VAD model saved to %s", target)
    return str(target)




class SileroOnnxVAD:
    """Thin wrapper around the Silero ONNX model with state management."""

    def __init__(self, model_path: str, force_cpu: bool = True):

        self.model_path = ensure_model_path(model_path)
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1

        providers = None
        if force_cpu:
            providers = ["CPUExecutionProvider"]

        self.session = ort.InferenceSession(
            self.model_path,
            providers=providers,
            sess_options=opts,
        )

        basename = os.path.basename(self.model_path)
        self.sample_rates = [16000] if "16k" in basename else [8000, 16000]

        self._context: Optional[np.ndarray] = None
        self._state: Optional[np.ndarray] = None
        self._last_sr: int = 0
        self._last_batch_size: int = 0
        self.reset_states()

    def reset_states(self, batch_size: int = 1) -> None:
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context = None
        self._last_sr = 0
        self._last_batch_size = batch_size

    def _validate_input(self, chunk: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
        data = np.asarray(chunk, dtype=np.float32)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        if data.ndim != 2:
            raise ValueError("Audio chunk must be 1D or 2D array")

        if sr != 16000 and sr % 16000 == 0:
            step = sr // 16000
            data = data[:, ::step]
            sr = 16000

        if sr not in self.sample_rates:
            raise ValueError(
                f"Supported sampling rates are {self.sample_rates} (or multiples of 16000)"
            )

        expected = 512 if sr == 16000 else 256
        if data.shape[-1] != expected:
            raise ValueError(
                f"Provided number of samples is {data.shape[-1]} (expected {expected} for sr={sr})"
            )

        return data, sr

    def __call__(self, chunk: np.ndarray, sr: int) -> float:
        data, sr = self._validate_input(chunk, sr)
        batch_size = data.shape[0]
        context_size = 64 if sr == 16000 else 32

        if not self._last_batch_size:
            self.reset_states(batch_size)
        if (self._last_sr and self._last_sr != sr) or (
            self._last_batch_size and self._last_batch_size != batch_size
        ):
            self.reset_states(batch_size)

        if self._context is None or self._context.shape[0] != batch_size:
            self._context = np.zeros((batch_size, context_size), dtype=np.float32)

        concat = np.concatenate([self._context, data], axis=1)
        inputs = {
            "input": concat.astype(np.float32),
            "state": self._state.astype(np.float32),
            "sr": np.array(sr, dtype=np.int64),
        }
        out, state = self.session.run(None, inputs)

        self._state = state.astype(np.float32)
        self._context = concat[:, -context_size:]
        self._last_sr = sr
        self._last_batch_size = batch_size

        return float(np.asarray(out).reshape(-1)[0])


def _to_mono(audio: np.ndarray) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 0:
        return data.reshape(1)
    if data.ndim > 1:
        data = data.reshape(-1)
    return data


def _maybe_visualize(probs: List[float], step: float) -> None:
    try:
        import pandas as pd  # type: ignore

        pd.DataFrame({"probs": probs}, index=[x * step for x in range(len(probs))]).plot(
            figsize=(16, 8), kind="area", ylim=[0, 1.05], xlim=[0, len(probs) * step]
        )
    except Exception:
        logger.warning("Failed to visualize VAD probabilities", exc_info=True)


def get_speech_timestamps(
    audio: np.ndarray,
    model: SileroOnnxVAD,
    threshold: float = 0.5,
    sampling_rate: int = 16000,
    min_speech_duration_ms: int = 250,
    max_speech_duration_s: float = math.inf,
    min_silence_duration_ms: int = 100,
    speech_pad_ms: int = 30,
    return_seconds: bool = False,
    time_resolution: int = 1,
    visualize_probs: bool = False,
    progress_tracking_callback: Optional[Callable[[float], None]] = None,
    neg_threshold: Optional[float] = None,
    window_size_samples: Optional[int] = None,
    min_silence_at_max_speech: float = 98,
    use_max_poss_sil_at_max_speech: bool = True,
) -> List[dict]:
    """Port of Silero's get_speech_timestamps that works with NumPy arrays."""

    data = _to_mono(audio)

    if sampling_rate > 16000 and (sampling_rate % 16000 == 0):
        step = sampling_rate // 16000
        sampling_rate = 16000
        data = data[::step]
        warnings.warn("Sampling rate is a multiply of 16000, casting to 16000 manually!")
    else:
        step = 1

    if sampling_rate not in [8000, 16000]:
        raise ValueError("Silero VAD models support only 8000 or 16000 Hz audio")

    window_size_samples = int(window_size_samples or (512 if sampling_rate == 16000 else 256))

    model.reset_states()
    min_speech_samples = int(sampling_rate * min_speech_duration_ms / 1000)
    speech_pad_samples = int(sampling_rate * speech_pad_ms / 1000)
    if math.isinf(max_speech_duration_s):
        max_speech_samples = math.inf
    else:
        max_speech_samples = int(
            sampling_rate * max_speech_duration_s - window_size_samples - 2 * speech_pad_samples
        )
    min_silence_samples = int(sampling_rate * min_silence_duration_ms / 1000)
    min_silence_samples_at_max_speech = int(sampling_rate * min_silence_at_max_speech / 1000)

    audio_length_samples = len(data)
    if not audio_length_samples:
        return []

    speech_probs: List[float] = []
    for current_start in range(0, audio_length_samples, window_size_samples):
        chunk = data[current_start : current_start + window_size_samples]
        if len(chunk) < window_size_samples:
            chunk = np.pad(chunk, (0, window_size_samples - len(chunk)))

        prob = float(model(chunk.reshape(1, -1), sampling_rate))
        speech_probs.append(prob)

        progress = min(current_start + window_size_samples, audio_length_samples)
        if progress_tracking_callback and audio_length_samples:
            progress_tracking_callback((progress / audio_length_samples) * 100)

    triggered = False
    speeches: List[dict] = []
    current_speech: dict = {}

    if neg_threshold is None:
        neg_threshold = max(threshold - 0.15, 0.01)
    temp_end = 0
    prev_end = next_start = 0
    possible_ends: List[tuple[int, int]] = []

    for i, speech_prob in enumerate(speech_probs):
        cur_sample = window_size_samples * i

        if (speech_prob >= threshold) and temp_end:
            sil_dur = cur_sample - temp_end
            if sil_dur > min_silence_samples_at_max_speech:
                possible_ends.append((temp_end, sil_dur))
            temp_end = 0
            if next_start < prev_end:
                next_start = cur_sample

        if (speech_prob >= threshold) and not triggered:
            triggered = True
            current_speech["start"] = cur_sample
            continue

        if triggered and current_speech and (
            cur_sample - current_speech["start"] > max_speech_samples
        ):
            if use_max_poss_sil_at_max_speech and possible_ends:
                prev_end, dur = max(possible_ends, key=lambda x: x[1])
                current_speech["end"] = prev_end
                speeches.append(current_speech)
                current_speech = {}
                next_start = prev_end + dur

                if next_start < prev_end + cur_sample:
                    current_speech["start"] = next_start
                else:
                    triggered = False
                prev_end = next_start = temp_end = 0
                possible_ends = []
            else:
                if prev_end:
                    current_speech["end"] = prev_end
                    speeches.append(current_speech)
                    current_speech = {}
                    if next_start < prev_end:
                        triggered = False
                    else:
                        current_speech["start"] = next_start
                    prev_end = next_start = temp_end = 0
                    possible_ends = []
                else:
                    current_speech["end"] = cur_sample
                    speeches.append(current_speech)
                    current_speech = {}
                    prev_end = next_start = temp_end = 0
                    triggered = False
                    possible_ends = []
                    continue

        if (speech_prob < neg_threshold) and triggered:
            if not temp_end:
                temp_end = cur_sample
            sil_dur_now = cur_sample - temp_end

            if (
                not use_max_poss_sil_at_max_speech
                and sil_dur_now > min_silence_samples_at_max_speech
            ):
                prev_end = temp_end

            if sil_dur_now < min_silence_samples:
                continue
            else:
                current_speech["end"] = temp_end
                if (current_speech["end"] - current_speech["start"]) > min_speech_samples:
                    speeches.append(current_speech)
                current_speech = {}
                prev_end = next_start = temp_end = 0
                triggered = False
                possible_ends = []
                continue

    if current_speech and (audio_length_samples - current_speech["start"]) > min_speech_samples:
        current_speech["end"] = audio_length_samples
        speeches.append(current_speech)

    for i, speech in enumerate(speeches):
        if i == 0:
            speech["start"] = int(max(0, speech["start"] - speech_pad_samples))
        if i != len(speeches) - 1:
            silence_duration = speeches[i + 1]["start"] - speech["end"]
            if silence_duration < 2 * speech_pad_samples:
                speech["end"] += int(silence_duration // 2)
                speeches[i + 1]["start"] = int(
                    max(0, speeches[i + 1]["start"] - silence_duration // 2)
                )
            else:
                speech["end"] = int(min(audio_length_samples, speech["end"] + speech_pad_samples))
                speeches[i + 1]["start"] = int(
                    max(0, speeches[i + 1]["start"] - speech_pad_samples)
                )
        else:
            speech["end"] = int(min(audio_length_samples, speech["end"] + speech_pad_samples))

    if return_seconds:
        audio_length_seconds = audio_length_samples / sampling_rate
        for speech_dict in speeches:
            speech_dict["start"] = max(
                round(speech_dict["start"] / sampling_rate, time_resolution), 0
            )
            speech_dict["end"] = min(
                round(speech_dict["end"] / sampling_rate, time_resolution),
                audio_length_seconds,
            )
    elif step > 1:
        for speech_dict in speeches:
            speech_dict["start"] *= step
            speech_dict["end"] *= step

    if visualize_probs:
        _maybe_visualize(speech_probs, window_size_samples / sampling_rate)

    return speeches


__all__ = [
    "SileroOnnxVAD",
    "get_speech_timestamps",
    "ensure_model_path",
    "download_model_file",
]
