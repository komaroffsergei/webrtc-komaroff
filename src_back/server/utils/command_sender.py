"""
Command Sender - утилита для отправки команд клиенту через SSE
"""

import uuid
from ..handlers.sse import sse_broadcast


async def send_command(app, method: str, params=None):
    """
    Отправить команду клиенту через SSE.
    
    Args:
        app: aiohttp application
        method: имя метода команды (например 'alert', 'reload')
        params: параметры команды (dict, str, или любой JSON-сериализуемый тип)
    
    Returns:
        str: uid команды
    """
    command_uid = str(uuid.uuid4())
    
    await sse_broadcast(app, {
        "type": "command",
        "method": method,
        "params": params,
        "uid": command_uid
    })
    
    return command_uid


async def send_text_message(app, text: str):
    """
    Отправить текстовое сообщение клиенту.
    
    Args:
        app: aiohttp application
        text: текст сообщения
    
    Returns:
        str: uid сообщения
    """
    message_uid = str(uuid.uuid4())
    
    await sse_broadcast(app, {
        "type": "message",
        "descr": "send",
        "uid": message_uid,
        "text": text
    })
    
    return message_uid
