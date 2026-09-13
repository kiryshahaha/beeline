"""Ticket creation, filtered listing and retrieval by ID."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.tickets import service
from app.modules.tickets.enums import TicketStatus
from app.modules.tickets.schemas import TicketCreate, TicketRead

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[TicketRead])
def list_tickets(
    session: DatabaseSession,
    status: Annotated[TicketStatus | None, Query(description="Фильтр по статусу заявки.")] = None,
    city_id: Annotated[
        int | None, Query(ge=1, le=2_147_483_647, description="ID города места выполнения.")
    ] = None,
    district_id: Annotated[
        int | None, Query(ge=1, le=2_147_483_647, description="ID района места выполнения.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Максимум заявок в ответе.")] = 20,
    offset: Annotated[
        int, Query(ge=0, le=2_147_483_647, description="Сколько подходящих заявок пропустить.")
    ] = 0,
) -> list[TicketRead]:
    """Получить список заявок с полными адресами по возрастанию ID.

    Фильтры необязательны и объединяются через AND. Пагинация применяется
    после фильтрации. Если совпадений нет, возвращается пустой массив.
    """
    return service.list_tickets(
        session, status=status, city_id=city_id, district_id=district_id, limit=limit, offset=offset
    )


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(data: TicketCreate, session: DatabaseSession, response: Response) -> TicketRead:
    """Создать заявку на существующее место выполнения из адресного справочника."""
    try:
        ticket = service.create_ticket(session, data)
    except service.LocationNotFoundError as error:
        raise HTTPException(status_code=422, detail="Место выполнения не найдено") from error
    response.headers["Location"] = f"/api/v1/tickets/{ticket.id}"
    return ticket


@router.get(
    "/{id}", response_model=TicketRead, responses={404: {"description": "Заявка не найдена"}}
)
def get_ticket(
    id: Annotated[int, Path(ge=1, le=2_147_483_647)],
    session: DatabaseSession,
) -> TicketRead:
    """Получить одну заявку вместе с адресом и координатами места выполнения."""
    try:
        return service.get_ticket(session, id)
    except service.TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Заявка не найдена") from error
