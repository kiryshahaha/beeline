"""FastAPI entry point. Business routers are added in the next implementation step."""

from fastapi import FastAPI

app = FastAPI(
    title="Планирование выездных работ",
    description="Основа сервиса: заявки и адресный справочник.",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness only: this endpoint does not check database readiness."""
    return {"status": "ok"}
