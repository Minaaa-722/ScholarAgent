import pytest
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict
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
    ctx = {"paper": {"journal": "cvpr"}}
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
