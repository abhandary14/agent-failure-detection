"""
Retry wrapper for calls to the local Ollama server. There's no external
rate limit to respect here (unlike a paid cloud API), but a local server
can still fail transiently -- not yet warmed up, model still loading into
memory, or a dropped local connection -- so the same retry shape is kept
for robustness.
"""

import time
from typing import Callable, TypeVar

import requests

import config

T = TypeVar("T")


class RetryExhausted(Exception):
    """Raised when all retry attempts against the local LLM server failed."""


def call_with_retry(fn: Callable[[], T]) -> T:
    """
    Call fn() with exponential backoff on connection errors or 5xx
    responses from the local Ollama server. Logs each retry attempt.
    Raises RetryExhausted if MAX_RETRIES is exceeded.
    """
    last_error: Exception | None = None

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_error = exc
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code < 500:
                raise  # client errors (4xx) are not retryable
            last_error = exc

        if attempt < config.MAX_RETRIES:
            backoff = config.RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            print(f"[retry] Ollama call failed (attempt {attempt}/{config.MAX_RETRIES}): "
                  f"{last_error}. Retrying in {backoff:.1f}s...")
            time.sleep(backoff)

    raise RetryExhausted(
        f"Ollama call failed after {config.MAX_RETRIES} attempts: {last_error}"
    )