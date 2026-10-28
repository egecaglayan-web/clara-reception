import hmac
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.models import DeliveryReview, Incoming
from app.service import Service

logger = logging.getLogger(__name__)


def create_app(config=None, service=None, schedule=True):
    config = config or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        engine = service or Service(config)
        app.state.service = engine
        if config.demo:
            logger.warning("DEMO_MODE active: no external services; synthetic data only")
        scheduler = BackgroundScheduler(timezone=config.timezone)
        if schedule:
            scheduler.add_job(engine.poll, "interval", seconds=config.poll_seconds,
                              max_instances=1, coalesce=True, id="inbox")
            scheduler.start()
        try:
            yield
        finally:
            if schedule:
                scheduler.shutdown(wait=True)
            if service is None:
                engine.close()

    app = FastAPI(title="Clara Reception", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def authorize(x_admin_token: str = Header(default="")):
        if not config.admin_token:
            raise HTTPException(503, "Set ADMIN_TOKEN.")
        if not hmac.compare_digest(x_admin_token.encode(), config.admin_token.encode()):
            raise HTTPException(401, "Unauthorized request.")

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        # Enforce a hard limit on the stream even if Content-Length is missing or wrong.
        total = 0
        chunks = []
        async for chunk in request.stream():
            total += len(chunk)
            if total > 65536:
                return JSONResponse({"detail": "Request exceeds the size limit."}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        return await call_next(request)

    @app.get("/health", dependencies=[Depends(authorize)])
    def health():
        return {"status": "ok", "demo": config.demo}

    @app.get("/admin/status", dependencies=[Depends(authorize)])
    def status():
        return app.state.service.status()

    @app.get("/admin/deliveries", dependencies=[Depends(authorize)])
    def deliveries():
        return app.state.service.deliveries_for_review()

    @app.post("/admin/deliveries/{reference}/resolve", dependencies=[Depends(authorize)])
    def resolve(reference: str, review: DeliveryReview):
        if not app.state.service.resolve_delivery(reference, review.decision):
            raise HTTPException(409, "No uncertain delivery found.")
        return {"resolved": True, "decision": review.decision}

    @app.post("/admin/poll", dependencies=[Depends(authorize)])
    def poll():
        app.state.service.poll()
        return app.state.service.status()

    @app.post("/demo/email", dependencies=[Depends(authorize)])
    def demo_email(message: Incoming):
        if not config.demo:
            raise HTTPException(404, "Demo is disabled.")
        engine = app.state.service
        previous = engine.store.get("messages", engine._link_key(message.sender, message.message_id))
        engine.inbox.add(message)
        engine.poll()
        # Calling process again only reads the stored result; side effects are not repeated.
        result = engine.process(message)
        return {**result, "duplicate": bool(previous), "demo": True}

    return app


app = create_app()
