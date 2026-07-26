from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict] = field(default_factory=list)


class LLMBase(ABC):
    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        ...


class MockLLM(LLMBase):
    def __init__(
        self,
        fixed_response: str = "",
        fixed_tool_call: dict | None = None,
    ):
        self.fixed_response = fixed_response
        self.fixed_tool_call = fixed_tool_call
        self.conversation_history: list[tuple[str, str]] = []

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        self.conversation_history.append((system_prompt, user_message))
        tool_calls = []
        if self.fixed_tool_call:
            tool_calls = [self.fixed_tool_call]
        return LLMResponse(text=self.fixed_response, tool_calls=tool_calls)


class OpenAILLM(LLMBase):
    """OpenAI-compatible API integration (supports DeepSeek proxy via base_url).

    Reads environment variables:
      LLM_API_KEY    — API key / Bearer token (required)
      LLM_BASE_URL   — API base URL, default https://njusehub.info/v1
      LLM_MODEL      — Model name, default deepseek-v4-flash
    """

    # Approximate token budget per model (context window minus safety margin)
    _MODEL_MAX_TOKENS = {
        "gpt-4o": 128_000,
        "gpt-4o-mini": 128_000,
        "gpt-4-turbo": 128_000,
        "gpt-3.5-turbo": 16_000,
        "deepseek-v4-flash": 128_000,
        "deepseek-chat": 128_000,
        "deepseek-reasoner": 128_000,
    }
    _SAFETY_MARGIN = 4_000  # reserved for tool definitions and response

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        temperature: float = 0.7,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "API key is required. Set LLM_API_KEY in .env or pass api_key."
            )
        self.model = model or os.getenv("LLM_MODEL", "deepseek-v4-flash")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://njusehub.info/v1")
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout

        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=timeout,
            )
        except ImportError:
            raise ImportError("openai package is required. Run: pip install openai>=1.0.0")

    # ------------------------------------------------------------------
    # Public generate method
    # ------------------------------------------------------------------
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        messages = self._build_messages(system_prompt, user_message)

        # Token truncation: drop user_message if combined payload is too large
        messages = self._truncate_if_needed(messages)

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                text = choice.message.content or ""

                tool_calls = []
                if choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        tool_calls.append({
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        })

                return LLMResponse(text=text, tool_calls=tool_calls)

            except Exception as e:
                last_exception = e
                error_name = type(e).__name__
                logger.warning(
                    "OpenAI API call failed (attempt %d/%d): %s: %s",
                    attempt, self.max_retries, error_name, e,
                )

                # Retry only on transient errors
                if self._is_retryable(e):
                    if attempt < self.max_retries:
                        sleep_sec = 2 ** (attempt - 1)  # 1, 2, 4, …
                        logger.info("Retrying in %ds …", sleep_sec)
                        time.sleep(sleep_sec)
                        continue

                # Non-retryable or exhausted retries → raise immediately
                raise RuntimeError(
                    f"OpenAI API error after {attempt} attempt(s): {error_name}: {e}"
                ) from e

        # Should not reach here, but guard against it
        raise RuntimeError(
            f"OpenAI API failed after {self.max_retries} retries: {last_exception}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_messages(self, system_prompt: str, user_message: str) -> list[dict]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    def _truncate_if_needed(self, messages: list[dict]) -> list[dict]:
        """Rough token-count check; truncates user message if near limit."""
        budget = self._MODEL_MAX_TOKENS.get(self.model, 128_000) - self._SAFETY_MARGIN
        # Very rough estimate: ~4 chars per token for English + 1 token overhead per message
        estimated = sum(len(m.get("content", "")) // 4 + 10 for m in messages)
        if estimated <= budget:
            return messages

        # Truncate user message
        excess = estimated - budget
        user_msg = messages[-1]
        content = user_msg.get("content", "")
        # Remove roughly `excess * 4` characters from the middle
        if len(content) > excess * 4:
            keep = len(content) - excess * 4
            half = keep // 2
            truncated = content[:half] + "\n\n[... content truncated due to length ...]\n\n" + content[-half:]
            user_msg["content"] = truncated
            logger.warning("Truncated user message from %d to ~%d chars", len(content), len(truncated))
        return messages

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Check if the error is transient and worth retrying."""
        error_name = type(error).__name__
        # OpenAI SDK error hierarchy
        if error_name in ("RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError"):
            return True
        # HTTP status code heuristic for raw httpx errors
        if hasattr(error, "status_code"):
            return error.status_code in (429, 500, 502, 503, 504)
        return False