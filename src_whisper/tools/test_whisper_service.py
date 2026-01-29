from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
import wave
from urllib.parse import urlparse

import nats
import numpy as np


def _build_wire_packet(meta: dict, pcm_i16: np.ndarray | None = None) -> bytes:
    meta_bytes = json.dumps(meta, ensure_ascii=True).encode("utf-8")
    payload = len(meta_bytes).to_bytes(4, "big") + meta_bytes
    if pcm_i16 is not None and pcm_i16.size:
        payload += np.asarray(pcm_i16, dtype="<i2").tobytes()
    return payload


def _load_wav_mono_16k_i16(path: str) -> np.ndarray:
    with wave.open(path, "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError("Only 16-bit PCM WAV is supported")
        if wf.getnchannels() != 1:
            raise ValueError("Only mono WAV is supported")
        if wf.getframerate() != 16000:
            raise ValueError("Only 16 kHz WAV is supported")
        frames = wf.readframes(wf.getnframes())
    return np.frombuffer(frames, dtype="<i2")


def _generate_test_audio(sr: int) -> np.ndarray:
    silence = np.zeros(int(0.3 * sr), dtype=np.int16)
    noise = np.random.normal(0, 0.15, int(1.0 * sr)).clip(-1.0, 1.0)
    noise_i16 = (noise * 32767.0).astype(np.int16)
    return np.concatenate([silence, noise_i16, silence])


async def _run(args: argparse.Namespace) -> int:
    url = urlparse(args.nats_url)
    fallback = "ws://127.0.0.1:9222"
    if args.nats_url in {"nats://127.0.0.1:4222", "nats://localhost:4222"}:
        try:
            await asyncio.wait_for(asyncio.open_connection(url.hostname or "127.0.0.1", url.port or 4222), timeout=0.2)
        except Exception:
            print(f"TCP NATS is not reachable at {args.nats_url}. Using {fallback} ...")
            args.nats_url = fallback

    nc = await nats.connect(
        servers=[args.nats_url],
        max_reconnect_attempts=0,
        connect_timeout=0.5,
    )
    inbox = nc.new_inbox()
    sub = await nc.subscribe(inbox)

    stream_id = args.stream_id or str(uuid.uuid4())
    seq = 0

    if args.mode == "phrase":
        audio_i16 = _load_wav_mono_16k_i16(args.wav) if args.wav else _generate_test_audio(16000)
        meta = {
            "type": "phrase",
            "phrase_id": str(uuid.uuid4()),
            "sample_rate": 16000,
            "duration": float(len(audio_i16) / 16000.0),
        }
        payload = _build_wire_packet(meta, audio_i16)
        await nc.publish(args.subject, payload, reply=inbox)

    else:
        audio_i16 = _load_wav_mono_16k_i16(args.wav) if args.wav else _generate_test_audio(args.sample_rate)
        frame_samples = int(args.sample_rate * args.frame_ms / 1000)
        if frame_samples <= 0:
            raise ValueError("frame_ms too small")

        for off in range(0, len(audio_i16), frame_samples):
            chunk = audio_i16[off : off + frame_samples]
            if not len(chunk):
                break
            seq += 1
            meta = {
                "type": "frame",
                "stream_id": stream_id,
                "seq": seq,
                "sample_rate": args.sample_rate,
                "sample_width": 2,
                "channels": 1,
            }
            if args.session_id:
                meta["session_id"] = args.session_id
            payload = _build_wire_packet(meta, chunk)
            await nc.publish(args.subject, payload, reply=inbox)

        seq += 1
        meta_end = {
            "type": "end",
            "stream_id": stream_id,
            "seq": seq,
            "sample_rate": args.sample_rate,
            "sample_width": 2,
            "channels": 1,
        }
        if args.session_id:
            meta_end["session_id"] = args.session_id
        await nc.publish(args.subject, _build_wire_packet(meta_end, None), reply=inbox)

    replies: list[dict] = []
    deadline = time.monotonic() + args.timeout_s
    while time.monotonic() < deadline:
        try:
            msg = await sub.next_msg(timeout=0.2)
        except asyncio.TimeoutError:
            continue
        try:
            replies.append(json.loads(msg.data.decode("utf-8")))
        except Exception:
            replies.append({"_raw": msg.data.decode("utf-8", errors="replace")})

        if args.stop_after and len(replies) >= args.stop_after:
            break

    await sub.unsubscribe()
    await nc.drain()

    print(json.dumps(replies, ensure_ascii=False, indent=2))
    if replies:
        return 0
    return 0 if args.allow_no_replies else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish audio to src_whisper over NATS and collect reply messages.")
    parser.add_argument("--nats-url", default="nats://127.0.0.1:4222")
    parser.add_argument(
        "--subject",
        default="",
        help="Target subject. If empty, uses NATS_ASR_SUBJECT + USER_ID from env.",
    )
    parser.add_argument("--mode", choices=["frame", "phrase"], default="frame")
    parser.add_argument("--wav", help="Optional WAV (mono, 16kHz, 16-bit PCM). If omitted, generates synthetic audio.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--frame-ms", type=int, default=20)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--stream-id", default="")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--stop-after", type=int, default=0, help="Stop after N replies (0 = until timeout)")
    parser.add_argument("--allow-no-replies", action="store_true")
    args = parser.parse_args()
    args.stop_after = int(args.stop_after) if args.stop_after else 0
    if not args.subject:
        import os

        prefix = (os.getenv("NATS_ASR_SUBJECT", "") or "").strip()
        user_id = (os.getenv("USER_ID", "") or "").strip()
        if not prefix or not user_id:
            raise SystemExit("Provide --subject or set NATS_ASR_SUBJECT and USER_ID in env")
        if not prefix.endswith("."):
            prefix += "."
        args.subject = prefix + user_id

    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
