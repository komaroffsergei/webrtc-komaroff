from __future__ import annotations

import json
from typing import Any

import numpy as np


def parse_wire_packet(payload: bytes) -> tuple[dict[str, Any], np.ndarray]:
    """
    Parse `[meta_len:u32 BE][meta_json UTF-8][pcm int16 LE bytes]`.

    Returns `(meta, audio_float32)` where audio is normalized to [-1, 1].
    PCM may be empty (e.g. for control packets) and will be returned as an empty array.
    """
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
        return meta, np.zeros((0,), dtype=np.float32)

    audio = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0
    return meta, audio

