"""
Nodes - узлы обработки аудио в конвейере транскрипции

Архитектура:
    Каждая нода выполняет одну задачу и передает результат через callback.
    Ноды соединяются в граф обработки данных.
    
Компоненты:
    - BaseNode: базовый класс для всех нод
    - NatsReceiverNode: получение аудио из NATS
    - PhraseSegmenterNode: сегментация аудио на фразы (Silero VAD)
    - FileSaverNode: сохранение фраз в файлы
    - WhisperTranscriberNode: распознавание речи
    - RawRecorderNode: запись сырого аудио для диагностики
"""

from .base_node import BaseNode
from .nats_receiver_node import NatsReceiverNode
from .phrase_segmenter_node import PhraseSegmenterNode, PhraseSegment
from .file_saver_node import FileSaverNode
from .whisper_transcriber_node import WhisperTranscriberNode
from .raw_recorder_node import RawRecorderNode

__all__ = [
    'BaseNode',
    'NatsReceiverNode',
    'PhraseSegmenterNode',
    'PhraseSegment',
    'FileSaverNode',
    'WhisperTranscriberNode',
    'RawRecorderNode'
]
