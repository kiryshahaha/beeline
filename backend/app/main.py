"""FastAPI entry point and module router registration."""

from fastapi import FastAPI

from app.modules.locations.router import router as locations_router
from app.modules.tickets.router import router as tickets_router
from app.modules.tickets.schemas import TICKET_CREATE_EXAMPLE, TICKET_READ_EXAMPLE

app = FastAPI(
    title="Планирование выездных работ",
    description="Основа сервиса: заявки и адресный справочник.",
    version="0.1.0",
)

app.include_router(locations_router)
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
    return schema


app.openapi = openapi_with_examples
