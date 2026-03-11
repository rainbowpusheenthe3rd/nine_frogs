"""LLM abstraction layer.

Supports:
  - Ollama  (provider="ollama")  — OpenAI-compatible local server
  - OpenAI  (provider="openai")  — cloud API
  - Anthropic (provider="anthropic") — via anthropic SDK adapter

Swap providers by changing LLM_PROVIDER in .env.  The rest of the codebase
only ever calls LLMClient.complete() / LLMClient.complete_json().
"""
from __future__ import annotations

import json
from loguru import logger
from typing import AsyncIterator

from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings



class LLMClient:
    def __init__(self) -> None:
        if settings.llm_provider in ("ollama", "openai"):
            from openai import AsyncOpenAI

            self._openai = AsyncOpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
            )
            self._backend = "openai"
        elif settings.llm_provider == "anthropic":
            from anthropic import AsyncAnthropic

            self._anthropic = AsyncAnthropic(api_key=settings.llm_api_key)
            self._backend = "anthropic"
        else:
            raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict],
        temperature: float | None = None,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        temp = temperature if temperature is not None else settings.llm_temperature
        if self._backend == "openai":
            if stream:
                return self._stream_openai(messages, temp)
            resp = await self._openai.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temp,
                max_tokens=settings.llm_max_tokens,
            )
            return resp.choices[0].message.content or ""
        else:
            return await self._complete_anthropic(messages, temp)

    async def _stream_openai(self, messages: list[dict], temperature: float) -> AsyncIterator[str]:
        stream = await self._openai.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def _complete_anthropic(self, messages: list[dict], temperature: float) -> str:
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_msgs = [m for m in messages if m["role"] != "system"]
        kwargs: dict = dict(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=temperature,
            messages=user_msgs,
        )
        if system:
            kwargs["system"] = system
        resp = await self._anthropic.messages.create(**kwargs)
        return resp.content[0].text

    async def complete_json(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        temperature: float = 0.1,
    ) -> BaseModel:
        """Complete with JSON mode and parse the response into a Pydantic model.

        Appends the schema to the conversation so the model knows the exact
        structure expected.  Retries up to 3 times on validation failure,
        feeding the error back to the model on each retry.
        """
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        augmented = list(messages) + [
            {
                "role": "user",
                "content": (
                    "Respond with ONLY a valid JSON object — no markdown fences, "
                    "no explanation, no text before or after.\n"
                    f"Schema:\n{schema_json}"
                ),
            }
        ]

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                if self._backend == "openai":
                    resp = await self._openai.chat.completions.create(
                        model=settings.llm_model,
                        messages=augmented,
                        temperature=temperature,
                        max_tokens=settings.llm_max_tokens,
                        response_format={"type": "json_object"},
                    )
                    content = resp.choices[0].message.content or ""
                else:
                    content = await self._complete_anthropic(augmented, temperature)

                # Strip accidental markdown fences
                content = content.strip()
                if content.startswith("```"):
                    parts = content.split("```")
                    content = parts[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                return schema.model_validate_json(content)

            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_err = exc
                logger.warning(
                    "JSON parse failed (attempt %d/3): %s — retrying with error feedback",
                    attempt + 1,
                    exc,
                )
                # Feed the error back so the model can self-correct
                augmented = augmented + [
                    {"role": "assistant", "content": content if "content" in dir() else ""},
                    {
                        "role": "user",
                        "content": (
                            f"That response was invalid. Error: {exc}\n"
                            "Please respond with ONLY valid JSON matching the schema."
                        ),
                    },
                ]

        raise RuntimeError(f"LLM failed to produce valid JSON after 3 attempts: {last_err}")


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
