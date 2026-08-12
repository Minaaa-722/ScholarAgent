from fastapi import APIRouter, Depends
from api.models import SurveyRequest, SurveyResponse, PaperItem, PaperListResponse, GraphNode, GraphLink, GraphResponse
from agent.core.harness import Harness

router = APIRouter(prefix="/api/survey", tags=["survey"])


def get_harness() -> Harness:
    from api.main import _harness
    return _harness


@router.post("", response_model=SurveyResponse)
async def create_survey(req: SurveyRequest, harness: Harness = Depends(get_harness)):
    harness.run_async(
        topic=req.topic, keywords=req.keywords, goal=req.goal, max_papers=req.max_papers,
        year_start=req.year_start or None, year_end=req.year_end or None,
    )
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.get("/status", response_model=SurveyResponse)
async def get_status(harness: Harness = Depends(get_harness)):
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/interrupt", response_model=SurveyResponse)
async def interrupt_survey(harness: Harness = Depends(get_harness)):
    harness.interrupt()
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/resume", response_model=SurveyResponse)
async def resume_survey(harness: Harness = Depends(get_harness)):
    harness.resume()
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/cancel", response_model=SurveyResponse)
async def cancel_survey(harness: Harness = Depends(get_harness)):
    """Cancel the current pipeline and reset all state back to idle."""
    harness.cancel()
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/restart", response_model=SurveyResponse)
async def restart_survey(harness: Harness = Depends(get_harness)):
    harness.restart()
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.get("/paper")
async def get_paper(harness: Harness = Depends(get_harness)):
    return harness.get_paper()


@router.get("/log")
async def get_execution_log(harness: Harness = Depends(get_harness)):
    return {"execution_log": harness.get_execution_log()}


@router.get("/papers", response_model=PaperListResponse)
async def get_papers(harness: Harness = Depends(get_harness)):
    """Return the list of retrieved papers."""
    info = harness.get_task_info()
    papers_data = info.get("execution_details", {}).get("papers", {})
    raw_list = papers_data.get("list", [])
    items = []
    for idx, p in enumerate(raw_list):
        items.append(PaperItem(
            title=p.get("title", "Untitled"),
            authors=p.get("authors", "Unknown"),
            year=str(p.get("year", "")),
            citations=p.get("citations", 0),
            source=p.get("source", "unknown"),
            paper_index=idx,
        ))
    return PaperListResponse(papers=items, total=papers_data.get("total", len(items)))


@router.get("/papers/graph", response_model=GraphResponse)
async def get_papers_graph(harness: Harness = Depends(get_harness)):
    """Build a citation/co-authorship graph from the paper list."""
    raw_papers = harness._papers if hasattr(harness, '_papers') else []
    nodes = []
    links = []
    for idx, p in enumerate(raw_papers):
        title = p.get("title", "Untitled")
        source = "arxiv" if p.get("arxiv_id") else "semantic_scholar" if p.get("source") == "semantic_scholar" else "unknown"
        citations = p.get("citation_count", 0) or 0
        nodes.append(GraphNode(
            id=idx,
            label=title[:60],
            group=source,
            size=max(1, min(citations, 100)),
        ))
    # Create links between papers that share authors
    for i, p1 in enumerate(raw_papers):
        authors1 = set(a.lower() for a in p1.get("authors", []) if a)
        if not authors1:
            continue
        for j in range(i + 1, len(raw_papers)):
            p2 = raw_papers[j]
            authors2 = set(a.lower() for a in p2.get("authors", []) if a)
            shared = authors1 & authors2
            if shared:
                links.append(GraphLink(source=i, target=j, weight=len(shared)))
    return GraphResponse(nodes=nodes, links=links)


@router.get("/papers/{index:int}")
async def get_paper_detail(index: int, harness: Harness = Depends(get_harness)):
    """Return full metadata for a single paper by index."""
    raw_papers = harness._papers if hasattr(harness, '_papers') else []
    if index < 0 or index >= len(raw_papers):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Paper index {index} not found")
    p = raw_papers[index]
    return PaperItem(
        title=p.get("title", "Untitled"),
        authors=", ".join(p.get("authors", [])) if isinstance(p.get("authors"), list) else str(p.get("authors", "Unknown")),
        year=str(p.get("year", "")),
        citations=p.get("citation_count", 0) or 0,
        source="arxiv" if p.get("arxiv_id") else p.get("source", "unknown"),
        paper_index=index,
    )


@router.get("/papers/export")
async def export_papers_csv(harness: Harness = Depends(get_harness)):
    """Export papers as a CSV file (UTF-8 with BOM for Excel compatibility)."""
    import csv, io
    from fastapi.responses import StreamingResponse

    info = harness.get_task_info()
    papers_data = info.get("execution_details", {}).get("papers", {})
    raw_list = papers_data.get("list", [])

    output = io.StringIO()
    output.write("﻿")  # BOM for Excel
    writer = csv.writer(output)
    writer.writerow(["Title", "Authors", "Year", "Citations", "Source"])

    for p in raw_list:
        writer.writerow([
            p.get("title", ""),
            p.get("authors", ""),
            p.get("year", ""),
            p.get("citations", 0),
            p.get("source", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=papers.csv"},
    )