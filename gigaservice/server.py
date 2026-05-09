from fastapi import FastAPI
import uvicorn
from middleware import register_middleware
from api import router as api_router

app = FastAPI(title="GigaService", version="0.1.0")
register_middleware(app)
app.include_router(api_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "gigaservice"}


@app.get("/health")
def health():
    return {"healthy": True}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
