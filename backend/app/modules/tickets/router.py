"""Ticket creation, filtered listing, retrieval, update, and worker assignment."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import get_optional_current_user
from app.modules.tickets import service
from app.modules.tickets.enums import TicketStatus
from app.modules.tickets.schemas import (
    TicketAssignWorkersRequest,
    TicketCreate,
    TicketRead,
    TicketUpdate,
)
from app.modules.users.enums import UserRole
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])
DatabaseSession = Annotated[Session, Depends(get_session)]
OptionalUser = Annotated[UserRead | None, Depends(get_optional_current_user)]


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
    worker_id: Annotated[
        int | None, Query(ge=1, le=2_147_483_647, description="ID назначенного исполнителя.")
    ] = None,
    unassigned: Annotated[
        bool | None,
        Query(
            description="true — только неназначенные заявки, false — только заявки с исполнителями."
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Максимум заявок в ответе.")] = 20,
    offset: Annotated[
        int, Query(ge=0, le=2_147_483_647, description="Сколько подходящих заявок пропустить.")
    ] = 0,
) -> list[TicketRead]:
    """Получить список заявок с полными адресами и назначенными исполнителями по возрастанию ID.

    Фильтры необязательны и объединяются через AND. Пагинация применяется
    после фильтрации. Если совпадений нет, возвращается пустой массив.
    """
    return service.list_tickets(
        session,
        status=status,
        city_id=city_id,
        district_id=district_id,
        worker_id=worker_id,
        unassigned=unassigned,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketCreate,
    session: DatabaseSession,
    response: Response,
    current_user: OptionalUser = None,
) -> TicketRead:
    """Создать заявку на существующее место выполнения из адресного справочника."""
    if current_user is not None and current_user.role == UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Исполнитель не может создавать заявки",
        )
    created_by_id = current_user.id if current_user is not None else None
    try:
        ticket = service.create_ticket(session, data, created_by_id=created_by_id)
    except service.LocationNotFoundError as error:
        raise HTTPException(status_code=422, detail="Место выполнения не найдено") from error
    except service.WorkerNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    response.headers["Location"] = f"/api/v1/tickets/{ticket.id}"
    return ticket


@router.get(
    "/{id}", response_model=TicketRead, responses={404: {"description": "Заявка не найдена"}}
)
def get_ticket(
    id: Annotated[int, Path(ge=1, le=2_147_483_647)],
    session: DatabaseSession,
) -> TicketRead:
    """Получить одну заявку вместе с адресом, координатами, создателем и исполнителями."""
    try:
        return service.get_ticket(session, id)
    except service.TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Заявка не найдена") from error


@router.patch(
    "/{id}",
    response_model=TicketRead,
    responses={
        404: {"description": "Заявка не найдена"},
        403: {"description": "Недостаточно прав для изменения заявки"},
        422: {"description": "Ошибка валидации данных или исполнителя"},
    },
)
def update_ticket(
    id: Annotated[int, Path(ge=1, le=2_147_483_647)],
    data: TicketUpdate,
    session: DatabaseSession,
    current_user: OptionalUser = None,
) -> TicketRead:
    """Обновить параметры заявки, список назначенных исполнителей или статус."""
    user_role = current_user.role.value if current_user is not None else None
    user_id = current_user.id if current_user is not None else None
    try:
        return service.update_ticket(
            session,
            id,
            data,
            current_user_role=user_role,
            current_user_id=user_id,
        )
    except service.TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Заявка не найдена") from error
    except service.WorkerNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except service.PermissionDeniedError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post(
    "/{id}/assign",
    response_model=TicketRead,
    responses={
        404: {"description": "Заявка не найдена"},
        403: {"description": "Недостаточно прав для назначения исполнителей"},
        422: {"description": "Один или несколько исполнителей не найдены"},
    },
)
def assign_workers_to_ticket(
    id: Annotated[int, Path(ge=1, le=2_147_483_647)],
    data: TicketAssignWorkersRequest,
    session: DatabaseSession,
    current_user: OptionalUser = None,
) -> TicketRead:
    """Назначить (или изменить) список исполнителей заявки."""
    if current_user is not None and current_user.role == UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Исполнитель не может назначать специалистов на заявки",
        )
    try:
        return service.assign_workers(session, id, data.worker_ids)
    except service.TicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="Заявка не найдена") from error
    except service.WorkerNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
