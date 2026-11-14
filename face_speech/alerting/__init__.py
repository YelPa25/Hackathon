"""Alerting module initialization."""

from alerting.adapters.facial import get_facial_config
from alerting.adapters.speech import get_speech_config
from alerting.core.config import AlertConfig
from alerting.core.node import AlertNode

__all__ = [
    "AlertConfig",
    "AlertNode",
    "get_facial_config",
    "get_speech_config",
]
