from agent.tools.models import Paper


def test_paper_default_values():
    p = Paper()
    assert p.title == ""
    assert p.authors == []
    assert p.abstract == ""
    assert p.year == 0
    assert p.relevance == "weak"
    assert p.relevance_confidence == 0.0
    assert p.composite_score == 0.0
    assert p.hit_channels == []
    assert p.search_source_queries == []
    assert p.extra == {}


def test_paper_with_all_fields():
    p = Paper(
        title="Test Paper",
        authors=["Alice", "Bob"],
        abstract="A test abstract",
        year=2024,
        arxiv_id="2401.12345",
        source="arxiv",
        url="https://arxiv.org/abs/2401.12345",
        venue="CVPR",
        citation_count=100,
        doi="10.1234/test",
        paper_id="abc123",
        categories=["cs.CV"],
        hit_channels=["arxiv_ti"],
        relevance="strong",
        relevance_confidence=0.95,
        relevance_reason="Directly addresses the topic",
        composite_score=0.85,
        search_source_queries=["vision transformer"],
        extra={"debug": True},
    )
    assert p.title == "Test Paper"
    assert p.relevance == "strong"
    assert p.relevance_confidence == 0.95
    assert p.composite_score == 0.85
    assert "vision transformer" in p.search_source_queries
    assert p.extra["debug"] is True


def test_paper_to_dict():
    p = Paper(title="Test", year=2024, relevance="strong")
    d = p.to_dict()
    assert d["title"] == "Test"
    assert d["year"] == 2024
    assert d["relevance"] == "strong"
    assert d["relevance_confidence"] == 0.0
    assert d["hit_channels"] == []


def test_paper_from_dict():
    d = {
        "title": "Test",
        "year": 2024,
        "relevance": "strong",
        "relevance_confidence": 0.95,
        "hit_channels": ["arxiv_ti"],
    }
    p = Paper.from_dict(d)
    assert p.title == "Test"
    assert p.year == 2024
    assert p.relevance == "strong"
    assert p.relevance_confidence == 0.95
    assert p.hit_channels == ["arxiv_ti"]


def test_paper_from_dict_ignores_extra_fields():
    d = {"title": "Test", "unknown_field": "should be ignored"}
    p = Paper.from_dict(d)
    assert p.title == "Test"


def test_paper_to_dict_from_dict_roundtrip():
    p = Paper(title="Test", year=2024, citation_count=42, relevance="strong")
    d = p.to_dict()
    p2 = Paper.from_dict(d)
    assert p2.title == p.title
    assert p2.year == p.year
    assert p2.citation_count == p.citation_count
    assert p2.relevance == p.relevance


def test_contribution_type_default():
    p = Paper(title="Test")
    assert p.contribution_type == "weak_application"


def test_contribution_type_roundtrip():
    p = Paper(title="Test", contribution_type="strong")
    d = p.to_dict()
    assert d["contribution_type"] == "strong"
    p2 = Paper.from_dict(d)
    assert p2.contribution_type == "strong"


def test_contribution_type_from_dict_default():
    # from_dict with missing field uses Paper default
    p2 = Paper.from_dict({"title": "Test"})
    assert p2.contribution_type == "weak_application"
