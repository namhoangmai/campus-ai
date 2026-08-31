"""Build the RAG prompt and call the LLM for a chat answer"""

import logging
import os
import textwrap
import time
from dataclasses import dataclass
from typing import Dict, List

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Config:
    base_url: str
    model: str
    api_key_env: str

LLM_CONFIG = Config(
    base_url="https://integrate.api.nvidia.com/v1",
    model="deepseek-ai/deepseek-v4-flash-0731",
    api_key_env="DEEPSEEK_API_KEY",
)
# max_tokens=16384

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are the TU/e (Eindhoven University of Technology) admission and
    enrollment assistant. Answer the student's question using ONLY the
    context provided below (the selected program's roadmap page, and/or
    excerpts from TU/e's admission pages). If the context does not contain
    the answer, say so clearly instead of guessing, and suggest the
    student check the official TU/e website or contact admissions.
    Do not include a "Sources" section or any citation links yourself --
    the app displays the source links separately below your answer. Be concise.
    """
).strip()

def call_model_with_retry(
    client: OpenAI,
    model: str,
    messages: List[Dict[str, str]],
    max_retries: int,
    initial_backoff: float,
    timeout_seconds: float,
) -> str:
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
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
            logger.warning(
                "Rate limit (%d/%d). Sleeping %.1fs...",
                attempt,
                max_retries,
                wait_time,
            )
            time.sleep(wait_time)

        except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
            if attempt == max_retries:
                raise RuntimeError(f"API failure after {max_retries} attempts.") from exc

            wait_time = initial_backoff * (2 ** (attempt - 1))
            print(
                f"[retry] {type(exc).__name__} on attempt {attempt}/{max_retries}. Sleeping {wait_time:.1f}s...",
                flush=True,
            )
            time.sleep(wait_time)

        except BadRequestError as exc:
            raise RuntimeError(f"Bad request sent to API: {exc}") from exc

    raise RuntimeError("Unexpected retry loop exit.")

def build_context(retrieved_chunks: list[dict], live_page: dict | None) -> str:
    parts = []
    
    if live_page:
        parts.append(
            f"### Selected program page: {live_page['title']} \n"
            f"Source: {live_page['url']} \n\n"
            f"{live_page['body']}"
        )
        
    for chunk in retrieved_chunks:
        source_url = chunk.get("source_url") or "(no URL available)"
        parts.append(f"### {chunk['title']} (source URL: {source_url})\n\n{chunk['content']}")
        
    if not parts:
        return "(no context available)"
    return "\n\n---\n\n".join(parts)

def build_messages(question: str, chat_history: list[dict], retrieved_chunks: list[dict], live_page: dict | None):
    context = build_context(retrieved_chunks, live_page)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(chat_history)
    messages.append(
        {
            "role": "user",
            "content": f"Context: \n\n{context}\n\n---\n\nQuestion: {question}"
        }
    )
    return messages

def generate_answer(
    question: str,
    chat_history: list[dict],
    retrieved_chunks: list[dict],
    live_page: dict | None,
    config: Config = LLM_CONFIG,
) -> str:
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise EnvironmentError(f"{config.api_key_env} is not set in the environment.")
    
    client = OpenAI(api_key=api_key, base_url=config.base_url)
    messages = build_messages(question, chat_history, retrieved_chunks, live_page)
    
    return call_model_with_retry(
        client=client,
        model=config.model,
        messages=messages,
        max_retries=3,
        initial_backoff=2.0,
        timeout_seconds=60.0,
    )
