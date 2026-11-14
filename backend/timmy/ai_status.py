from typing import Literal

import httpx
from pydantic import BaseModel

from .config import Settings


class OllamaStatus(BaseModel):
    model: str
    status: Literal["ready", "model_missing", "unreachable"]


async def probe_ollama(config: Settings) -> OllamaStatus:
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(f"{config.ollama_url}/api/tags")
            response.raise_for_status()
            models = response.json()["models"]
            if not isinstance(models, list):
                raise ValueError("Invalid tags response")
            installed = {item.get("name") for item in models if isinstance(item, dict)}
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return OllamaStatus(model=config.ollama_model, status="unreachable")
    model = config.ollama_model
    tag = model if ":" in model.rsplit("/", 1)[-1] else f"{model}:latest"
    return OllamaStatus(model=model, status="ready" if {model, tag} & installed else "model_missing")
