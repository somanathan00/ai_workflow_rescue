import logging
import time
from dataclasses import dataclass

from google import genai
from google.genai import errors, types

from app.agents.schemas import InvestigationResult
from app.core.config import settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_API_ATTEMPTS = 3


class LLMUnavailable(Exception):
    """Gemini could not be reached or is not configured."""


@dataclass(frozen=True)
class LLMUsage:
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


class GeminiInvestigationClient:

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise LLMUnavailable("GEMINI_API_KEY is not configured")

        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=settings.GEMINI_TIMEOUT_SECONDS * 1000,
            ),
        )

    def investigate(
        self,
        prompt: str,
        system_instruction: str,
    ) -> tuple[InvestigationResult, LLMUsage]:
        started = time.monotonic()
        response = None

        for attempt in range(1, MAX_API_ATTEMPTS + 1):
            try:
                response = self.client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=InvestigationResult,
                        temperature=0,
                    ),
                )
                break
            except errors.APIError as exc:
                retryable = exc.code in RETRYABLE_STATUS

                if not retryable or attempt == MAX_API_ATTEMPTS:
                    raise LLMUnavailable(
                        f"Gemini API error {exc.code}"
                    ) from exc

                logger.warning(
                    "gemini_retry",
                    extra={"attempt": attempt, "status": exc.code},
                )
                time.sleep(2 ** (attempt - 1))
            except Exception as exc:  # network / timeout
                if attempt == MAX_API_ATTEMPTS:
                    raise LLMUnavailable(
                        f"Gemini request failed: {type(exc).__name__}"
                    ) from exc
                time.sleep(2 ** (attempt - 1))

        if response is None or response.text is None:
            raise ValueError("Gemini returned no investigation result")

        result = InvestigationResult.model_validate_json(response.text)
        usage = response.usage_metadata

        return result, LLMUsage(
            model=settings.GEMINI_MODEL,
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            completion_tokens=getattr(usage, "candidates_token_count", None),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
