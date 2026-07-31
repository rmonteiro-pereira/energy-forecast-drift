"""A small, polite HTTP helper shared by every API client.

Rules enforced here (so no client can break them):
  * at most `MAX_RETRIES` attempts, exponential backoff (2s, 4s, 8s);
  * only transient failures are retried (timeouts, connection errors, 429, 5xx);
  * `Retry-After` is honoured when the server sends it;
  * query strings are redacted before anything is logged, so an API key can
    never reach stdout or a log file.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from ingest.config import BACKOFF_BASE_SECONDS, MAX_RETRIES, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

SECRET_PARAMS = {"api_key", "apikey", "token", "key"}


def redact(url: str) -> str:
    """Strip the query string from a URL so secrets never get logged."""
    parts = urlsplit(str(url))
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def redact_params(params: dict[str, Any]) -> dict[str, Any]:
    """Copy of `params` with any secret-looking value masked."""
    return {k: ("***" if k.lower() in SECRET_PARAMS else v) for k, v in params.items()}


class ApiError(RuntimeError):
    """Raised when a request could not be completed within the retry budget."""


def get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, Any],
    *,
    context: str = "",
) -> dict[str, Any]:
    """GET `url` and return the decoded JSON body, retrying transient errors."""
    last_error: str = "unknown error"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code == 200:
                # A 200 does not guarantee a JSON *object*. Both upstreams can
                # return an HTML error page through a proxy, and a JSON array or
                # bare scalar would satisfy `.json()` while breaking every
                # caller's `body["response"]` with a TypeError far from here.
                # Validate once, at the boundary, and fail as `ApiError` like
                # every other failure mode -- so the per-source handlers keep
                # working instead of an unhandled ValueError escaping the loop.
                try:
                    body = response.json()
                except ValueError as exc:
                    raise ApiError(
                        f"{redact(url)} returned HTTP 200 with a body that is not "
                        f"JSON ({exc}). First 300 chars: {response.text[:300]!r}"
                    ) from exc

                if not isinstance(body, dict):
                    raise ApiError(
                        f"{redact(url)} returned JSON that is not an object but a "
                        f"{type(body).__name__}. Callers index into the response, "
                        "so a non-object body cannot be handled here."
                    )

                validated: dict[str, Any] = body
                return validated

            if response.status_code in (401, 403):
                # A bad key is not transient; retrying just burns quota.
                raise ApiError(
                    f"{redact(url)} rejected the credentials "
                    f"(HTTP {response.status_code}). Check EIA_API_KEY in .env."
                )

            if response.status_code not in RETRYABLE_STATUS:
                raise ApiError(
                    f"{redact(url)} returned HTTP {response.status_code}: {response.text[:300]}"
                )

            last_error = f"HTTP {response.status_code}"
            retry_after = _retry_after_seconds(response)
            if retry_after is not None and attempt < MAX_RETRIES:
                log.warning(
                    "%s rate-limited%s; honouring Retry-After=%.1fs",
                    redact(url),
                    f" ({context})" if context else "",
                    retry_after,
                )
                time.sleep(retry_after)
                continue

        if attempt < MAX_RETRIES:
            delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            log.warning(
                "%s failed (%s)%s; retry %d/%d in %.1fs",
                redact(url),
                last_error,
                f" [{context}]" if context else "",
                attempt,
                MAX_RETRIES - 1,
                delay,
            )
            time.sleep(delay)

    raise ApiError(
        f"{redact(url)} failed after {MAX_RETRIES} attempts "
        f"({last_error}){f' [{context}]' if context else ''}"
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        # Cap it so a hostile header cannot stall the pipeline for hours.
        return min(float(raw), 60.0)
    except ValueError:
        return None
