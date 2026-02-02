from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import nats
from nats import errors as nats_errors


def build_wire_packet(meta: dict, pcm_bytes: bytes | None) -> bytes:
    meta_bytes = json.dumps(meta, ensure_ascii=True).encode("utf-8")
    payload = len(meta_bytes).to_bytes(4, "big") + meta_bytes
    if pcm_bytes:
        payload += pcm_bytes
    return payload


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def convert_wav_to_pcm16le_mono(
    wav_path: str | Path,
    *,
    sample_rate: int,
) -> bytes:
    """
    Convert any WAV into 16-bit PCM (s16le), mono, `sample_rate`.

    Preferred converter is ffmpeg. If ffmpeg is not available, falls back to the
    standard library `wave` reader for 16-bit PCM WAV only (no resampling).
    """
    wav_path = str(wav_path)
    sr = int(sample_rate)
    if sr <= 0:
        raise ValueError("sample_rate must be positive")

    if _ffmpeg_available():
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            wav_path,
            "-ac",
            "1",
            "-ar",
            str(sr),
            "-f",
            "s16le",
            "-",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg failed to convert wav: {err or 'unknown error'}")
        return proc.stdout

    # Fallback: only 16-bit PCM WAV, mono or stereo, no resampling.
    try:
        with wave.open(wav_path, "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
    except Exception as exc:
        raise RuntimeError("Failed to read WAV. Install ffmpeg for broader WAV support.") from exc

    if width != 2:
        raise RuntimeError("WAV is not 16-bit PCM. Install ffmpeg for conversion.")
    if rate != sr:
        raise RuntimeError("WAV sample rate mismatch. Install ffmpeg to resample.")
    if channels not in (1, 2):
        raise RuntimeError("WAV must be mono or stereo. Install ffmpeg for conversion.")

    if channels == 1:
        return frames

    # Downmix stereo to mono by averaging L/R (int16).
    import array

    samples = array.array("h")
    samples.frombytes(frames)
    if len(samples) % 2 != 0:
        samples = samples[: len(samples) - 1]

    out = array.array("h")
    out_extend = out.append
    for i in range(0, len(samples), 2):
        out_extend(int((samples[i] + samples[i + 1]) / 2))
    return out.tobytes()


def iter_pcm_frames(
    pcm_s16le: bytes,
    *,
    sample_rate: int,
    frame_ms: int,
) -> Iterable[bytes]:
    sr = int(sample_rate)
    ms = int(frame_ms)
    if sr <= 0:
        raise ValueError("sample_rate must be positive")
    if ms <= 0:
        raise ValueError("frame_ms must be positive")

    samples_per_frame = int(sr * ms / 1000)
    if samples_per_frame <= 0:
        raise ValueError("frame_ms is too small for the given sample_rate")

    bytes_per_frame = samples_per_frame * 2
    total = len(pcm_s16le)
    if total % 2 != 0:
        raise ValueError("PCM byte length is not aligned to int16 samples")

    off = 0
    while off < total:
        chunk = pcm_s16le[off : off + bytes_per_frame]
        off += bytes_per_frame
        if len(chunk) < bytes_per_frame:
            chunk = chunk + (b"\x00" * (bytes_per_frame - len(chunk)))
        yield chunk


def _validate_exact_subject(value: str, *, arg_name: str) -> str:
    """
    Validate an exact NATS subject (no wildcards, no empty tokens).

    This prevents server-side protocol errors like "-ERR Invalid Subject" which
    close the connection and surface as ConnectionClosedError in the client.
    """
    s = (value or "").strip()
    if not s:
        raise SystemExit(f"{arg_name} is required")
    if "*" in s or ">" in s:
        raise SystemExit(f"{arg_name} must be an exact subject (wildcards are not allowed): {s}")
    if s.startswith(".") or s.endswith(".") or ".." in s:
        raise SystemExit(f"{arg_name} is not a valid subject (empty token): {s}")
    return s


def _default_out_dir() -> Path:
    return (Path(__file__).resolve().parents[1] / "out").resolve()


async def run_probe(args: argparse.Namespace) -> int:
    args.in_subject = _validate_exact_subject(args.in_subject, arg_name="--in-subject")
    args.out_subject = _validate_exact_subject(args.out_subject, arg_name="--out-subject")

    url = urlparse(args.nats_url)
    fallback_ws = "ws://127.0.0.1:9222"
    if args.nats_url in {"nats://127.0.0.1:4222", "nats://localhost:4222"}:
        try:
            await asyncio.wait_for(asyncio.open_connection(url.hostname or "127.0.0.1", url.port or 4222), timeout=0.2)
        except Exception:
            print(f"TCP NATS is not reachable at {args.nats_url}. Using {fallback_ws} ...")
            args.nats_url = fallback_ws

    nc = await nats.connect(
        servers=[args.nats_url],
        max_reconnect_attempts=0,
        connect_timeout=1.0,
    )
    sub = await nc.subscribe(args.out_subject)

    session_id = args.session_id

    pcm = convert_wav_to_pcm16le_mono(args.wav_path, sample_rate=args.sample_rate)

    frames_sent = 0
    seq = 0
    for frame in iter_pcm_frames(pcm, sample_rate=args.sample_rate, frame_ms=args.frame_ms):
        meta = {
            "type": "frame",
            "seq": seq,
            "sample_rate": args.sample_rate,
            "sample_width": 2,
            "channels": 1,
            "session_id": session_id,
        }
        await nc.publish(args.in_subject, build_wire_packet(meta, frame))
        frames_sent += 1
        seq += 1
        if args.mode == "realtime":
            await asyncio.sleep(args.frame_ms / 1000.0)

    meta_end = {
        "type": "end",
        "seq": seq,
        "sample_rate": args.sample_rate,
        "sample_width": 2,
        "channels": 1,
        "session_id": session_id,
    }
    end_sent_at = time.monotonic()
    last_reply_time = end_sent_at
    await nc.publish(args.in_subject, build_wire_packet(meta_end, None))

    out_path = Path(args.out) if args.out else None
    if out_path is None:
        wav_base = Path(args.wav_path).name
        out_path = _default_out_dir() / f"{wav_base}.{session_id}.whisper_replies.jsonl"
    out_path = out_path.resolve()

    replies_received = 0
    max_wait_deadline = end_sent_at + args.max_wait_s

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        try:
            while True:
                now = time.monotonic()
                if now - last_reply_time > args.timeout_s:
                    break
                if now > max_wait_deadline:
                    break

                try:
                    msg = await sub.next_msg(timeout=0.2)
                except asyncio.TimeoutError:
                    continue

                last_reply_time = time.monotonic()
                raw = msg.data.decode("utf-8", errors="replace")
                if not raw:
                    # Ignore empty payloads (not JSON).
                    continue

                # Validate it's JSON (keep the original formatting in output).
                json.loads(raw)
                f.write(raw.rstrip("\n") + "\n")
                replies_received += 1
        except nats_errors.ConnectionClosedError:
            print("error: NATS connection closed. Check that subjects are valid and NATS is reachable.")
            return 2

    await sub.unsubscribe()
    await nc.drain()

    print(f"in_subject: {args.in_subject}")
    print(f"out_subject: {args.out_subject}")
    print(f"session_id: {session_id}")
    print(f"sample_rate: {args.sample_rate}")
    print(f"frame_ms: {args.frame_ms}")
    print(f"mode: {args.mode}")
    print(f"frames_sent: {frames_sent}")
    print(f"replies_received: {replies_received}")
    print(f"out_file: {out_path}")
    if replies_received == 0:
        print("error: no replies received (timeout). Ensure src_whisper is running and subscribed to the matching token.")
        return 2
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src_whisper.tools.whisper_probe",
        description="Send WAV as PCM frames to src_whisper over NATS and write JSONL replies from output subject.",
    )
    parser.add_argument("wav_path", help="Input WAV file")
    parser.add_argument("--in-subject", required=True, help="NATS subject to publish audio packets to")
    parser.add_argument("--out-subject", required=True, help="NATS subject to subscribe and collect replies from")
    parser.add_argument("--session-id", required=True, help="Session id to include into meta.session_id")
    parser.add_argument("--nats-url", default=os.getenv("NATS_URL", "nats://127.0.0.1:4222"))
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--frame-ms", type=int, default=20)
    parser.add_argument("--mode", choices=["fast", "realtime"], default="fast")
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--max-wait-s", type=float, default=120.0)
    parser.add_argument("--out", default="", help="Output JSONL path")
    args = parser.parse_args()

    if args.sample_rate <= 0:
        raise SystemExit("--sample-rate must be positive")
    if args.frame_ms <= 0:
        raise SystemExit("--frame-ms must be positive")
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be positive")
    if args.max_wait_s <= 0:
        raise SystemExit("--max-wait-s must be positive")

    raise SystemExit(asyncio.run(run_probe(args)))


if __name__ == "__main__":
    main()
