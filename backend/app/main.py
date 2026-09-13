"""FastAPI entry point and module router registration."""

from fastapi import FastAPI

from app.modules.locations.router import router as locations_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.schemas import (
    LOGIN_REQUEST_EXAMPLE,
    REFRESH_TOKEN_REQUEST_EXAMPLE,
    TOKEN_RESPONSE_EXAMPLE,
)
from app.modules.tickets.router import router as tickets_router
from app.modules.tickets.schemas import TICKET_CREATE_EXAMPLE, TICKET_READ_EXAMPLE
from app.modules.users.router import router as users_router, skills_router
from app.modules.users.schemas import (
    USER_CREATE_OBSERVER_EXAMPLE,
    USER_CREATE_WORKER_EXAMPLE,
    USER_READ_OBSERVER_EXAMPLE,
    USER_READ_WORKER_EXAMPLE,
    USER_UPDATE_EXAMPLE,
    WORKER_SKILL_CREATE_EXAMPLE,
    WORKER_SKILL_EXAMPLE,
)

app = FastAPI(
    title="Планирование выездных работ",
    description="Основа сервиса: заявки, адресный справочник, пользователи и авторизация.",
    version="0.2.0",
)

app.include_router(locations_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(skills_router)
app.include_router(tickets_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness only: this endpoint does not check database readiness."""
    return {"status": "ok"}


default_openapi = app.openapi


def openapi_with_examples() -> dict:
    schema = default_openapi()
    # FastAPI removes None recursively while generating OpenAPI. Restore the examples
    # afterwards so Swagger shows nullable response fields and unset manual duration.
    schemas = schema["components"]["schemas"]
    schemas["TicketCreate"]["examples"] = [TICKET_CREATE_EXAMPLE]
    schemas["TicketRead"]["examples"] = [TICKET_READ_EXAMPLE]

    if "UserCreate" in schemas:
        schemas["UserCreate"]["examples"] = [
            USER_CREATE_WORKER_EXAMPLE,
            USER_CREATE_OBSERVER_EXAMPLE,
        ]
    if "UserUpdate" in schemas:
        schemas["UserUpdate"]["examples"] = [USER_UPDATE_EXAMPLE]
    if "UserRead" in schemas:
        schemas["UserRead"]["examples"] = [
            USER_READ_WORKER_EXAMPLE,
            USER_READ_OBSERVER_EXAMPLE,
        ]
    if "WorkerSkillCreate" in schemas:
        schemas["WorkerSkillCreate"]["examples"] = [WORKER_SKILL_CREATE_EXAMPLE]
    if "WorkerSkillRead" in schemas:
        schemas["WorkerSkillRead"]["examples"] = [WORKER_SKILL_EXAMPLE]
    if "LoginRequest" in schemas:
        schemas["LoginRequest"]["examples"] = [LOGIN_REQUEST_EXAMPLE]
    if "RefreshTokenRequest" in schemas:
        schemas["RefreshTokenRequest"]["examples"] = [REFRESH_TOKEN_REQUEST_EXAMPLE]
    if "TokenResponse" in schemas:
        schemas["TokenResponse"]["examples"] = [TOKEN_RESPONSE_EXAMPLE]

    return schema


app.openapi = openapi_with_examples
