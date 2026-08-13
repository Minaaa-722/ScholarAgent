import pytest
from agent.core.llm import MockLLM


@pytest.fixture
def mock_llm():
    return MockLLM(fixed_response="Mock response")


@pytest.fixture
def mock_llm_with_tool():
    return MockLLM(fixed_tool_call={
        "name": "arxiv_search",
        "arguments": {"query": "transformer"}
    })
