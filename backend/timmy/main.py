from contextlib import asynccontextmanager
import asyncio
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .observability import reference, Telemetry, router as telemetry_router, current, parent, overview_data
from sqlalchemy.orm import Session
from .auth import current_principal, Authenticated, Database
import re

from .workflow_payments import router as workflow_payments_router
from .global_mappings import router as global_mappings_router
from .reporting_register import router as reporting_register_router
from .payment_configuration import router as payment_policy_router
from .demo_operations import router as demo_router
from .config import Settings, settings
from .database import make_engine
from .documents import router as document_router
from .routes import router
from .voice import router as voice_router
from .workspace import AuthLimit, router as workspace_router
from .operations import router as operations_router
from .chat_activity import ChatActivity
from .chat_routes import router as chat_router
from .workflows import router as workflow_router
from .workflow_scheduler import scheduler_loop


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = make_engine(config.database_url)
        activity = app.state.chat_activity = ChatActivity()
        telemetry = app.state.telemetry = Telemetry(app.state.engine, config)
        telemetry.task = asyncio.create_task(telemetry.loop()) if config.telemetry_enabled else None
        scheduler = asyncio.create_task(scheduler_loop(app.state.engine, config, telemetry)) if config.weekly_enabled else None
        try:
            yield
        finally:
            if scheduler:
                scheduler.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduler
            if telemetry.task:
                telemetry.task.cancel()
                with suppress(asyncio.CancelledError):
                    await telemetry.task
            telemetry.flush()
            if telemetry.engine is not None:
                telemetry.engine.dispose()
            app.state.engine.dispose()
            for handler in activity.logger.handlers:
                handler.close()

    app = FastAPI(title="Agent Timmy", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.config = config
    app.state.auth_limit = AuthLimit()
    app.add_middleware(
        CORSMiddleware, allow_origins=[config.frontend_origin], allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT"], allow_headers=["Content-Type", "X-CSRF-Token", "Last-Event-ID"],
        expose_headers=["X-Execution-ID"],
    )

    @app.middleware("http")
    async def trace_operations(request: Request, call_next):
        path = request.url.path
        tracked = request.method in {"POST", "PUT", "PATCH", "DELETE"} and any(
            path.startswith('/api/' + area) for area in ('chat/', 'documents', 'workflows', 'operations', 'projects', 'workspace/projects', 'workspace/activities', 'reporting-register', 'global-mappings', 'workflow-payments'))
        trace = None
        if tracked and config.telemetry_enabled:
            try:
                with Session(request.app.state.engine) as db:
                    actor = current_principal(request, db)
                    actor.require('projects:read')
                    # Conservative scope: recheck all assignments that could contribute
                    # to global document/project tools, including after revocation.
                    scopes = [pid for pid, grants in actor.project_permissions.items() if 'projects:read' in grants]
                    match = re.search(r'/conversations/([0-9a-f-]{36})', path)
                    area = path.split('/')[2]
                    trace = request.app.state.telemetry.start(actor.user.id,
                        request.method + ' ' + area, scopes, match.group(1) if match else None)
                if trace:
                    trace.info['access_grants'] = {str(pid): grants for pid, grants in actor.project_permissions.items() if pid in scopes}
                    request.app.state.telemetry.flush()
            except Exception:
                pass  # The original endpoint remains the permission authority.
        token = current.set(trace)
        parent_token = parent.set(trace.root if trace else None)
        try:
            if trace:
                from .instruction_pack import DIGEST
                reference('approved-action-pack', 'available', DIGEST)
            response = await call_next(request)
            if trace:
                trace.emit('http.result', parent_id=trace.root,
                           status='failed' if response.status_code >= 400 else 'completed',
                           http_status=response.status_code, category='response', operation='HTTP response')
                trace.finish('failed' if response.status_code >= 400 else 'completed')
                response.headers['X-Execution-ID'] = trace.info['id']
            return response
        except BaseException:
            if trace:
                trace.finish('failed')
            raise
        finally:
            parent.reset(parent_token)
            current.reset(token)

    @app.middleware("http")
    async def disable_caching(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError):
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    @app.get('/api/overview')
    def overview(principal: Authenticated, db: Database):
        return overview_data(principal, db)

    app.include_router(workflow_payments_router)
    app.include_router(global_mappings_router)
    app.include_router(reporting_register_router)
    app.include_router(telemetry_router)
    app.include_router(router)
    app.include_router(document_router)
    app.include_router(voice_router)
    app.include_router(operations_router)
    app.include_router(chat_router)
    app.include_router(workflow_router)
    app.include_router(workspace_router)
    app.include_router(payment_policy_router)
    app.include_router(demo_router)
    return app


app = create_app()
