from aiohttp import web

from ..utils.sse import sse_log

async def handle_startup(app: web.Application):
    # валидация моделей
    print("startup")
    # asyncio.create_task(handle_startup(app))
    # await sse_log(
    #     app,
    #     "startup msg",
    #     level="info"
    # )


async def handle_startup_sse(request: web.Request):
    await sse_log(request.app, "SSE connection established", level="info")
    await sse_log(
        request.app,
        "startup msg",
        level="info"
    )
    # привязываю событие при старте (отрабатывает после старте
    # app.handle_startup_sse = handle_startup