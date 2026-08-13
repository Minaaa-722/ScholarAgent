from agent.tools.prompts import (
    SEARCH_QUERY_PROMPT,
    RELEVANCE_JUDGE_PROMPT,
    METHODOLOGY_QUERY_PROMPT,
    CONTRIBUTION_TYPES_DETAILED,
    CONTRIBUTION_TYPES_SIMPLE,
)


def test_search_query_prompt_contains_arrow_format():
    assert "->" in SEARCH_QUERY_PROMPT
    assert "full name" in SEARCH_QUERY_PROMPT.lower()


def test_search_query_prompt_avoids_generic_queries():
    """Prompt 应禁止生成泛化检索词."""
    assert "NO generic" in SEARCH_QUERY_PROMPT
    # 检查 prompt 是否包含对 generic 词的禁用指令
    assert "deep learning" in SEARCH_QUERY_PROMPT.lower()  # 出现在禁用示例中
    assert "survey" in SEARCH_QUERY_PROMPT.lower()  # 出现在禁用示例中


def test_search_query_prompt_exactly_5():
    assert "exactly 5" in SEARCH_QUERY_PROMPT


def test_relevance_judge_prompt_contains_topic_placeholder():
    assert "{topic}" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_has_format_placeholders():
    """RELEVANCE_JUDGE_PROMPT 应包含所有 format 占位符."""
    assert "{topic}" in RELEVANCE_JUDGE_PROMPT
    assert "{contribution_types}" in RELEVANCE_JUDGE_PROMPT
    assert "{reason_field}" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_has_confidence():
    assert "CONFIDENCE" in RELEVANCE_JUDGE_PROMPT
    assert "0.0" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_no_abstract_rule():
    assert "abstract" in RELEVANCE_JUDGE_PROMPT.lower()


def test_relevance_judge_prompt_json_output():
    assert "JSON" in RELEVANCE_JUDGE_PROMPT
    assert "judgments" in RELEVANCE_JUDGE_PROMPT


def test_relevance_prompt_uses_double_braces():
    """RELEVANCE_JUDGE_PROMPT JSON 示例应使用 {{ }} 保格式安全."""
    prompt = RELEVANCE_JUDGE_PROMPT
    assert "{{" in prompt
    assert "}}" in prompt


def test_methodology_prompt_has_method_category_guidance():
    """METHODOLOGY_QUERY_PROMPT 应包含方法类别引导."""
    prompt = METHODOLOGY_QUERY_PROMPT
    assert "method category" in prompt.lower() or "design space" in prompt.lower()
    assert "->" in prompt
    assert "{topic}" in prompt


def test_contribution_types_detailed_has_4_levels():
    """CONTRIBUTION_TYPES_DETAILED 应包含完整 4 级分类."""
    assert "strong" in CONTRIBUTION_TYPES_DETAILED
    assert "weak_extension" in CONTRIBUTION_TYPES_DETAILED
    assert "weak_application" in CONTRIBUTION_TYPES_DETAILED
    assert "irrelevant" in CONTRIBUTION_TYPES_DETAILED


def test_contribution_types_simple_has_3_levels():
    """CONTRIBUTION_TYPES_SIMPLE 应包含简易 3 级分类."""
    assert "relevant" in CONTRIBUTION_TYPES_SIMPLE
    assert "weak" in CONTRIBUTION_TYPES_SIMPLE
    assert "irrelevant" in CONTRIBUTION_TYPES_SIMPLE


def test_relevance_prompt_format_with_detailed_types():
    """验证 RELEVANCE_JUDGE_PROMPT 在 4 级模式下可正常 format."""
    prompt = RELEVANCE_JUDGE_PROMPT.format(
        topic="test topic",
        contribution_types=CONTRIBUTION_TYPES_DETAILED,
        reason_field=', "reason": "Short justification"',
    )
    assert "test topic" in prompt
    assert "strong" in prompt
    assert "weak_extension" in prompt
    assert "weak_application" in prompt
    assert "irrelevant" in prompt
    assert "reason" in prompt


def test_relevance_prompt_format_with_simple_types_no_reason():
    """验证 RELEVANCE_JUDGE_PROMPT 在 3 级模式 + 关闭 reason 时可正常 format."""
    prompt = RELEVANCE_JUDGE_PROMPT.format(
        topic="test topic",
        contribution_types=CONTRIBUTION_TYPES_SIMPLE,
        reason_field="",
    )
    assert "test topic" in prompt
    assert "relevant" in prompt
    assert "weak" in prompt
    assert "irrelevant" in prompt
    assert '"reason"' not in prompt