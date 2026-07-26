import pytest
from agent.core.llm import LLMBase, MockLLM, LLMResponse


def test_mock_llm_returns_fixed_response():
    llm = MockLLM(fixed_response="Test output")
    response = llm.generate("system prompt", "user message")
    assert response.text == "Test output"
    assert response.tool_calls == []


def test_mock_llm_returns_tool_call():
    llm = MockLLM(fixed_tool_call={"name": "test_tool", "arguments": {"key": "value"}})
    response = llm.generate("system", "call tool")
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "test_tool"


def test_mock_llm_records_conversation():
    llm = MockLLM(fixed_response="ok")
    llm.generate("sys1", "msg1")
    llm.generate("sys2", "msg2")
    assert len(llm.conversation_history) == 2
    assert llm.conversation_history[0] == ("sys1", "msg1")


def test_llm_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        LLMBase()  # Abstract class