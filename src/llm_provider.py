# ============================================================================
# FILE: llm_provider.py
# LOCATION: src/
# PIPELINE POSITION: Foundation - called by router.py and action_generator.py
# PURPOSE: Provider-agnostic LLM interface (OpenRouter, Anthropic, Ollama)
# ============================================================================
"""
Single LLM client. Provider, model, auth, and request format all come from
config YAML files via Config. No hardcoded defaults.
"""

import httpx
import logging
from typing import Optional
from src.config_loader import Config

logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Provider-agnostic LLM client. Provider selected in tuning.yaml.

    Formats:
    - "openrouter" / "openai_compatible": POST /chat/completions
    - "anthropic": POST /v1/messages (different auth + response shape)
    - "ollama": POST /api/chat (no auth, different options format)
    """

    def __init__(self, config: Config):
        self.config = config
        self.provider = config.llm_provider
        self.base_url = config.llm_base_url.rstrip("/")
        self.api_key = config.llm_api_key
        self.timeout = config.llm_request_timeout
        self.max_retries = config.llm_max_retries
        self.extra_headers = config.llm_extra_headers
        self.anthropic_api_version = config.llm_anthropic_api_version
        self.response_preview_length = config.llm_response_preview_length
        self.error_preview_length = config.llm_error_preview_length

        self.headers = self._build_headers()
        self.client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)
        logger.info(f"LLM provider initialized: {self.provider} at {self.base_url}")

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.provider == "anthropic":
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = self.anthropic_api_version
        elif self.provider in ("openrouter", "openai_compatible"):
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.provider == "ollama":
            pass
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers

    async def complete(self, prompt: str, task: str) -> Optional[str]:
        """
        Send a prompt for a named task. Task must exist under llm.models in tuning.yaml.
        Returns model's text response or None on failure.
        """
        model_cfg = self.config.llm_model_config(task)
        body = self._build_body(prompt, model_cfg)
        endpoint = self._get_endpoint()

        for attempt in range(self.max_retries + 1):
            try:
                resp = await self.client.post(endpoint, json=body)
                resp.raise_for_status()
                text = self._parse_response(resp.json())
                if text:
                    logger.debug(
                        f"LLM ({task}, {model_cfg['id']}): "
                        f"{text[:self.response_preview_length]}..."
                    )
                    return text.strip()
                logger.warning(f"LLM returned empty response for task '{task}'")
                return None
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"LLM HTTP error (attempt {attempt + 1}/{self.max_retries + 1}): "
                    f"{e.response.status_code} - "
                    f"{e.response.text[:self.error_preview_length]}"
                )
                if attempt == self.max_retries:
                    return None
            except httpx.TimeoutException:
                logger.error(f"LLM timeout (attempt {attempt + 1}/{self.max_retries + 1})")
                if attempt == self.max_retries:
                    return None
            except Exception as e:
                logger.error(f"LLM unexpected error: {e}")
                return None
        return None

    def _build_body(self, prompt: str, model_cfg: dict) -> dict:
        if self.provider == "ollama":
            return {
                "model": model_cfg["id"],
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {
                    "temperature": model_cfg["temperature"],
                    "num_predict": model_cfg["max_tokens"],
                },
            }
        else:
            return {
                "model": model_cfg["id"],
                "max_tokens": model_cfg["max_tokens"],
                "temperature": model_cfg["temperature"],
                "messages": [{"role": "user", "content": prompt}],
            }

    def _get_endpoint(self) -> str:
        if self.provider == "anthropic":
            return f"{self.base_url}/v1/messages"
        elif self.provider == "ollama":
            return f"{self.base_url}/api/chat"
        else:
            return f"{self.base_url}/chat/completions"

    def _parse_response(self, data: dict) -> Optional[str]:
        if self.provider == "anthropic":
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block.get("text", "")
            return None
        elif self.provider == "ollama":
            return data.get("message", {}).get("content", "")
        else:
            choices = data.get("choices", [])
            return choices[0].get("message", {}).get("content", "") if choices else None

    async def close(self):
        await self.client.aclose()
