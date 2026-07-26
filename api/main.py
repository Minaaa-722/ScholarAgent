from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent.core.llm import OpenAILLM
from agent.core.harness import Harness, HarnessConfig
from api.routes import survey, feedback, progress, memory

app = FastAPI(title="ScholarAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_harness = Harness(config=HarnessConfig(), llm=OpenAILLM(api_key=""))

app.include_router(survey.router)
app.include_router(feedback.router)
app.include_router(progress.router)
app.include_router(memory.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}