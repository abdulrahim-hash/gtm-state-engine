"""FastAPI application factory."""

from fastapi import FastAPI

from gtm_state_api import __version__
from gtm_state_api.config import get_settings
from gtm_state_api.decision_api import router as decision_router
from gtm_state_api.health import router as health_router
from gtm_state_api.read_api import router as read_router
from gtm_state_api.signals_api import router as signals_router
from gtm_state_api.state_api import router as state_router


def create_app() -> FastAPI:
    """Build the API with environment-appropriate documentation exposure."""

    settings = get_settings()
    public_docs = settings.app_env != "production"
    application = FastAPI(
        title="GTM State & Signal Engine API",
        summary="Typed service boundary for evidence-backed GTM decisions.",
        version=__version__,
        docs_url="/docs" if public_docs else None,
        redoc_url="/redoc" if public_docs else None,
        openapi_url="/openapi.json" if public_docs else None,
    )
    application.include_router(health_router)
    application.include_router(read_router)
    application.include_router(signals_router)
    application.include_router(state_router)
    application.include_router(decision_router)
    return application


app = create_app()
