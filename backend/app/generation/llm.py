"""LLM calling with retry/backoff. Ported from v1's answer.py, which was already correct here —
only the prompt construction moved out (see prompts.py) so this file is purely "call the model
reliably," not also "know what a tenant is."
"""

import logging
import time
from typing import Dict, List

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


def call_model_with_retry(
    client: OpenAI,
    model: str,
    messages: List[Dict[str, str]],
    max_retries: int = 3,
    initial_backoff: float = 2.0,
    timeout_seconds: float = 60.0,
) -> str:
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=16384,
                seed=0,
                extra_body={"reasoning": {"enabled": True}},
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Model returned empty content")
            return content

        except RateLimitError as exc:
            if attempt == max_retries:
                raise RuntimeError(f"Rate limit: failed after {max_retries} attempts.") from exc
            wait_time = initial_backoff * (2 ** (attempt - 1))
            logger.warning("Rate limit (%d/%d). Sleeping %.1fs...", attempt, max_retries, wait_time)
            time.sleep(wait_time)

        except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
            if attempt == max_retries:
                raise RuntimeError(f"API failure after {max_retries} attempts.") from exc
            wait_time = initial_backoff * (2 ** (attempt - 1))
            logger.warning("%s on attempt %d/%d. Sleeping %.1fs...", type(exc).__name__, attempt, max_retries, wait_time)
            time.sleep(wait_time)

        except BadRequestError as exc:
            raise RuntimeError(f"Bad request sent to API: {exc}") from exc

    raise RuntimeError("Unexpected retry loop exit.")


def generate_answer(messages: List[Dict[str, str]]) -> str:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set in the environment.")

    client = OpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
    return call_model_with_retry(client=client, model=settings.generation_model, messages=messages)
