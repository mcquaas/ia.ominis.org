"""Vast.ai Serverless integration (route + worker via vastai SDK)."""

from app.vast_serverless.generators import (
    ServerlessOllamaChatGenerator,
    ServerlessOpenAIChatGenerator,
    openai_chat_completion_sync,
)

__all__ = [
    "ServerlessOpenAIChatGenerator",
    "ServerlessOllamaChatGenerator",
    "openai_chat_completion_sync",
]
