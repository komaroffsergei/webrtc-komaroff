#!/usr/bin/env python3
import asyncio
import json
import logging
import os
from typing import Tuple, Optional

import nats

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("whisper")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
IN_SUBJ = os.getenv("AUDIO_SUBJ") or os.getenv("NATS_SUBJECT") or "audio.frames"
IN_SUBJ = IN_SUBJ if not str(IN_SUBJ).endswith(".") else f"{IN_SUBJ}frames"
OUT_SUBJ = os.getenv("WHISPER_SUBJ") or (f"{IN_SUBJ}.whisper" if not IN_SUBJ.endswith(".") else f"{IN_SUBJ}whisper")


def decode_payload(data: bytes) -> Tuple[Optional[dict], Optional[bytes]]:
    if len(data) < 4:
        return None, None
    meta_len = int.from_bytes(data[:4], "big")
    end = 4 + meta_len
    if end > len(data):
        return None, None
    try:
        meta = json.loads(data[4:end].decode("utf-8"))
    except Exception:
        meta = {}
    audio = data[end:]
    return meta, audio


def encode_payload(meta: dict, audio: bytes) -> bytes:
    mb = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    return len(mb).to_bytes(4, "big") + mb + (audio or b"")


async def main():
    urls = [u.strip() for u in str(NATS_URL).split(",") if u.strip()]
    nc = await nats.connect(
        servers=urls or [NATS_URL],
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
        ping_interval=10,
    )
    log.info(f"connected to {nc.connected_url.netloc} IN={IN_SUBJ} OUT={OUT_SUBJ}")

    async def handler(msg: nats.aio.client.Msg):
        meta, audio = decode_payload(msg.data)
        if meta is None:
            log.warning("bad payload; skip")
            return
        note = meta.get("note", "")
        meta["note"] = f"from-whisper:{note}"
        out = encode_payload(meta, audio or b"")
        await nc.publish(OUT_SUBJ, out)

    await nc.subscribe(IN_SUBJ, cb=handler)
    log.info("subscription established")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        try:
            await nc.drain()
        except Exception:
            pass
        try:
            await nc.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
