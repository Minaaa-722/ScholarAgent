from agent.tools.prompts import SEARCH_QUERY_PROMPT, RELEVANCE_JUDGE_PROMPT


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


def test_relevance_judge_prompt_three_levels():
    assert "STRONG" in RELEVANCE_JUDGE_PROMPT
    assert "WEAK" in RELEVANCE_JUDGE_PROMPT
    assert "IRRELEVANT" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_has_confidence():
    assert "CONFIDENCE" in RELEVANCE_JUDGE_PROMPT
    assert "0.0" in RELEVANCE_JUDGE_PROMPT


def test_relevance_judge_prompt_no_abstract_rule():
    assert "abstract" in RELEVANCE_JUDGE_PROMPT.lower()
    assert "strong" in RELEVANCE_JUDGE_PROMPT.lower()


def test_relevance_judge_prompt_json_output():
    assert "JSON" in RELEVANCE_JUDGE_PROMPT
    assert "judgments" in RELEVANCE_JUDGE_PROMPT