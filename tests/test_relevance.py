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
    """无摘要时 confidence 上限 0.6，且强制 weak_application."""
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
    assert result[0].relevance == "weak_application"
    assert result[0].contribution_type == "weak_application"


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


# === 4-level contribution type tests (Task 5) ===


def test_strong_kept():
    """strong contribution → kept unconditionally."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Core Method", "contribution_type": "strong", "confidence": 0.95, "reason": "Core method innovation"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Core Method", abstract="Novel attention mechanism")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "strong"


def test_weak_extension_kept():
    """weak_extension → kept unconditionally."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Extension Work", "contribution_type": "weak_extension", "confidence": 0.8, "reason": "Extends method to new domain"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Extension Work", abstract="Adapting method to medical imaging")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_extension"


def test_weak_application_high_conf_kept():
    """weak_application with high confidence → kept."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "App Paper", "contribution_type": "weak_application", "confidence": 0.85, "reason": "Uses method for classification"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="App Paper", abstract="Using X for Y classification")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_application"


def test_weak_application_low_conf_kept():
    """weak_application with low confidence → kept (no removal)."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Low Conf App", "contribution_type": "weak_application", "confidence": 0.4, "reason": "Uncertain application"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Low Conf App", abstract="Some application")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_application"


def test_irrelevant_high_conf_removed():
    """irrelevant + confidence >= 0.6 → removed."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Unrelated", "contribution_type": "irrelevant", "confidence": 0.9, "reason": "Different field"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Unrelated", abstract="Physics research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 0


def test_irrelevant_low_conf_downgraded():
    """irrelevant + confidence < 0.6 → downgraded to weak_application."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "Ambiguous", "contribution_type": "irrelevant", "confidence": 0.4, "reason": "Uncertain"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Ambiguous", abstract="Maybe related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_application"


def test_no_abstract_forced_weak_application():
    """无摘要 → forced to weak_application, confidence capped at 0.6."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [{"index": 1, "title": "No Abstract", "contribution_type": "strong", "confidence": 0.95, "reason": "Looks good"}]
    }))
    config = SearchConfig()
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="No Abstract", abstract="")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_application"
    assert result[0].relevance_confidence <= 0.6


def test_parse_judgments_contribution_type():
    """_parse_judgments 读取 contribution_type 字段."""
    from agent.tools.relevance import RelevanceFilter

    text = json.dumps({
        "judgments": [
            {"index": 1, "title": "Paper A", "contribution_type": "strong", "confidence": 0.9, "reason": "A"},
            {"index": 2, "title": "Paper B", "contribution_type": "weak_extension", "confidence": 0.7, "reason": "B"},
        ]
    })
    result = RelevanceFilter._parse_judgments(text)
    assert result["paper a"]["contribution_type"] == "strong"
    assert result["paper b"]["contribution_type"] == "weak_extension"