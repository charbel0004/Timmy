from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .config import Settings, settings
from .database import make_engine
from .documents import router as document_router
from .routes import router
from .voice import router as voice_router
from .workspace import AuthLimit, router as workspace_router
from .operations import router as operations_router
from .chat_routes import router as chat_router


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = make_engine(config.database_url)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(title="Agent Timmy", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.config = config
    app.state.auth_limit = AuthLimit()
    app.add_middleware(
        CORSMiddleware, allow_origins=[config.frontend_origin], allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT"], allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def disable_caching(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError):
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    app.include_router(router)
    app.include_router(document_router)
    app.include_router(voice_router)
    app.include_router(operations_router)
    app.include_router(chat_router)
    app.include_router(workspace_router)
    return app


app = create_app()
