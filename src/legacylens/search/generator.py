"""LLM answer generation using OpenAI."""

import logging
from collections.abc import Generator

from openai import OpenAI

from legacylens.config import get_settings

logger = logging.getLogger(__name__)

_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def generate_answer(question: str, context: str) -> str:
    """Generate an answer using the LLM with retrieved context."""
    settings = get_settings()
    client = _get_openai_client()

    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": context},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=settings.llm_max_tokens,
    )

    answer = response.choices[0].message.content or ""
    logger.info(
        f"Generated answer: {response.usage.prompt_tokens} prompt tokens, "
        f"{response.usage.completion_tokens} completion tokens"
    )
    return answer


def generate_answer_stream(question: str, context: str) -> Generator[str, None, None]:
    """Generate an answer using the LLM with streaming."""
    settings = get_settings()
    client = _get_openai_client()

    stream = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": context},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=settings.llm_max_tokens,
        stream=True,
    )

    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
