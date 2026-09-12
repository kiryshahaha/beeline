"""Only ticket creation and retrieval are exposed at this stage."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.tickets import service
from app.modules.tickets.schemas import TicketCreate, TicketRead

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])
DatabaseSession = Annotated[Session, Depends(get_session)]


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
