import logging.config

import dramatiq
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models
from .aws.util import xml_response
from .database import SessionLocal
from .routers import gateway, s3
from .settings import get_settings

app = FastAPI(title="exodus-gw")
app.include_router(gateway.router)
app.include_router(s3.router)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request, exc):
    # Override HTTPException to produce XML error responses for the
    # given endpoints.

    path = request.scope.get("path")

    if path.startswith("/upload"):
        return xml_response(
            "Error", Code=exc.status_code, Message=exc.detail, Endpoint=path
        )

    return await http_exception_handler(request, exc)


@app.on_event("startup")
def configure_loggers():
    settings = get_settings()
    logging.config.dictConfig(settings.log_config)

    root = logging.getLogger()
    if not root.hasHandlers():
        fmtr = logging.Formatter(
            fmt="[%(asctime)s] [%(process)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S %z",
        )
        hdlr = logging.StreamHandler()
        hdlr.setFormatter(fmtr)
        root.addHandler(hdlr)


@app.on_event("startup")
def db_init() -> None:
    models.Base.metadata.create_all(bind=SessionLocal().get_bind())


@app.middleware("http")
async def db_session(request: Request, call_next):
    """Maintain a DB session around each request, which is also shared
    with the dramatiq broker.

    An implicit commit occurs if and only if the request succeeds.
    """

    request.state.db = SessionLocal()

    # Any dramatiq operations should also make use of this session.
    broker = dramatiq.get_broker()
    broker.set_session(request.state.db)

    try:
        response = await call_next(request)
        if response.status_code >= 200 and response.status_code < 300:
            request.state.db.commit()
    finally:
        broker.set_session(None)
        request.state.db.close()
        request.state.db = None

    return response
