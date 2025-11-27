import asyncio
import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()
HOST = os.getenv("LLM_HOST", "127.0.0.1")
PORT = int(os.getenv("LLM_PORT", "6007"))

config = uvicorn.Config(
    "main:app",
    host=HOST,
    port=PORT,
    reload=False,
)

server = uvicorn.Server(config)

if __name__ == "__main__":
    asyncio.run(server.serve())
