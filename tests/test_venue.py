"""Tests for VenueLookup."""
from agent.tools.venue import VenueLookup, TOP_VENUES


def test_is_top_venue():
    assert "cvpr" in TOP_VENUES
    assert "neurips" in TOP_VENUES
    assert "iclr" in TOP_VENUES
    assert "non_existent_venue" not in TOP_VENUES


def test_venue_lookup_skip_existing_top():
    """Papers already marked as top venue should be skipped."""
    lookup = VenueLookup()
    papers = [
        {"title": "A", "venue": "CVPR", "is_top_venue": True},
    ]
    result = lookup.execute({"papers": papers})
    assert result.success
    assert result.data["papers"][0]["is_top_venue"] is True


def test_venue_lookup_normalize():
    """Venue name normalization should work."""
    assert VenueLookup._normalize_venue("  Proceedings of CVPR  ") == "cvpr"
    assert VenueLookup._normalize_venue("IEEE/CVF CVPR") == "cvpr"
    assert VenueLookup._normalize_venue("NeurIPS 2023") == "neurips"


def test_venue_lookup_empty():
    lookup = VenueLookup()
    result = lookup.execute({"papers": []})
    assert result.success
    assert result.data["papers"] == []


def test_venue_lookup_no_change_on_unknown():
    """Papers without venue info should remain unchanged (no crash)."""
    lookup = VenueLookup()
    papers = [{"title": "Some Obscure Paper"}]
    result = lookup.execute({"papers": papers})
    assert result.success
    assert len(result.data["papers"]) == 1
    # is_top_venue should not be set (DBLP lookup failed gracefully)
    assert result.data["papers"][0].get("is_top_venue", False) is False


def test_venue_classify():
    assert VenueLookup._classify_venue("Journal of Machine Learning Research") == "journal"
    assert VenueLookup._classify_venue("CVPR") == "conference"
    assert VenueLookup._classify_venue("IEEE Transactions on Pattern Analysis") == "journal"