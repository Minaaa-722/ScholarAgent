import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app
from api.routes.survey import get_harness as survey_get_harness
from api.routes.history import get_harness as history_get_harness
from agent.core.llm import MockLLM
from agent.core.harness import Harness, HarnessConfig


@pytest.fixture
def test_harness():
    llm = MockLLM(fixed_response="Survey content")
    h = Harness(config=HarnessConfig(), llm=llm)
    return h


@pytest.fixture
def client(test_harness):
    app.dependency_overrides[survey_get_harness] = lambda: test_harness
    app.dependency_overrides[history_get_harness] = lambda: test_harness
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_create_survey(client):
    response = await client.post("/api/survey", json={
        "topic": "Transformer Models",
        "keywords": "attention, BERT, GPT",
        "goal": "Survey transformer architectures",
        "max_papers": 20,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "Transformer Models"
    assert data["status"] in ("PLANNING", "RETRIEVAL")  # Race: mock LLM may progress quickly


@pytest.mark.asyncio
async def test_get_survey_status(client, test_harness):
    test_harness.start(topic="Test")
    response = await client.get("/api/survey/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PLANNING"


@pytest.mark.asyncio
async def test_interrupt_survey(client, test_harness):
    test_harness.start(topic="Test")
    response = await client.post("/api/survey/interrupt")
    assert response.status_code == 200
    assert response.json()["status"] == "INTERRUPTED"


@pytest.mark.asyncio
async def test_resume_survey(client, test_harness):
    test_harness.start(topic="Test")
    test_harness.interrupt()
    response = await client.post("/api/survey/resume")
    assert response.status_code == 200
    assert response.json()["status"] == "PLANNING"


@pytest.mark.asyncio
async def test_submit_feedback(client, test_harness):
    test_harness.start(topic="Test")
    test_harness._pipeline_running = True  # Simulate running pipeline
    response = await client.post("/api/feedback", json={
        "category": "literature",
        "content": "Add more papers on attention mechanisms",
    })
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_papers_empty(client, test_harness):
    """Returns empty list when no papers exist."""
    response = await client.get("/api/survey/papers")
    assert response.status_code == 200
    data = response.json()
    assert data["papers"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_papers_with_data(client, test_harness):
    """Returns paper list when papers exist."""
    test_harness._papers = [
        {"title": "Paper One", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
        {"title": "Paper Two", "authors": ["Bob", "Charlie"], "year": "2024", "citation_count": 5, "source": "semantic_scholar"},
    ]
    response = await client.get("/api/survey/papers")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["papers"][0]["title"] == "Paper One"
    assert data["papers"][0]["authors"] == "Alice"
    assert data["papers"][0]["source"] == "arxiv"
    assert data["papers"][1]["title"] == "Paper Two"
    assert data["papers"][1]["source"] == "semantic_scholar"


@pytest.mark.asyncio
async def test_get_papers_graph(client, test_harness):
    """Returns graph nodes and links."""
    test_harness._papers = [
        {"title": "Paper A", "authors": ["Alice"], "year": "2023", "citation_count": 15, "arxiv_id": "123"},
        {"title": "Paper B", "authors": ["Bob"], "year": "2024", "citation_count": 3, "source": "semantic_scholar"},
    ]
    response = await client.get("/api/survey/papers/graph")
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["label"] == "Paper A"
    assert data["nodes"][0]["size"] == 15
    assert data["nodes"][0]["group"] == "arxiv"
    assert isinstance(data["links"], list)


@pytest.mark.asyncio
async def test_get_paper_by_index(client, test_harness):
    """Returns a single paper by index."""
    test_harness._papers = [
        {"title": "Paper One", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
    ]
    response = await client.get("/api/survey/papers/0")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Paper One"
    assert data["paper_index"] == 0


@pytest.mark.asyncio
async def test_get_paper_not_found(client, test_harness):
    """Returns 404 for out-of-range index."""
    response = await client.get("/api/survey/papers/999")
    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_export_papers_csv(client, test_harness):
    """Returns CSV file with paper data."""
    test_harness._papers = [
        {"title": "Paper One", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
    ]
    response = await client.get("/api/survey/papers/export")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    body = response.text
    assert "Title" in body
    assert "Paper One" in body
    assert "Alice" in body


@pytest.mark.asyncio
async def test_get_history_empty(client, test_harness):
    """Returns empty list when no history exists."""
    test_harness._memory_integration.session.clear()
    response = await client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_get_history_with_data(client, test_harness):
    """Returns history entries when tasks exist."""
    from agent.core.pipeline import TaskInfo
    mem = test_harness._memory_integration
    mem.session.clear()
    task = TaskInfo(topic="Test Topic", keywords=["ai"], goal="Goal")
    result = {
        "status": "complete",
        "paper": "\\section{Paper}",
        "papers": [
            {"title": "Paper A", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
        ],
        "rounds": 1,
        "has_warnings": False,
    }
    mem.save_task_history(task, result)

    response = await client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["topic"] == "Test Topic"
    assert data[0]["paper_count"] == 1
    assert "final_paper" not in data[0]  # Summary only


@pytest.mark.asyncio
async def test_get_history_detail(client, test_harness):
    """Returns full detail for a specific history entry."""
    from agent.core.pipeline import TaskInfo
    mem = test_harness._memory_integration
    mem.session.clear()
    task = TaskInfo(topic="Detail Topic", keywords=["ml"], goal="Detail goal")
    result = {
        "status": "complete",
        "paper": "\\section{Detail Paper}\nContent.",
        "papers": [
            {"title": "Paper A", "authors": ["Alice"], "year": "2023", "citation_count": 10, "arxiv_id": "2301.001"},
        ],
        "rounds": 2,
        "has_warnings": True,
    }
    mem.save_task_history(task, result)
    entry_id = mem.get_task_history()[0]["id"]

    response = await client.get(f"/api/history/{entry_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "Detail Topic"
    assert data["final_paper"] == "\\section{Detail Paper}\nContent."
    assert len(data["papers"]) == 1
    assert data["papers"][0]["title"] == "Paper A"
    assert data["rounds"] == 2
    assert data["has_warnings"] is True


@pytest.mark.asyncio
async def test_get_history_detail_not_found(client):
    """Returns 404 for non-existent UUID."""
    response = await client.get("/api/history/nonexistent")
    assert response.status_code == 404