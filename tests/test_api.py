import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app
from api.routes.survey import get_harness
from agent.core.llm import MockLLM
from agent.core.harness import Harness, HarnessConfig


@pytest.fixture
def test_harness():
    llm = MockLLM(fixed_response="Survey content")
    h = Harness(config=HarnessConfig(), llm=llm)
    return h


@pytest.fixture
def client(test_harness):
    app.dependency_overrides[get_harness] = lambda: test_harness
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
    assert data["status"] == "PLANNING"


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
    response = await client.post("/api/feedback", json={
        "category": "literature",
        "content": "Add more papers on attention mechanisms",
    })
    assert response.status_code == 200