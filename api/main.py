from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent.core.llm import OpenAILLM, MockLLM
from agent.core.harness import Harness, HarnessConfig
from api.routes import survey, feedback, progress, memory, credentials, history
from api.routes.credentials import _resolve_credential
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

app = FastAPI(title="ScholarAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy init: use OpenAILLM if API key is set, otherwise fall back to MockLLM
# Use _resolve_credential to check all sources (keyring > process env > .env)
_api_key = _resolve_credential("LLM_API_KEY") or ""
if not _api_key:
    print(
        "\n" + "=" * 60,
        "\n  ⚠️  LLM_API_KEY 未配置",
        "\n",
        "\n  请通过以下方式之一配置 API Key：",
        "\n",
        "\n  ① 启动 Web 前端，进入 Credentials 页面录入",
        "\n     （推荐，加密存储至操作系统凭据管理器）",
        "\n",
        "\n  ② 启动后端后访问 FastAPI 文档页面在线配置",
        "\n     http://localhost:8000/docs → PUT /api/credentials",
        "\n",
        "\n  ③ 编辑项目根目录 .env 文件（明文，仅建议开发环境）",
        "\n",
        "\n" + "=" * 60,
    )
if _api_key:
    _llm = OpenAILLM(api_key=_api_key)
else:
    _llm = MockLLM(fixed_response="Mock fallback – no LLM_API_KEY set")

_harness = Harness(config=HarnessConfig(), llm=_llm)

# Store LLM reference in app.state so routes can update the API key at runtime
app.state.llm = _llm

app.include_router(survey.router)
app.include_router(feedback.router)
app.include_router(progress.router)
app.include_router(memory.router)
app.include_router(credentials.router)
app.include_router(history.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
