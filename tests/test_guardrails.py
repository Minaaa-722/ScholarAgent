import pytest
from agent.guardrails.base import Guardrail, GuardrailVerdict
from agent.guardrails.source_filter import SourceFilter
from agent.guardrails.fact_binding import FactBinding
from agent.guardrails.op_safety import OpSafety
from agent.guardrails.rate_limit import RateLimit
from agent.guardrails.output_std import OutputStandard


def test_guardrail_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Guardrail()


def test_source_filter_blocks_blacklisted_journal():
    guard = SourceFilter(blacklist=["predatory-journal"])
    ctx = {"paper": {"journal": "predatory-journal"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.BLOCK


def test_source_filter_allows_valid_source():
    guard = SourceFilter(blacklist=["predatory"])
    ctx = {"paper": {"journal": "ieeetran"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS


def test_op_safety_blocks_rm_rf():
    guard = OpSafety()
    ctx = {"action": "shell_exec", "params": {"command": "rm -rf /"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.REQUIRE_APPROVAL


def test_op_safety_allows_safe_command():
    guard = OpSafety()
    ctx = {"action": "shell_exec", "params": {"command": "ls -la"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS


def test_rate_limit_blocks_excessive_calls():
    guard = RateLimit(max_calls=2, window_seconds=60)
    ctx = {"action": "arxiv_search"}
    assert guard.check(ctx).verdict == GuardrailVerdict.PASS
    assert guard.check(ctx).verdict == GuardrailVerdict.PASS
    assert guard.check(ctx).verdict == GuardrailVerdict.BLOCK


def test_fact_binding_blocks_unsupported_claim():
    guard = FactBinding()
    ctx = {"chapter": {"content": "Transformers are the best model [citation-needed]"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.BLOCK


def test_fact_binding_allows_supported_claim():
    guard = FactBinding()
    ctx = {"chapter": {"content": "Transformers achieve SOTA results [@vaswani2017]"}}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS


def test_output_std_blocks_informal_language():
    guard = OutputStandard()
    ctx = {"text": "this paper is super cool and awesome"}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.BLOCK


def test_output_std_allows_formal_language():
    guard = OutputStandard()
    ctx = {"text": "This paper presents a novel approach to the problem."}
    result = guard.check(ctx)
    assert result.verdict == GuardrailVerdict.PASS


def test_guardrail_manager_empty():
    """Test GuardrailManager with empty guardrail list."""
    from agent.guardrails.manager import GuardrailManager
    manager = GuardrailManager(guardrails=[])
    assert manager.check_all({"text": "test"}) == []
    assert manager.filter_papers([{"title": "Test"}]) == [{"title": "Test"}]


def test_guardrail_manager_check_all():
    """Test GuardrailManager.check_all runs all guardrails."""
    from agent.guardrails.manager import GuardrailManager
    manager = GuardrailManager()
    results = manager.check_all({"text": "This is a formal paper with citations [@ref]"})
    assert len(results) >= 2
    # All should pass for clean input
    assert all(r.verdict == GuardrailVerdict.PASS for r in results)


def test_guardrail_manager_filter_papers():
    """Test GuardrailManager.filter_papers removes blacklisted sources."""
    from agent.guardrails.manager import GuardrailManager
    from agent.guardrails.source_filter import SourceFilter
    manager = GuardrailManager(guardrails=[
        SourceFilter(blacklist=["predatory"]),
    ])
    papers = [
        {"title": "Good Paper", "journal": "ieeetran"},
        {"title": "Bad Paper", "journal": "predatory-journal"},
    ]
    filtered = manager.filter_papers(papers)
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Good Paper"


def test_guardrail_manager_check_tool_call():
    """Test GuardrailManager.check_tool_call runs OpSafety and RateLimit."""
    from agent.guardrails.manager import GuardrailManager
    from agent.guardrails.op_safety import OpSafety
    from agent.guardrails.rate_limit import RateLimit
    manager = GuardrailManager(guardrails=[
        OpSafety(),
        RateLimit(max_calls=100, window_seconds=60),
    ])
    result = manager.check_tool_call("ls", {"command": "ls -la"})
    assert result.verdict == GuardrailVerdict.PASS
    result = manager.check_tool_call("rm", {"command": "rm -rf /"})
    assert result.verdict == GuardrailVerdict.REQUIRE_APPROVAL
