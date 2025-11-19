from src_back.server.utils.sse import sse_log, logger


async def handle_transcription(data):
    try:
        text = data.get("text", "").strip()
        if not text:
            return

        await sse_log(app, f"Transcription: {text}", level="info")

    except Exception as e:
        logger.warning(f"transcription error: {e}")
