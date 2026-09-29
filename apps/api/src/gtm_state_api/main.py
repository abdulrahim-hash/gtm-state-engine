"""FastAPI application factory."""

from fastapi import FastAPI

from gtm_state_api import __version__
from gtm_state_api.config import get_settings
from gtm_state_api.health import router as health_router


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
    return application


app = create_app()
