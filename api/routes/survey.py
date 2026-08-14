import logging
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse
from api.models import SurveyRequest, SurveyResponse, PaperItem, PaperListResponse, GraphNode, GraphLink, GraphResponse
from agent.core.harness import Harness
from agent.core.llm import OpenAILLM
from api.routes.credentials import _resolve_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/survey", tags=["survey"])


def get_harness() -> Harness:
    from api.main import _harness
    return _harness


# ---------------------------------------------------------------------------
# 新增：LLM 连通性测试函数
# 复用 OpenAILLM 的初始化逻辑（base_url、model 统一管理），避免配置两份不一致
# 使用极低 token 消耗的 ping 请求（max_tokens=1）
# ---------------------------------------------------------------------------
def _test_llm_connectivity(api_key: str) -> str | None:
    """Test LLM connectivity by sending a minimal ping request.

    Reuses the existing OpenAILLM configuration (base_url, model) to ensure
    configuration consistency — avoids duplicating default values.

    Returns:
        None on success, or an error message string on failure.
    """
    try:
        # 复用 OpenAILLM 的初始化逻辑，确保 base_url/model 与环境变量保持一致
        llm = OpenAILLM(api_key=api_key)
        # 极低 token 消耗的 ping 请求
        llm.client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return None
    except Exception as e:
        error_name = type(e).__name__
        error_str = str(e)

        # 鉴权失败 (401)
        if hasattr(e, 'status_code') and e.status_code == 401:
            return "LLM_API_KEY无效、过期或权限不足，请前往Credentials页面重新配置密钥"
        auth_keywords = ("401", "Unauthorized", "Authentication", "auth")
        error_lower = error_str.lower()
        if any(kw.lower() in error_lower for kw in auth_keywords):
            return "LLM_API_KEY无效、过期或权限不足，请前往Credentials页面重新配置密钥"

        # 网络超时/连接失败
        network_keywords = [
            "timeout", "connection", "connect",
            "nameresolution", "name or service",
        ]
        if any(kw in error_lower for kw in network_keywords):
            return f"无法连接到LLM服务，请检查网络连接和API地址(LLM_BASE_URL)配置: {error_name}"

        # 其他异常
        return f"LLM连通性测试失败: {error_name}: {error_str}"


# ---------------------------------------------------------------------------
# 改造：create_survey 增加 LLM 密钥前置校验
# 校验通过才允许创建流水线任务，校验失败直接拦截
# ---------------------------------------------------------------------------
@router.post("")
async def create_survey(req: SurveyRequest, harness: Harness = Depends(get_harness)):
    # 前置校验①：检查 LLM_API_KEY 是否已配置
    api_key = _resolve_credential("LLM_API_KEY")
    if not api_key:
        logger.warning("任务启动拦截: LLM_API_KEY 未配置")
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "未配置LLM_API_KEY，请前往Credentials页面填写有效的API密钥后再启动任务",
            },
        )

    # 前置校验②：连通性测试，验证密钥是否有效
    error_msg = _test_llm_connectivity(api_key)
    if error_msg is not None:
        logger.warning("任务启动拦截: LLM 连通性测试失败 — %s", error_msg)
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": error_msg,
            },
        )

    # 前置校验全部通过 → 正常创建并启动流水线任务
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
        source = (
            "arxiv" if p.get("arxiv_id")
            else "semantic_scholar" if p.get("source") == "semantic_scholar"
            else "unknown"
        )
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
        authors=(
            ", ".join(p.get("authors", []))
            if isinstance(p.get("authors"), list)
            else str(p.get("authors", "Unknown"))
        ),
        year=str(p.get("year", "")),
        citations=p.get("citation_count", 0) or 0,
        source="arxiv" if p.get("arxiv_id") else p.get("source", "unknown"),
        paper_index=index,
    )


@router.get("/papers/export")
async def export_papers_csv(harness: Harness = Depends(get_harness)):
    """Export papers as a CSV file (UTF-8 with BOM for Excel compatibility)."""
    import csv
    import io
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
