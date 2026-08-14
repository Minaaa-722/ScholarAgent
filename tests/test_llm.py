import pytest
from agent.core.llm import LLMBase, MockLLM


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


def test_openai_llm_set_api_key_updates_client():
    """OpenAILLM.set_api_key() updates api_key and recreates the client."""
    from unittest.mock import MagicMock, patch
    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        from agent.core.llm import OpenAILLM
        llm = OpenAILLM(api_key="sk-old-key")
        assert llm.api_key == "sk-old-key"

        # set_api_key should update the key and recreate the client
        llm.set_api_key("sk-new-key")
        assert llm.api_key == "sk-new-key"
        mock_openai.assert_called_with(
            api_key="sk-new-key",
            base_url=llm.base_url,
            timeout=llm.timeout,
        )
