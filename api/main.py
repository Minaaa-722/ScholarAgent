from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent.core.llm import OpenAILLM, MockLLM
from agent.core.harness import Harness, HarnessConfig
from api.routes import survey, feedback, progress, memory
import os

app = FastAPI(title="ScholarAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy init: use OpenAILLM if API key is set, otherwise fall back to MockLLM
_api_key = os.getenv("LLM_API_KEY", "")
if _api_key:
    _llm = OpenAILLM(api_key=_api_key)
else:
    _llm = MockLLM(fixed_response="Mock fallback – no LLM_API_KEY set")

_harness = Harness(config=HarnessConfig(), llm=_llm)

app.include_router(survey.router)
app.include_router(feedback.router)
app.include_router(progress.router)
app.include_router(memory.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}