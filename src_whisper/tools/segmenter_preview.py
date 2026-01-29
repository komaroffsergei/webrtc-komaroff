from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

from src_whisper.utils.audio_utils import resample_audio
from src_whisper.utils.silero_onnx_vad import SileroOnnxVAD, get_speech_timestamps


def _read_wav_mono_int16(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if sample_width != 2:
        raise ValueError(f"Only 16-bit PCM WAV is supported (got sample_width={sample_width})")

    audio = np.frombuffer(frames, dtype="<i2")
    if channels == 2:
        audio = audio.reshape(-1, 2).mean(axis=1).astype(np.int16)
    elif channels != 1:
        raise ValueError(f"Unsupported channel count: {channels}")

    return audio, int(sample_rate)


def _write_wav_mono_int16(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.asarray(audio, dtype="<i2").tobytes()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm)


def _float32_from_int16(audio: np.ndarray) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32) / 32768.0


def _int16_from_float32(audio: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    return (x * 32767.0).astype(np.int16)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Preview Whisper stream segmentation (offline, no NATS).")
    p.add_argument("wav", type=Path, help="Input WAV (16-bit PCM).")
    p.add_argument("--vad-model", type=Path, required=True, help="Path to silero_vad.onnx")
    p.add_argument("--out-dir", type=Path, default=Path("out_segments"), help="Output directory")

    p.add_argument("--vad-sample-rate", type=int, default=16000)
    p.add_argument("--frame-duration-ms", type=int, default=20)
    p.add_argument("--buffer-check-interval-s", type=float, default=1.0)
    p.add_argument("--min-speech-ms", type=int, default=250)
    p.add_argument("--min-silence-ms", type=int, default=500)
    p.add_argument("--max-speech-s", type=float, default=30.0)
    p.add_argument("--speech-pad-ms", type=int, default=30)
    p.add_argument("--vad-threshold", type=float, default=0.8)
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    pcm_i16, src_sr = _read_wav_mono_int16(args.wav)
    src_audio = _float32_from_int16(pcm_i16)

    vad_sr = int(args.vad_sample_rate)
    frame_len = int(src_sr * args.frame_duration_ms / 1000)
    if frame_len <= 0:
        raise ValueError("Invalid frame length")

    vad = SileroOnnxVAD(str(args.vad_model))

    buffer: list[np.ndarray] = []
    buffer_samples = 0
    segment_index = 0

    def check_and_maybe_flush(*, flush: bool) -> None:
        nonlocal buffer, buffer_samples, segment_index
        if not buffer:
            return

        audio = np.concatenate(buffer)
        if src_sr != vad_sr:
            audio = resample_audio(audio, src_sr, vad_sr)

        if not flush and (len(audio) / vad_sr) < 1.0:
            return

        timestamps = get_speech_timestamps(
            audio,
            vad,
            threshold=float(args.vad_threshold),
            sampling_rate=vad_sr,
            min_speech_duration_ms=int(args.min_speech_ms),
            min_silence_duration_ms=int(args.min_silence_ms),
            max_speech_duration_s=float(args.max_speech_s),
            speech_pad_ms=int(args.speech_pad_ms),
            return_seconds=False,
        )

        if not timestamps:
            if (len(audio) / vad_sr) > 5.0:
                buffer = []
                buffer_samples = 0
            return

        should_flush = flush
        if not should_flush:
            last_end = int(timestamps[-1]["end"])
            silence_after = (len(audio) - last_end) / vad_sr
            should_flush = silence_after >= (int(args.min_silence_ms) / 1000.0)
        if not should_flush:
            return

        for ts in timestamps:
            start = int(ts["start"])
            end = int(ts["end"])
            segment = audio[start:end]
            dur_ms = int(1000.0 * (len(segment) / vad_sr)) if vad_sr else 0
            start_ms = int(1000.0 * (start / vad_sr)) if vad_sr else 0
            end_ms = int(1000.0 * (end / vad_sr)) if vad_sr else 0

            segment_index += 1
            out_path = args.out_dir / f"segment_{segment_index:03d}_{start_ms}-{end_ms}ms_{dur_ms}ms.wav"
            _write_wav_mono_int16(out_path, _int16_from_float32(segment), vad_sr)
            print(f"segment #{segment_index}: {start_ms}..{end_ms} ms ({dur_ms} ms) -> {out_path}")

        buffer = []
        buffer_samples = 0

    for i in range(0, len(src_audio), frame_len):
        frame = src_audio[i : i + frame_len]
        if frame.size == 0:
            continue
        buffer.append(frame)
        buffer_samples += int(frame.size)

        duration = buffer_samples / max(1, src_sr)
        if duration >= float(args.buffer_check_interval_s):
            check_and_maybe_flush(flush=False)

    check_and_maybe_flush(flush=True)


if __name__ == "__main__":
    main()

