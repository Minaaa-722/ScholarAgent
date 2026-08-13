import json
from agent.tools.models import Paper
from agent.core.config import SearchConfig
from agent.core.llm import MockLLM


def test_filter_keep_strong():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Core Paper", "relevance": "strong",
             "confidence": 0.95, "reason": "Direct match"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False  # 兼容旧测试
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Core Paper", abstract="Important research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance == "strong"


def test_filter_keep_weak():
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Peripheral", "relevance": "weak",
             "confidence": 0.7, "reason": "Related work"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Peripheral", abstract="Somewhat related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1


def test_filter_remove_irrelevant_high_confidence():
    """Fix 3: irrelevant + confidence >= 0.6 剔除."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Unrelated", "relevance": "irrelevant",
             "confidence": 0.9, "reason": "Different field"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Unrelated", abstract="Physics research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 0


def test_filter_keep_irrelevant_low_confidence():
    """Fix 3: irrelevant + confidence < 0.6 降级 weak 保留."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Ambiguous", "relevance": "irrelevant",
             "confidence": 0.4, "reason": "Uncertain"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Ambiguous", abstract="Maybe related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].relevance == "weak"


def test_filter_no_abstract_cap_confidence():
    """无摘要时 confidence 上限 0.6，且强制 weak_application."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "No Abstract", "relevance": "strong",
             "confidence": 0.95, "reason": "Looks good"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
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
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    assert rf.filter([], "topic") == []


def test_filter_llm_parse_failure():
    """LLM 返回非 JSON 时保留全部."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response="Not valid JSON")
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
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
    config.relevance_keyword_filter_enabled = False
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
        "judgments": [
            {"index": 1, "title": "Core Method", "contribution_type": "strong",
             "confidence": 0.95, "reason": "Core method innovation"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Core Method", abstract="Novel attention mechanism")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "strong"


def test_weak_extension_kept():
    """weak_extension → kept unconditionally."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Extension Work", "contribution_type": "weak_extension",
             "confidence": 0.8, "reason": "Extends method to new domain"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Extension Work", abstract="Adapting method to medical imaging")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_extension"


def test_weak_application_high_conf_kept():
    """weak_application with high confidence → kept."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "App Paper", "contribution_type": "weak_application",
             "confidence": 0.85, "reason": "Uses method for classification"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="App Paper", abstract="Using X for Y classification")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_application"


def test_weak_application_low_conf_kept():
    """weak_application with low confidence → kept (no removal)."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Low Conf App", "contribution_type": "weak_application",
             "confidence": 0.4, "reason": "Uncertain application"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Low Conf App", abstract="Some application")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_application"


def test_irrelevant_high_conf_removed():
    """irrelevant + confidence >= 0.6 → removed."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Unrelated", "contribution_type": "irrelevant",
             "confidence": 0.9, "reason": "Different field"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Unrelated", abstract="Physics research")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 0


def test_irrelevant_low_conf_downgraded():
    """irrelevant + confidence < 0.6 → downgraded to weak_application."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "Ambiguous", "contribution_type": "irrelevant",
             "confidence": 0.4, "reason": "Uncertain"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
    rf = RelevanceFilter(llm, config)
    papers = [Paper(title="Ambiguous", abstract="Maybe related")]
    result = rf.filter(papers, "test topic")
    assert len(result) == 1
    assert result[0].contribution_type == "weak_application"


def test_no_abstract_forced_weak_application():
    """无摘要 → forced to weak_application, confidence capped at 0.6."""
    from agent.tools.relevance import RelevanceFilter

    llm = MockLLM(fixed_response=json.dumps({
        "judgments": [
            {"index": 1, "title": "No Abstract", "contribution_type": "strong",
             "confidence": 0.95, "reason": "Looks good"},
        ]
    }))
    config = SearchConfig()
    config.relevance_keyword_filter_enabled = False
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


# ====================================================================
# LLM 时延优化测试（2026-08）
# ====================================================================


class TestBatchSplitting:
    """分批逻辑测试。"""

    def test_batch_split_exact(self):
        """论文数等于 max_batch_size 时只产生 1 批。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": i, "title": f"Paper {i}", "contribution_type": "strong", "confidence": 0.9}
                for i in range(1, 21)
            ]
        }))
        config = SearchConfig()
        config.relevance_max_batch_size = 20
        config.relevance_keyword_filter_enabled = False  # 禁用预过滤，只测分批
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title=f"Paper {i}", abstract=f"Abstract {i}") for i in range(1, 21)]
        result = rf.filter(papers, "test topic")
        assert len(result) == 20

    def test_batch_split_exceeds(self):
        """论文数超过 max_batch_size 时自动分批，共产生 2 批 (20+5)。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": i, "title": f"Paper {i}", "contribution_type": "strong", "confidence": 0.9}
                for i in range(1, 26)
            ]
        }))
        config = SearchConfig()
        config.relevance_max_batch_size = 20
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title=f"Paper {i}", abstract=f"Abstract {i}") for i in range(1, 26)]
        # 验证不报错且全部保留
        result = rf.filter(papers, "test topic")
        assert len(result) == 25

    def test_batch_split_single(self):
        """论文数少于 max_batch_size 时只有 1 批。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": i, "title": f"Paper {i}", "contribution_type": "strong", "confidence": 0.9}
                for i in range(1, 6)
            ]
        }))
        config = SearchConfig()
        config.relevance_max_batch_size = 20
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title=f"Paper {i}", abstract=f"Abstract {i}") for i in range(1, 6)]
        result = rf.filter(papers, "test topic")
        assert len(result) == 5


class TestCache:
    """缓存策略测试。"""

    def test_cache_hit_doi(self):
        """相同 (doi, topic) 的论文应命中缓存，不调用 LLM。"""
        from agent.tools.relevance import RelevanceFilter

        # 第一次调用：LLM 正常返回
        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [{"index": 1, "title": "Cached Paper", "contribution_type": "strong", "confidence": 0.95}]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        paper1 = Paper(title="Cached Paper", abstract="Important research", doi="10.1234/test")
        rf.filter([paper1], "test topic")

        # 第二次调用：相同 (doi, topic)，LLM 应不被调用
        # 将 MockLLM 改为返回 "irrelevant" — 如果命中缓存，应返回原来的 "strong"
        llm.fixed_response = json.dumps({
            "judgments": [{"index": 1, "title": "Cached Paper", "contribution_type": "irrelevant", "confidence": 0.9}]
        })
        paper2 = Paper(title="Cached Paper", abstract="Important research", doi="10.1234/test")
        result2 = rf.filter([paper2], "test topic")
        assert len(result2) == 1
        # 应为缓存中的 strong，而非新 LLM 返回的 irrelevant
        assert result2[0].contribution_type == "strong"

    def test_cache_miss_different_topic(self):
        """相同 DOI 但不同 topic 不应命中缓存。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [{"index": 1, "title": "Paper", "contribution_type": "strong", "confidence": 0.95}]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        paper = Paper(title="Paper", abstract="Test", doi="10.1234/test")
        rf.filter([paper], "topic A")

        # 相同 DOI 但不同 topic
        llm.fixed_response = json.dumps({
            "judgments": [{"index": 1, "title": "Paper", "contribution_type": "irrelevant", "confidence": 0.9}]
        })
        result = rf.filter([paper], "topic B")
        assert len(result) == 0  # 被新判断过滤掉，说明未命中缓存

    def test_cache_miss_no_doi(self):
        """无 DOI 的论文不应缓存。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [{"index": 1, "title": "No DOI Paper", "contribution_type": "strong", "confidence": 0.95}]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        paper = Paper(title="No DOI Paper", abstract="Test")
        rf.filter([paper], "topic")

        # 再次调用，应仍调用 LLM（无 DOI 无法缓存）
        call_count_before = len(llm.conversation_history)
        rf.filter([paper], "topic")
        assert len(llm.conversation_history) == call_count_before + 1

    def test_cache_fifo_eviction(self):
        """缓存超过 max_size 时淘汰最早的条目。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [{"index": 1, "title": "Paper X", "contribution_type": "strong", "confidence": 0.95}]
        }))
        config = SearchConfig()
        config.relevance_cache_size = 2  # 只有 2 个缓存槽位
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)

        # 填入 3 个不同 DOI 的论文，触发淘汰
        for i in range(3):
            p = Paper(title=f"Paper {i}", abstract=f"Abstract {i}", doi=f"10.1234/paper{i}")
            rf.filter([p], "topic")

        # 第一个 DOI 应已被淘汰，再次调用应不命中缓存
        call_count_before = len(llm.conversation_history)
        p0 = Paper(title="Paper 0", abstract="Abstract 0", doi="10.1234/paper0")
        _ = rf.filter([p0], "topic")
        # 应调用 LLM（缓存未命中），且结果应为 "Paper X"（MockLLM 固定）
        assert len(llm.conversation_history) == call_count_before + 1


class TestTimeoutFallback:
    """超时降级测试。"""

    def test_llm_failure_fallback(self):
        """LLM 调用失败时论文标记为 unclassified 并保留。"""
        from agent.tools.relevance import RelevanceFilter

        # 模拟一个会抛出异常的 LLM
        class FailingLLM:
            def generate(self, system_prompt, user_message, tools=None):
                raise RuntimeError("Simulated API failure")

        config = SearchConfig()
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(FailingLLM(), config)
        papers = [Paper(title="Paper A", abstract="Test abstract")]
        result = rf.filter(papers, "topic")
        assert len(result) == 1
        assert result[0].contribution_type == "weak_application"
        assert result[0].relevance_confidence == 0.5
        assert result[0].relevance == "weak"

    def test_llm_empty_response_fallback(self):
        """LLM 返回空/不可解析 JSON 时标记为 unclassified。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response="Not valid JSON at all")
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title="Paper A", abstract="Test abstract")]
        result = rf.filter(papers, "topic")
        assert len(result) == 1
        assert result[0].contribution_type == "weak_application"
        assert result[0].relevance_confidence == 0.5


class TestGrayscaleSwitch:
    """灰度开关 enable_detailed_contribution_classify 测试。"""

    def test_detailed_mode_4_class(self):
        """开启详细模式：使用 4 级分类 (strong/weak_extension/weak_application/irrelevant)。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": 1, "title": "Strong Paper", "contribution_type": "strong", "confidence": 0.95},
                {"index": 2, "title": "Extension Paper", "contribution_type": "weak_extension", "confidence": 0.8},
            ]
        }))
        config = SearchConfig()
        config.enable_detailed_contribution_classify = True
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        papers = [
            Paper(title="Strong Paper", abstract="Novel method"),
            Paper(title="Extension Paper", abstract="Extended method"),
        ]
        result = rf.filter(papers, "test topic")
        assert len(result) == 2
        assert result[0].contribution_type == "strong"
        assert result[1].contribution_type == "weak_extension"

    def test_simple_mode_3_class(self):
        """关闭详细模式：使用 3 级分类 (relevant/weak/irrelevant)。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": 1, "title": "Relevant Paper", "contribution_type": "relevant", "confidence": 0.95},
                {"index": 2, "title": "Weak Paper", "contribution_type": "weak", "confidence": 0.6},
            ]
        }))
        config = SearchConfig()
        config.enable_detailed_contribution_classify = False
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        papers = [
            Paper(title="Relevant Paper", abstract="Directly about topic"),
            Paper(title="Weak Paper", abstract="Somewhat related"),
        ]
        result = rf.filter(papers, "test topic")
        assert len(result) == 2
        assert result[0].contribution_type == "relevant"
        assert result[1].contribution_type == "weak"

    def test_simple_mode_irrelevant_removed(self):
        """3 级模式下 irrelevant + high confidence 仍应剔除。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": 1, "title": "Unrelated", "contribution_type": "irrelevant", "confidence": 0.9},
            ]
        }))
        config = SearchConfig()
        config.enable_detailed_contribution_classify = False
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title="Unrelated", abstract="Completely different field")]
        result = rf.filter(papers, "test topic")
        assert len(result) == 0


class TestKeywordPreFilter:
    """关键词预过滤测试。"""

    def test_prefilter_keeps_matching_title(self):
        """标题包含核心术语的论文应保留。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": 1, "title": "Edge Detection Paper", "contribution_type": "strong",
                 "confidence": 0.95},
            ]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = True
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title="Edge Detection in Medical Images", abstract="")]
        result = rf.filter(papers, "edge detection")
        # 标题包含 "edge" 和 "detection" → 应通过预过滤，进入 LLM
        assert len(result) == 1

    def test_prefilter_keeps_matching_abstract(self):
        """标题不匹配但摘要匹配核心术语的论文应保留。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [{"index": 1, "title": "Some Paper", "contribution_type": "strong", "confidence": 0.95}]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = True
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title="Unrelated Title", abstract="This paper is about edge detection methods")]
        result = rf.filter(papers, "edge detection")
        # 摘要包含 "edge" 和 "detection" → 应通过预过滤
        assert len(result) == 1

    def test_prefilter_removes_completely_unrelated(self):
        """标题和摘要都不包含核心术语的论文应被预过滤剔除。"""
        from agent.tools.relevance import RelevanceFilter

        # 使用一个不会抛出异常的 LLM（但预过滤应在 LLM 之前拦截）
        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": 1, "title": "Quantum Computing in Space",
                 "contribution_type": "irrelevant", "confidence": 0.9},
            ]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = True
        rf = RelevanceFilter(llm, config)
        # 论文标题和摘要都不包含 "edge" 或 "detection"
        papers = [Paper(title="Quantum Computing in Space", abstract="Star formation in distant galaxies")]
        result = rf.filter(papers, "edge detection")
        # "edge detection" 的核心术语是 "edge" 和 "detection"
        # 论文标题和摘要中都不包含这几个词 → 应被预过滤剔除
        assert len(result) == 0

    def test_prefilter_disabled(self):
        """关闭预过滤时所有论文进入 LLM。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": 1, "title": "Astronomical Object Detection",
                 "contribution_type": "irrelevant", "confidence": 0.9},
            ]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(llm, config)
        papers = [Paper(title="Astronomical Object Detection", abstract="Star formation")]
        result = rf.filter(papers, "edge detection")
        # 预过滤关闭 → 论文进入 LLM → LLM 返回 irrelevant → 被剔除
        assert len(result) == 0

    def test_prefilter_single_word_topic(self):
        """单次 topic 的核心术语提取正确。"""
        from agent.tools.relevance import RelevanceFilter

        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [{"index": 1, "title": "Paper", "contribution_type": "strong", "confidence": 0.95}]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = True
        rf = RelevanceFilter(llm, config)
        # topic="transformer" → 核心术语=["transformer"]
        papers = [Paper(title="Some Paper", abstract="This paper uses a transformer architecture")]
        result = rf.filter(papers, "transformer")
        assert len(result) == 1

    def test_prefilter_stop_words_not_false_positive(self):
        """仅命中停用词不视为核心术语匹配。"""
        from agent.tools.relevance import RelevanceFilter

        # 这个测试验证预过滤不会因为停用词而误保留
        llm = MockLLM(fixed_response=json.dumps({
            "judgments": [
                {"index": 1, "title": "Astronomy Stars", "contribution_type": "irrelevant",
                 "confidence": 0.9},
            ]
        }))
        config = SearchConfig()
        config.relevance_keyword_filter_enabled = True
        rf = RelevanceFilter(llm, config)
        # topic="for using based" → 核心术语为空（全部停用词）
        papers = [Paper(title="Astronomy Stars", abstract="Galaxy formation")]
        result = rf.filter(papers, "for using based")
        # 核心术语为空 → 不过滤，全部保留，进入 LLM
        assert len(result) == 0  # LLM 返回 irrelevant → 剔除


class TestUnclassifiedHandling:
    """unclassified 标记处理测试。"""

    def test_unclassified_kept_as_weak_application(self):
        """unclassified 论文应保留为 weak_application。"""
        from agent.tools.relevance import RelevanceFilter

        # 模拟 LLM 返回包含 unclassified 的结果
        class PartialLLM:
            def generate(self, system_prompt, user_message, tools=None):
                return type("Resp", (), {"text": "invalid json", "tool_calls": []})()

        config = SearchConfig()
        config.relevance_keyword_filter_enabled = False
        rf = RelevanceFilter(PartialLLM(), config)
        papers = [Paper(title="Paper A", abstract="Test")]
        result = rf.filter(papers, "topic")
        assert len(result) == 1
        assert result[0].contribution_type == "weak_application"
        assert result[0].relevance_confidence == 0.5
