"""LLM answer generation using OpenAI."""

import logging

from openai import OpenAI

from legacylens.config import get_settings

logger = logging.getLogger(__name__)


def generate_answer(question: str, context: str) -> str:
    """Generate an answer using the LLM with retrieved context.

    Args:
        question: The user's natural language question
        context: Assembled context from retriever + context assembler

    Returns:
        The LLM's answer string
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": context},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=2000,
    )

    answer = response.choices[0].message.content or ""
    logger.info(
        f"Generated answer: {response.usage.prompt_tokens} prompt tokens, "
        f"{response.usage.completion_tokens} completion tokens"
    )
    return answer
