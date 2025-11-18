from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class PhrasePacket:
    phrase_id: str
    sample_rate: int
    duration: float
    audio: np.ndarray

    @classmethod
    def from_bytes(cls, payload: bytes) -> "PhrasePacket":
        if len(payload) < 4:
            raise ValueError("Payload is too short to contain metadata")

        meta_len = int.from_bytes(payload[:4], "big")
        meta_bytes = payload[4 : 4 + meta_len]
        if len(meta_bytes) != meta_len:
            raise ValueError("Invalid metadata length in packet")

        try:
            meta = json.loads(meta_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid metadata JSON") from exc

        pcm_bytes = payload[4 + meta_len :]
        if not pcm_bytes:
            raise ValueError("Packet does not contain PCM bytes")

        audio = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0

        phrase_id = str(meta.get("phrase_id") or "")
        if not phrase_id:
            raise ValueError("Packet metadata does not contain phrase_id")

        sample_rate = int(meta.get("sample_rate") or 0)
        if not sample_rate:
            raise ValueError("Packet metadata does not contain sample_rate")

        duration = float(meta.get("duration") or len(audio) / sample_rate)

        return cls(
            phrase_id=phrase_id,
            sample_rate=sample_rate,
            duration=duration,
            audio=audio,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "phrase_id": self.phrase_id,
            "sample_rate": self.sample_rate,
            "duration": self.duration,
        }
