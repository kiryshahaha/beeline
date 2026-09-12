"""FastAPI entry point and module router registration."""

from fastapi import FastAPI

from app.modules.tickets.router import router as tickets_router

app = FastAPI(
    title="Планирование выездных работ",
    description="Основа сервиса: заявки и адресный справочник.",
    version="0.1.0",
)

app.include_router(tickets_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness only: this endpoint does not check database readiness."""
    return {"status": "ok"}
