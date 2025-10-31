"""
Command Sender - утилита для отправки команд клиенту через SSE
Обертки над специализированными SSE функциями для обратной совместимости.
"""

from ..handlers.sse import sse_command, sse_message


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
    return await sse_command(app, method, params)


async def send_text_message(app, text: str):
    """
    Отправить текстовое сообщение клиенту.
    
    Args:
        app: aiohttp application
        text: текст сообщения
    
    Returns:
        str: uid сообщения
    """
    return await sse_message(app, text, descr="send")
