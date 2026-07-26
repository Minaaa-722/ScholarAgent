from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        # Real implementation calls OpenAI API
        # Stub for now — will be filled in during integration
        raise NotImplementedError("OpenAI integration requires API key setup")