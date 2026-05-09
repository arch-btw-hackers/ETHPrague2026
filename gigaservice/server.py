from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import storage.swarm as swarm_store
from api import router as api_router
from middleware import register_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the shared HTTP client on startup; close it on shutdown."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        swarm_store.set_http_client(client)
        yield


app = FastAPI(title="GigaService", version="0.1.0", lifespan=lifespan)
register_middleware(app)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Global error handlers — convert Swarm network failures to 503
# ---------------------------------------------------------------------------

@app.exception_handler(httpx.RequestError)
async def swarm_request_error_handler(request: Request, exc: httpx.RequestError):
    return JSONResponse(status_code=503, content={"detail": "Swarm storage unavailable"})


@app.exception_handler(httpx.HTTPStatusError)
async def swarm_http_error_handler(request: Request, exc: httpx.HTTPStatusError):
    return JSONResponse(status_code=503, content={"detail": "Swarm storage unavailable"})


@app.get("/")
def root():
    return {"status": "ok", "service": "gigaservice"}


@app.get("/health")
def health():
    return {"healthy": True}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
