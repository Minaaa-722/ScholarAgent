from agent.tools.prompts import SEARCH_QUERY_PROMPT, RELEVANCE_JUDGE_PROMPT, METHODOLOGY_QUERY_PROMPT


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


def test_relevance_judge_prompt_has_contribution_types():
    """RELEVANCE_JUDGE_PROMPT 应包含 4 种贡献类型."""
    assert "strong" in RELEVANCE_JUDGE_PROMPT.lower()
    assert "weak_extension" in RELEVANCE_JUDGE_PROMPT
    assert "weak_application" in RELEVANCE_JUDGE_PROMPT
    assert "irrelevant" in RELEVANCE_JUDGE_PROMPT
    assert "contribution_type" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_has_confidence():
    assert "CONFIDENCE" in RELEVANCE_JUDGE_PROMPT
    assert "0.0" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_no_abstract_rule():
    assert "abstract" in RELEVANCE_JUDGE_PROMPT.lower()
    assert "strong" in RELEVANCE_JUDGE_PROMPT.lower()


def test_relevance_judge_prompt_json_output():
    assert "JSON" in RELEVANCE_JUDGE_PROMPT
    assert "judgments" in RELEVANCE_JUDGE_PROMPT


def test_methodology_prompt_has_method_category_guidance():
    """METHODOLOGY_QUERY_PROMPT 应包含方法类别引导."""
    prompt = METHODOLOGY_QUERY_PROMPT
    assert "method category" in prompt.lower() or "design space" in prompt.lower()
    assert "->" in prompt
    assert "{topic}" in prompt


def test_relevance_prompt_has_contribution_types():
    """RELEVANCE_JUDGE_PROMPT 应定义所有 4 种贡献类型."""
    prompt = RELEVANCE_JUDGE_PROMPT
    assert "strong" in prompt
    assert "weak_extension" in prompt
    assert "weak_application" in prompt
    assert "irrelevant" in prompt
    assert "contribution_type" in prompt


def test_relevance_prompt_examples():
    """RELEVANCE_JUDGE_PROMPT 应包含贡献类型示例."""
    prompt = RELEVANCE_JUDGE_PROMPT
    assert "methodological" in prompt.lower() or "core method" in prompt.lower()


def test_relevance_prompt_uses_double_braces():
    """RELEVANCE_JUDGE_PROMPT JSON 示例应使用 {{ }} 保格式安全."""
    prompt = RELEVANCE_JUDGE_PROMPT
    assert "{{" in prompt
    assert "}}" in prompt