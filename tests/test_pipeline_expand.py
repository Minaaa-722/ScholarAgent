"""Tests for _expand_and_dedup_queries."""
from agent.core.pipeline import PipelineOrchestrator
from agent.tools.registry import ToolRegistry
from agent.core.llm import MockLLM
from agent.guardrails.manager import GuardrailManager
from agent.core.pipeline import HarnessConfig


def _make_orch():
    llm = MockLLM(fixed_response="Test response")
    tools = ToolRegistry()
    guardrails = GuardrailManager(guardrails=[])
    config = HarnessConfig()
    return PipelineOrchestrator(
        llm=llm, tools=tools, validators=[], guardrails=guardrails,
        config=config, latex_repair=None,
    )


def test_expand_full_to_abbrev():
    """"Vision Transformer -> ViT" → 2 条 + 扩展至 3 条."""
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["Vision Transformer -> ViT"], "topic", ["kw"])
    assert len(result) >= 2
    assert "Vision Transformer" in result
    assert "ViT" in result


def test_expand_dedup_identical():
    """Fix 5: "attention -> attention" → 1 条（去重后扩展至 3 条）."""
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["attention -> attention"], "topic", ["kw"])
    assert len(result) >= 1
    assert result[0] == "attention"


def test_expand_dedup_case_insensitive():
    """Fix 5: "ViT -> vit" → 1 条（大小写不敏感，去重后扩展至 3 条）."""
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["ViT -> vit"], "topic", ["kw"])
    assert len(result) >= 1
    assert result[0] == "ViT"


def test_expand_fallback_empty():
    orch = _make_orch()
    result = orch._expand_and_dedup_queries([], "topic", ["kw1", "kw2", "kw3"])
    assert len(result) >= 1
    assert "topic" in result


def test_expand_fill_shortfall():
    orch = _make_orch()
    result = orch._expand_and_dedup_queries(["only one -> one"], "topic", ["kw1", "kw2"])
    assert len(result) >= 2


def test_expand_mixed_formats():
    orch = _make_orch()
    raw = ["ViT -> ViT", "plain query", "CNN -> Convolutional Neural Network"]
    result = orch._expand_and_dedup_queries(raw, "topic", ["kw"])
    assert "ViT" in result
    assert "plain query" in result
    assert "CNN" in result
    assert "Convolutional Neural Network" in result