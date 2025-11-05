"""
Структуры и утилиты для работы с пакетами фраз, поступающих через NATS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

import numpy as np


_INT16_SCALE = 32768.0
_INT32_SCALE = 2147483648.0


class PhrasePacketError(RuntimeError):
    """Ошибка разбора входящего пакета."""


@dataclass
class PhrasePacket:
    phrase_id: str | None
    sample_rate: int
    sample_width: int
    audio: np.ndarray  # float32, диапазон [-1, 1]
    metadata: Dict[str, Any]

    @property
    def duration(self) -> float:
        if not self.sample_rate:
            return 0.0
        return len(self.audio) / float(self.sample_rate)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "PhrasePacket":
        if len(payload) < 4:
            raise PhrasePacketError("payload too short for metadata header")

        meta_len = int.from_bytes(payload[:4], "big")
        if meta_len < 0 or len(payload) < 4 + meta_len:
            raise PhrasePacketError("invalid metadata length")

        meta_raw = payload[4 : 4 + meta_len]
        try:
            metadata: Dict[str, Any] = json.loads(meta_raw.decode("utf-8")) if meta_raw else {}
        except json.JSONDecodeError as exc:
            raise PhrasePacketError(f"invalid metadata json: {exc}") from exc

        audio_bytes = payload[4 + meta_len :]
        if not audio_bytes:
            raise PhrasePacketError("audio payload is empty")

        sample_width = int(metadata.get("sample_width", 2))
        if sample_width == 2:
            audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / _INT16_SCALE
        elif sample_width == 4:
            audio = np.frombuffer(audio_bytes, dtype=np.int32).astype(np.float32) / _INT32_SCALE
        else:
            raise PhrasePacketError(f"unsupported sample width: {sample_width}")

        sample_rate = int(metadata.get("sample_rate", 16000))
        phrase_id = metadata.get("phrase_id")

        return cls(
            phrase_id=str(phrase_id) if phrase_id is not None else None,
            sample_rate=sample_rate,
            sample_width=sample_width,
            audio=audio,
            metadata=metadata,
        )
