from fastapi import FastAPI

app = FastAPI(title="AI RAG Assistant")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
