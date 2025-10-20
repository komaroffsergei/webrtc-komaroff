import asyncio
import logging
import time

from aiohttp import web

from .utils.validate import get_params, validate_sdp

logger = logging.getLogger("webrtc")


async def handle_offer(request):
    t0 = time.monotonic()
    [params, err] = await get_params(request)
    t_json = time.monotonic()
    if err is not None:
        return web.json_response({"error": err}, status=400)

    sdp = params.get("sdp")
    ok, err = validate_sdp(sdp)
    t_validate = time.monotonic()
    if not ok:
        return web.json_response({"error": err}, status=400)

    t_parse = time.monotonic()
    call_manager = request.app["call_manager"]
    resp, error = await call_manager.handle_offer(params)
    t_done = time.monotonic()

    if error:
        logger.info(
            "offer_timing_total: json=%.2fms validate=%.2fms parse=%.2fms total=%.2fms",
            (t_json - t0) * 1000,
            (t_validate - t_json) * 1000,
            (t_parse - t_validate) * 1000,
            (t_done - t0) * 1000,
        )
        return web.json_response({"error": error}, status=400)

    logger.info(
        "offer_timing_total: json=%.2fms validate=%.2fms parse=%.2fms setRemote+create+setLocal=see-above total=%.2fms",
        (t_json - t0) * 1000,
        (t_validate - t_json) * 1000,
        (t_parse - t_validate) * 1000,
        (t_done - t0) * 1000,
    )
    return web.json_response(resp)


async def handle_index(request):
    from .utils.config import STATIC_DIR
    import os
    logger.debug("Serving index.html")
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))



async def handle_shutdown(app):
    logger.info("Shutdown: closing all peer connections")
    pcs = list(app["pcs"])
    await asyncio.gather(*(pc.close() for pc in pcs), return_exceptions=True)
    app["pcs"].clear()
    logger.info("Shutdown complete")