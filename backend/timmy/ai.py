import json
from typing import Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings, settings
from .extraction_validation import review_issues
from .prompts import EXTRACTION_SYSTEM_PROMPT
from .schemas import Extraction, ExtractionResult

Model = TypeVar("Model", bound=BaseModel)

FailureCode = Literal[
    "timeout", "connection", "http_error", "malformed_json", "invalid_response",
    "truncated_output", "schema_validation",
]


class OllamaExtractionError(RuntimeError):
    def __init__(self, code: FailureCode):
        self.code = code
        super().__init__(f"Ollama extraction failed ({code})")


def _timeout(config: Settings) -> httpx.Timeout:
    return httpx.Timeout(config.ollama_timeout_seconds, connect=config.ollama_connect_timeout_seconds)


class OllamaAdapter:
    def __init__(self, config: Settings, client: httpx.AsyncClient):
        self.config = config
        self.client = client

    async def extract(self, source_row: dict[str, str]) -> ExtractionResult:
        row = dict(source_row)
        extracted = await self.structured([
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(row, ensure_ascii=False)},
        ], Extraction)
        issues = review_issues(extracted, row)
        return ExtractionResult(
            source_row=row, extracted=extracted, requires_review=bool(issues), review_issues=issues,
        )


    async def structured(self, messages: list[dict[str, str]], schema: type[Model]) -> Model:
        try:
            response = await self.client.post(
                f"{self.config.ollama_url}/api/chat",
                timeout=_timeout(self.config),
                follow_redirects=False,
                json={
                    "model": self.config.ollama_model,
                    "stream": False,
                    "think": False,
                    "format": schema.model_json_schema(),
                    "options": {
                        "temperature": 0,
                        "seed": self.config.ollama_seed,
                        "num_predict": self.config.ollama_max_tokens,
                    },
                    "messages": messages,
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise OllamaExtractionError("timeout") from None
        except httpx.RequestError:
            raise OllamaExtractionError("connection") from None
        except httpx.HTTPStatusError:
            raise OllamaExtractionError("http_error") from None

        try:
            body = response.json()
        except (ValueError, UnicodeError):
            raise OllamaExtractionError("malformed_json") from None
        if not isinstance(body, dict):
            raise OllamaExtractionError("invalid_response")
        if body.get("done_reason") == "length" or body.get("done") is False:
            raise OllamaExtractionError("truncated_output")
        message = body.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise OllamaExtractionError("invalid_response")

        try:
            candidate = json.loads(message["content"], object_pairs_hook=_unique_keys)
        except ValueError:
            raise OllamaExtractionError("malformed_json") from None
        try:
            return schema.model_validate(candidate)
        except ValidationError:
            raise OllamaExtractionError("schema_validation") from None

def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON key")
        obj[key] = value
    return obj


def build_ollama_client(config: Settings | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_timeout(config or settings()), trust_env=False, follow_redirects=False)
