"""
Processing Nodes - модульная архитектура обработки аудио
"""

from .base_node import BaseNode
from .nats_receiver_node import NatsReceiverNode
from .phrase_segmenter_node import PhraseSegmenterNode
from .file_saver_node import FileSaverNode
from .whisper_transcriber_node import WhisperTranscriberNode

__all__ = [
    'BaseNode',
    'NatsReceiverNode',
    'PhraseSegmenterNode',
    'FileSaverNode',
    'WhisperTranscriberNode'
]
