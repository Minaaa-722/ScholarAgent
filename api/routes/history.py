from fastapi import APIRouter, Depends, HTTPException
from api.models import HistoryItem, HistoryDetail, PaperItem
from agent.core.harness import Harness

router = APIRouter(prefix="/api/history", tags=["history"])


def get_harness() -> Harness:
    from api.main import _harness
    return _harness


@router.get("", response_model=list[HistoryItem])
async def get_history(harness: Harness = Depends(get_harness)):
    """Return summary list of all past tasks."""
    mem = harness._memory_integration
    entries = mem.get_task_history()
    result = []
    for entry in entries:
        result.append(HistoryItem(
            id=entry.get("id", ""),
            topic=entry.get("topic", ""),
            keywords=entry.get("keywords", []),
            goal=entry.get("goal", ""),
            status=entry.get("status", ""),
            timestamp=entry.get("timestamp", ""),
            paper_count=len(entry.get("papers", [])),
            has_warnings=entry.get("has_warnings", False),
            rounds=entry.get("rounds", 0),
        ))
    return result


@router.get("/{entry_id}", response_model=HistoryDetail)
async def get_history_detail(entry_id: str, harness: Harness = Depends(get_harness)):
    """Return full detail for one task, including papers and final_paper."""
    mem = harness._memory_integration
    entry = mem.get_task_history_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"History entry '{entry_id}' not found")

    papers = []
    for idx, p in enumerate(entry.get("papers", [])):
        papers.append(PaperItem(
            title=p.get("title", "Untitled"),
            authors=p.get("authors", "Unknown"),
            year=str(p.get("year", "")),
            citations=p.get("citations", 0),
            source=p.get("source", "unknown"),
            paper_index=idx,
        ))

    return HistoryDetail(
        id=entry.get("id", ""),
        topic=entry.get("topic", ""),
        keywords=entry.get("keywords", []),
        goal=entry.get("goal", ""),
        status=entry.get("status", ""),
        timestamp=entry.get("timestamp", ""),
        paper_count=len(papers),
        has_warnings=entry.get("has_warnings", False),
        rounds=entry.get("rounds", 0),
        papers=papers,
        final_paper=entry.get("final_paper", ""),
    )