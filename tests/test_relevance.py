import json
from agent.tools.models import Paper
from agent.core.config import SearchConfig
from agent.core.llm import MockLLM


def test_filter_keep_strong():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Core Paper", "relevance": "strong", "confidence": 0.95, "reason": "Direct match"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Core Paper", abstract="Important research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance == "strong"


def test_filter_keep_weak():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Peripheral", "relevance": "weak", "confidence": 0.7, "reason": "Related work"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Peripheral", abstract="Somewhat related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1


def test_filter_remove_irrelevant_high_confidence():
    """Fix 3: irrelevant + confidence >= 0.6 剔除."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Unrelated", "relevance": "irrelevant", "confidence": 0.9, "reason": "Different field"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Unrelated", abstract="Physics research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 0


def test_filter_keep_irrelevant_low_confidence():
    """Fix 3: irrelevant + confidence < 0.6 降级 weak 保留."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Ambiguous", "relevance": "irrelevant", "confidence": 0.4, "reason": "Uncertain"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Ambiguous", abstract="Maybe related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance == "weak"


def test_filter_no_abstract_cap_confidence():
    """无摘要时 confidence 上限 0.6，且不可为 strong."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "No Abstract", "relevance": "strong", "confidence": 0.95, "reason": "Looks good"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="No Abstract", abstract="")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance_confidence <= 0.6
    assert result[0].relevance == "weak"


def test_filter_empty_papers():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response="{}")
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    assert rf.filter([], "topic") == []


def test_filter_llm_parse_failure():
    """LLM 返回非 JSON 时保留全部."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response="Not valid JSON")
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Paper A", abstract="Test")]
    result = rf.filter(papers, "topic")
    assert len(result) == 1


def test_filter_all_irrelevant_low_conf_kept():
    """所有 irrelevant 但 confidence<0.6，全部保留为 weak."""
    from agent.tools.relevance import RelevanceFilter

    judgments = {"judgments": [
        {"index": 1, "title": "Paper A", "relevance": "irrelevant", "confidence": 0.3, "reason": "?"},
        {"index": 2, "title": "Paper B", "relevance": "irrelevant", "confidence": 0.2, "reason": "?"},
    ]}
    llm = MockLLM(fixed_response=json.dumps(judgments))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Paper A", abstract="A"), Paper(title="Paper B", abstract="B")]
    result = rf.filter(papers, "topic")
    assert len(result) == 2
    assert all(p.relevance == "weak" for p in result)