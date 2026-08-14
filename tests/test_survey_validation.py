"""Tests for LLM API key validation on POST /api/survey.

Covers all branch scenarios of the pre-start credential validation:
  ① LLM_API_KEY 为空 —— 后端拦截返回 400
  ② LLM_API_KEY 存在但 401 无效 —— 后端拦截返回 400
  ③ 连通测试网络异常 —— 后端拦截返回 400
  ④ 密钥正常校验通过 —— 允许创建流水线任务

All tests mock _resolve_credential and _test_llm_connectivity to avoid
depending on real keyring, .env, or external OpenAI API calls.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app
from api.routes.survey import get_harness as survey_get_harness
from agent.core.llm import MockLLM
from agent.core.harness import Harness, HarnessConfig

# 使用同步 TestClient 简化测试
client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_harness_dependency():
    """Override the harness dependency with a MockLLM-based harness.

    Applied to every test in this file so the FastAPI dependency
    resolution always works, even when the route returns early.
    """
    llm = MockLLM(fixed_response="Survey content")
    h = Harness(config=HarnessConfig(), llm=llm)
    app.dependency_overrides[survey_get_harness] = lambda: h
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 场景①：LLM_API_KEY 为空
# ---------------------------------------------------------------------------
class TestApiKeyMissing:
    """_resolve_credential returns None → 400 with "未配置" message."""

    @patch("api.routes.survey._resolve_credential", return_value=None)
    def test_no_api_key_returns_400(self, mock_resolve):
        """LLM_API_KEY 不存在时返回 400 并提示未配置."""
        response = client.post("/api/survey", json={
            "topic": "Transformer Models",
            "keywords": "attention, BERT",
            "goal": "Survey",
            "max_papers": 20,
        })
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "未配置LLM_API_KEY" in data["message"]

    @patch("api.routes.survey._resolve_credential", return_value=None)
    def test_no_api_key_does_not_start_task(self, mock_resolve):
        """LLM_API_KEY 不存在时不会启动任务 —— 验证 harness 未调用."""
        # 保存原始 harness 引用，验证其 run_async 未被调用
        original_harness = app.dependency_overrides[survey_get_harness]()
        with patch.object(original_harness, "run_async") as mock_run:
            app.dependency_overrides[survey_get_harness] = lambda: original_harness
            response = client.post("/api/survey", json={
                "topic": "Transformer Models",
                "keywords": "attention, BERT",
                "goal": "Survey",
                "max_papers": 20,
            })
            assert response.status_code == 400
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# 场景②：LLM_API_KEY 存在但无效（401 鉴权失败）
# ---------------------------------------------------------------------------
class TestApiKeyInvalid:
    """_resolve_credential returns a key, _test_llm_connectivity returns 401 error."""

    @patch(
        "api.routes.survey._test_llm_connectivity",
        return_value="LLM_API_KEY无效、过期或权限不足，请前往Credentials页面重新配置密钥",
    )
    @patch("api.routes.survey._resolve_credential", return_value="sk-invalid-key")
    def test_invalid_key_returns_400(self, mock_resolve, mock_test):
        """无效密钥返回 400 并提示密钥无效."""
        response = client.post("/api/survey", json={
            "topic": "Transformer Models",
            "keywords": "attention, BERT",
            "goal": "Survey",
            "max_papers": 20,
        })
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "无效" in data["message"] or "过期" in data["message"]

    @patch(
        "api.routes.survey._test_llm_connectivity",
        return_value="LLM_API_KEY无效、过期或权限不足，请前往Credentials页面重新配置密钥",
    )
    @patch("api.routes.survey._resolve_credential", return_value="sk-invalid-key")
    def test_invalid_key_does_not_start_task(self, mock_resolve, mock_test):
        """无效密钥时不会启动任务 —— 验证 harness 未调用."""
        original_harness = app.dependency_overrides[survey_get_harness]()
        with patch.object(original_harness, "run_async") as mock_run:
            app.dependency_overrides[survey_get_harness] = lambda: original_harness
            response = client.post("/api/survey", json={
                "topic": "Transformer Models",
                "keywords": "attention, BERT",
                "goal": "Survey",
                "max_papers": 20,
            })
            assert response.status_code == 400
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# 场景③：连通测试网络异常
# ---------------------------------------------------------------------------
class TestNetworkError:
    """_test_llm_connectivity returns a network/unreachable error message."""

    @patch(
        "api.routes.survey._test_llm_connectivity",
        return_value="无法连接到LLM服务，请检查网络连接和API地址(LLM_BASE_URL)配置: APIConnectionError",
    )
    @patch("api.routes.survey._resolve_credential", return_value="sk-valid-but-unreachable")
    def test_network_error_returns_400(self, mock_resolve, mock_test):
        """网络异常返回 400 并提示连接失败."""
        response = client.post("/api/survey", json={
            "topic": "Transformer Models",
            "keywords": "attention, BERT",
            "goal": "Survey",
            "max_papers": 20,
        })
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"
        assert "网络" in data["message"] or "连接" in data["message"]

    @patch(
        "api.routes.survey._test_llm_connectivity",
        return_value="无法连接到LLM服务，请检查网络连接和API地址(LLM_BASE_URL)配置: APIConnectionError",
    )
    @patch("api.routes.survey._resolve_credential", return_value="sk-valid-but-unreachable")
    def test_network_error_does_not_start_task(self, mock_resolve, mock_test):
        """网络异常时不会启动任务 —— 验证 harness 未调用."""
        original_harness = app.dependency_overrides[survey_get_harness]()
        with patch.object(original_harness, "run_async") as mock_run:
            app.dependency_overrides[survey_get_harness] = lambda: original_harness
            response = client.post("/api/survey", json={
                "topic": "Transformer Models",
                "keywords": "attention, BERT",
                "goal": "Survey",
                "max_papers": 20,
            })
            assert response.status_code == 400
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# 场景④：密钥正常校验通过
# ---------------------------------------------------------------------------
class TestApiKeyValid:
    """_test_llm_connectivity returns None (success) → task proceeds normally."""

    @patch("api.routes.survey._test_llm_connectivity", return_value=None)
    @patch("api.routes.survey._resolve_credential", return_value="sk-valid-key")
    def test_valid_key_returns_200(self, mock_resolve, mock_test):
        """密钥校验通过返回 200 并正常创建任务."""
        response = client.post("/api/survey", json={
            "topic": "Transformer Models",
            "keywords": "attention, BERT",
            "goal": "Survey",
            "max_papers": 20,
        })
        # 校验通过后进入正常流程，返回 200
        assert response.status_code == 200
        data = response.json()
        # 正常流水线响应应包含 topic
        assert data.get("topic") == "Transformer Models"

    @patch("api.routes.survey._test_llm_connectivity", return_value=None)
    @patch("api.routes.survey._resolve_credential", return_value="sk-valid-key")
    def test_valid_key_starts_task(self, mock_resolve, mock_test):
        """密钥校验通过后调用 harness.run_async 启动任务."""
        original_harness = app.dependency_overrides[survey_get_harness]()
        with patch.object(original_harness, "run_async") as mock_run:
            # 让 run_async 实际调用，否则 get_task_info 返回空数据
            # 这里我们只验证 run_async 被调用，不验证返回值
            def _fake_run(**kwargs):
                original_harness._task_info = {
                    "topic": "Transformer Models",
                    "status": "PLANNING",
                    "pipeline_running": True,
                    "current_stage": "starting",
                    "current_message": "",
                    "retry_count": 0,
                    "has_warnings": False,
                }
            mock_run.side_effect = _fake_run
            app.dependency_overrides[survey_get_harness] = lambda: original_harness
            response = client.post("/api/survey", json={
                "topic": "Transformer Models",
                "keywords": "attention, BERT",
                "goal": "Survey",
                "max_papers": 20,
            })
            assert response.status_code == 200
            mock_run.assert_called_once()
