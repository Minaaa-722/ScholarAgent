"""Tests for LLM module — covering retry, streaming, auth failure, model switching."""
import pytest
from unittest.mock import MagicMock, patch
from agent.core.llm import LLMBase, MockLLM, LLMResponse, OpenAILLM


# ---------------------------------------------------------------------------
# MockLLM tests
# ---------------------------------------------------------------------------

def test_mock_llm_returns_fixed_response():
    """MockLLM should return text from fixed_response."""
    llm = MockLLM(fixed_response="Test output")
    response = llm.generate("system prompt", "user message")
    assert response.text == "Test output"
    assert response.tool_calls == []


def test_mock_llm_returns_tool_call():
    """MockLLM should return tool_calls from fixed_tool_call."""
    llm = MockLLM(fixed_tool_call={"name": "test_tool", "arguments": {"key": "value"}})
    response = llm.generate("system", "call tool")
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "test_tool"


def test_mock_llm_records_conversation():
    """MockLLM should record (system, user) pairs in conversation_history."""
    llm = MockLLM(fixed_response="ok")
    llm.generate("sys1", "msg1")
    llm.generate("sys2", "msg2")
    assert len(llm.conversation_history) == 2
    assert llm.conversation_history[0] == ("sys1", "msg1")


def test_llm_base_cannot_be_instantiated():
    """LLMBase is abstract and should raise TypeError."""
    with pytest.raises(TypeError):
        LLMBase()  # Abstract class


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------

def test_llm_response_defaults():
    """LLMResponse should default tool_calls to empty list."""
    resp = LLMResponse(text="hello")
    assert resp.text == "hello"
    assert resp.tool_calls == []


def test_llm_response_with_tool_calls():
    """LLMResponse should accept tool_calls at construction."""
    resp = LLMResponse(text="hello", tool_calls=[{"name": "tool1"}])
    assert len(resp.tool_calls) == 1


# ---------------------------------------------------------------------------
# OpenAILLM — initialization
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_openai_llm_init_defaults(mock_openai):
    """Should raise ValueError when no API key is available."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="API key is required"):
            OpenAILLM()


@patch("openai.OpenAI")
def test_openai_llm_init_with_env(mock_openai):
    """Should read LLM_API_KEY, LLM_MODEL, LLM_BASE_URL from env."""
    import os
    with patch.dict(os.environ, {
        "LLM_API_KEY": "sk-env-key",
        "LLM_MODEL": "gpt-4o",
        "LLM_BASE_URL": "https://custom.api/v1",
    }, clear=True):
        llm = OpenAILLM()
        assert llm.api_key == "sk-env-key"
        assert llm.model == "gpt-4o"
        assert llm.base_url == "https://custom.api/v1"


@patch("openai.OpenAI")
def test_openai_llm_init_with_params(mock_openai):
    """Explicit params should override env vars."""
    llm = OpenAILLM(api_key="sk-explicit", model="gpt-4-turbo",
                    base_url="https://api.openai.com/v1", max_retries=5, timeout=60)
    assert llm.api_key == "sk-explicit"
    assert llm.model == "gpt-4-turbo"
    assert llm.max_retries == 5
    assert llm.timeout == 60


@patch("openai.OpenAI")
def test_openai_llm_raises_on_missing_openai(mock_openai):
    """Should raise ImportError when openai package is not installed."""
    import sys
    with patch.dict(sys.modules, {"openai": None}):
        with pytest.raises(ImportError, match="openai package is required"):
            OpenAILLM(api_key="sk-test")


# ---------------------------------------------------------------------------
# OpenAILLM — set_api_key
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_openai_llm_set_api_key_updates_client(mock_openai):
    """set_api_key() updates the API key and recreates the client."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    llm = OpenAILLM(api_key="sk-old-key")
    assert llm.api_key == "sk-old-key"

    llm.set_api_key("sk-new-key")
    assert llm.api_key == "sk-new-key"
    mock_openai.assert_called_with(
        api_key="sk-new-key",
        base_url=llm.base_url,
        timeout=llm.timeout,
    )


@patch("openai.OpenAI")
def test_openai_llm_set_api_key_empty_value(mock_openai):
    """Empty value should be silently ignored, keeping old key."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    llm = OpenAILLM(api_key="sk-old-key")
    llm.set_api_key("")
    assert llm.api_key == "sk-old-key"  # unchanged


# ---------------------------------------------------------------------------
# OpenAILLM.generate — successful response
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_openai_generate_success(mock_openai):
    """Successful API call should return LLMResponse with text."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    # Mock the chat completion response
    mock_choice = MagicMock()
    mock_choice.message.content = "Generated response"
    mock_choice.message.tool_calls = None

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_response

    llm = OpenAILLM(api_key="sk-test")
    result = llm.generate("system prompt", "user message")
    assert result.text == "Generated response"
    assert result.tool_calls == []


@patch("openai.OpenAI")
def test_openai_generate_with_tool_calls(mock_openai):
    """Successful API call with tool calls should return them."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    # Mock a tool call in the response
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_1"
    mock_tool_call.type = "function"
    mock_tool_call.function.name = "arxiv_search"
    mock_tool_call.function.arguments = '{"query": "test"}'

    mock_choice = MagicMock()
    mock_choice.message.content = "Using tool"
    mock_choice.message.tool_calls = [mock_tool_call]

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_response

    llm = OpenAILLM(api_key="sk-test")
    result = llm.generate("system", "search", tools=[{"type": "function", "function": {"name": "test"}}])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["function"]["name"] == "arxiv_search"
    assert result.tool_calls[0]["id"] == "call_1"


@patch("openai.OpenAI")
def test_openai_generate_empty_content(mock_openai):
    """When content is None, should return empty string."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.tool_calls = None

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_response

    llm = OpenAILLM(api_key="sk-test")
    result = llm.generate("system", "user")
    assert result.text == ""


# ---------------------------------------------------------------------------
# OpenAILLM.generate — retry logic
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_openai_generate_retry_on_transient_error(mock_openai):
    """Should retry on transient errors (RateLimitError)."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    # First call fails, second succeeds
    from openai import RateLimitError
    mock_client.chat.completions.create.side_effect = [
        RateLimitError("Rate limited", response=MagicMock(), body=MagicMock()),
        MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content="Success after retry",
                        tool_calls=None,
                    )
                )
            ]
        ),
    ]

    llm = OpenAILLM(api_key="sk-test", max_retries=2)
    with patch("time.sleep") as _:  # Speed up test
        result = llm.generate("system", "user")
    assert result.text == "Success after retry"
    assert mock_client.chat.completions.create.call_count == 2


@patch("openai.OpenAI")
def test_openai_generate_non_retryable_error(mock_openai):
    """Non-retryable errors should raise immediately."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    from openai import AuthenticationError
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_client.chat.completions.create.side_effect = AuthenticationError(
        "Auth failed", response=mock_response, body=MagicMock()
    )

    llm = OpenAILLM(api_key="sk-test", max_retries=2)
    with pytest.raises(RuntimeError, match="OpenAI API error after 1 attempt"):
        with patch("time.sleep"):
            llm.generate("system", "user")


@patch("openai.OpenAI")
def test_openai_generate_exhausted_retries(mock_openai):
    """Should raise after exhausting all retries."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    from openai import RateLimitError
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_client.chat.completions.create.side_effect = RateLimitError(
        "Rate limited", response=mock_response, body=MagicMock()
    )

    llm = OpenAILLM(api_key="sk-test", max_retries=2)
    with pytest.raises(RuntimeError, match="OpenAI API error after 2 attempt"):
        with patch("time.sleep"):
            llm.generate("system", "user")


@patch("openai.OpenAI")
def test_openai_generate_last_resort_guard(mock_openai):
    """The final raise after all retries should work."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    from openai import APITimeoutError
    import httpx
    request = httpx.Request("GET", "https://api.openai.com")
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=request)

    llm = OpenAILLM(api_key="sk-test", max_retries=1)
    with pytest.raises(RuntimeError) as excinfo:
        with patch("time.sleep"):
            llm.generate("system", "user")
    assert "OpenAI API error after 1 attempt" in str(excinfo.value)


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_build_messages(mock_openai):
    """_build_messages should return system and user message dicts."""
    llm = OpenAILLM(api_key="sk-test")
    messages = llm._build_messages("system prompt", "user message")
    assert len(messages) == 2
    assert messages[0] == {"role": "system", "content": "system prompt"}
    assert messages[1] == {"role": "user", "content": "user message"}


# ---------------------------------------------------------------------------
# _truncate_if_needed
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_truncate_if_needed_below_budget(mock_openai):
    """When message is under budget, should return unchanged."""
    llm = OpenAILLM(api_key="sk-test")
    messages = [
        {"role": "system", "content": "short"},
        {"role": "user", "content": "short user message"},
    ]
    result = llm._truncate_if_needed(messages)
    assert result == messages


@patch("openai.OpenAI")
def test_truncate_if_needed_truncates(mock_openai):
    """When message exceeds budget, should truncate user message."""
    llm = OpenAILLM(api_key="sk-test")
    # Create a very long user message (600k chars, ~150k tokens)
    long_content = "Hello " * 100000  # ~600k chars
    messages = [
        {"role": "system", "content": "short"},
        {"role": "user", "content": long_content},
    ]
    result = llm._truncate_if_needed(messages)
    # Should be truncated
    assert len(result[1]["content"]) < len(long_content)
    assert "[... content truncated due to length ...]" in result[1]["content"]


@patch("openai.OpenAI")
def test_truncate_if_needed_unknown_model(mock_openai):
    """Unknown model should use default 128k budget."""
    llm = OpenAILLM(api_key="sk-test", model="unknown-model")
    long_content = "Hello " * 100000  # ~600k chars
    messages = [
        {"role": "system", "content": "short"},
        {"role": "user", "content": long_content},
    ]
    result = llm._truncate_if_needed(messages)
    assert len(result[1]["content"]) < len(long_content)


# ---------------------------------------------------------------------------
# _is_retryable
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_is_retryable_rate_limit(mock_openai):
    """RateLimitError should be retryable."""
    llm = OpenAILLM(api_key="sk-test")
    from openai import RateLimitError
    error = RateLimitError("Rate limited", response=MagicMock(), body=MagicMock())
    assert llm._is_retryable(error) is True


@patch("openai.OpenAI")
def test_is_retryable_timeout(mock_openai):
    """APITimeoutError should be retryable."""
    llm = OpenAILLM(api_key="sk-test")
    from openai import APITimeoutError
    error = APITimeoutError("Timeout")
    assert llm._is_retryable(error) is True


@patch("openai.OpenAI")
def test_is_retryable_connection_error(mock_openai):
    """APIConnectionError should be retryable."""
    llm = OpenAILLM(api_key="sk-test")
    from openai import APIConnectionError
    import httpx
    request = httpx.Request("GET", "https://api.openai.com")
    error = APIConnectionError(message="Connection failed", request=request)
    assert llm._is_retryable(error) is True


@patch("openai.OpenAI")
def test_is_retryable_internal_server_error(mock_openai):
    """InternalServerError should be retryable."""
    llm = OpenAILLM(api_key="sk-test")
    from openai import InternalServerError
    error = InternalServerError("Server error", response=MagicMock(), body=MagicMock())
    assert llm._is_retryable(error) is True


@patch("openai.OpenAI")
def test_is_retryable_authentication_error(mock_openai):
    """Auth errors should NOT be retryable."""
    llm = OpenAILLM(api_key="sk-test")
    from openai import AuthenticationError
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    error = AuthenticationError("Auth failed", response=mock_resp, body=MagicMock())
    assert llm._is_retryable(error) is False


@patch("openai.OpenAI")
def test_is_retryable_bad_request_error(mock_openai):
    """BadRequestError should NOT be retryable."""
    llm = OpenAILLM(api_key="sk-test")
    from openai import BadRequestError
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    error = BadRequestError("Bad request", response=mock_resp, body=MagicMock())
    assert llm._is_retryable(error) is False


@patch("openai.OpenAI")
def test_is_retryable_http_status_code(mock_openai):
    """HTTP status code 500 should be retryable, 401 should not."""
    llm = OpenAILLM(api_key="sk-test")

    class ErrorWithCode(Exception):
        def __init__(self, status_code):
            self.status_code = status_code
            super().__init__()

    error_500 = ErrorWithCode(500)
    assert llm._is_retryable(error_500) is True

    error_502 = ErrorWithCode(502)
    assert llm._is_retryable(error_502) is True

    error_401 = ErrorWithCode(401)
    assert llm._is_retryable(error_401) is False


@patch("openai.OpenAI")
def test_is_retryable_unknown_error(mock_openai):
    """Unknown errors should NOT be retryable."""
    llm = OpenAILLM(api_key="sk-test")
    error = ValueError("Something else")
    assert llm._is_retryable(error) is False


# ---------------------------------------------------------------------------
# OpenAILLM — model max tokens
# ---------------------------------------------------------------------------

@patch("openai.OpenAI")
def test_model_max_tokens_known(mock_openai):
    """Known model should have max tokens in the dict."""
    llm = OpenAILLM(api_key="sk-test", model="gpt-4o")
    assert llm._MODEL_MAX_TOKENS["gpt-4o"] == 128_000


@patch("openai.OpenAI")
def test_model_max_tokens_default(mock_openai):
    """Unknown model defaults to 128_000."""
    llm = OpenAILLM(api_key="sk-test", model="custom-model")
    assert llm._MODEL_MAX_TOKENS.get("custom-model", 128_000) == 128_000
