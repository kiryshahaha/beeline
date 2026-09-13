"""Create, update and retrieve tickets without HTTP-specific exceptions."""

import json
from sqlalchemy import RowMapping
from sqlalchemy.orm import Session

from app.modules.locations.schemas import LocationRead
from app.modules.tickets import repository
from app.modules.tickets.enums import TicketStatus
from app.modules.tickets.schemas import (
    TicketAssigneeRead,
    TicketCreate,
    TicketFields,
    TicketRead,
    TicketUpdate,
    TicketUserRead,
)
from app.modules.users.enums import UserRole


class LocationNotFoundError(Exception):
    pass


class TicketNotFoundError(Exception):
    pass


class WorkerNotFoundError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


def get_ticket(session: Session, ticket_id: int) -> TicketRead:
    details = repository.find_ticket(session, ticket_id)
    if details is None:
        raise TicketNotFoundError
    return _ticket_from_row(details)


def list_tickets(
    session: Session,
    *,
    status: TicketStatus | None = None,
    city_id: int | None = None,
    district_id: int | None = None,
    worker_id: int | None = None,
    unassigned: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[TicketRead]:
    rows = repository.find_tickets(
        session,
        status=status.value if status is not None else None,
        city_id=city_id,
        district_id=district_id,
        worker_id=worker_id,
        unassigned=unassigned,
        limit=limit,
        offset=offset,
    )
    return [_ticket_from_row(row) for row in rows]


def _ticket_from_row(details: RowMapping) -> TicketRead:
    """Build the same full response from either a single row or a row in a page."""
    created_by = None
    if details["created_by_id"] is not None and details["creator_name"] is not None:
        created_by = TicketUserRead(
            id=details["created_by_id"],
            name=details["creator_name"],
            surname=details["creator_surname"],
            lastname=details["creator_lastname"],
            username=details["creator_username"],
            role=UserRole(details["creator_role"]),
        )

    raw_assignees = details["assignees"]
    if isinstance(raw_assignees, str):
        raw_assignees = json.loads(raw_assignees)
    elif raw_assignees is None:
        raw_assignees = []

    assignees = [
        TicketAssigneeRead.model_validate(assignee_data)
        for assignee_data in raw_assignees
    ]

    return TicketRead(
        **TicketFields.model_validate(details).model_dump(),
        id=details["id"],
        created_by_id=details["created_by_id"],
        created_by=created_by,
        assignees=assignees,
        created_at=details["created_at"],
        updated_at=details["updated_at"],
        location=LocationRead(
            id=details["location_id"],
            city_id=details["city_id"],
            city=details["city"],
            district_id=details["district_id"],
            district=details["district"],
            street_id=details["street_id"],
            street=details["street"],
            building_id=details["building_id"],
            building_number=details["building_number"],
            block=details["block"],
            entrance_id=details["entrance_id"],
            entrance_number=details["entrance_number"],
            floor=details["floor"],
            apartment=details["apartment"],
            latitude=details["latitude"],
            longitude=details["longitude"],
        ),
    )


def create_ticket(
    session: Session,
    data: TicketCreate,
    created_by_id: int | None = None,
) -> TicketRead:
    with session.begin():
        if repository.find_location_id(session, data.location_id) is None:
            raise LocationNotFoundError
        if data.worker_ids:
            valid_worker_ids = set(repository.validate_worker_ids(session, data.worker_ids))
            invalid_ids = set(data.worker_ids) - valid_worker_ids
            if invalid_ids:
                raise WorkerNotFoundError(f"Исполнители с ID {sorted(invalid_ids)} не найдены")

        values = data.model_dump(exclude={"worker_ids"})
        values["status"] = data.status.value
        values["created_by_id"] = created_by_id
        ticket_id = repository.add_ticket(session, values)

        if data.worker_ids:
            repository.set_ticket_assignees(session, ticket_id, data.worker_ids)

        # Build the response inside the transaction; a failed operation leaves no ticket.
        return get_ticket(session, ticket_id)


def update_ticket(
    session: Session,
    ticket_id: int,
    data: TicketUpdate,
    current_user_role: str | None = None,
    current_user_id: int | None = None,
) -> TicketRead:
    with session.begin():
        existing = repository.find_ticket(session, ticket_id)
        if existing is None:
            raise TicketNotFoundError

        # If current user is a worker, enforce role permissions
        if current_user_role == UserRole.WORKER.value:
            raw_assignees = existing["assignees"]
            if isinstance(raw_assignees, str):
                raw_assignees = json.loads(raw_assignees)
            elif raw_assignees is None:
                raw_assignees = []
            assignee_ids = [a["id"] for a in raw_assignees]

            if current_user_id not in assignee_ids:
                raise PermissionDeniedError("Вы не назначены на эту заявку")
            if data.worker_ids is not None:
                raise PermissionDeniedError("Исполнитель не может изменять состав исполнителей")
            if (
                data.title is not None
                or data.description is not None
                or data.work_type is not None
                or data.visit_window_start is not None
                or data.visit_window_end is not None
                or data.planned_start_at is not None
                or data.planned_end_at is not None
                or data.estimated_duration_minutes is not None
            ):
                raise PermissionDeniedError(
                    "Исполнитель может изменять только статус и фактическую длительность"
                )

        if data.worker_ids is not None:
            if data.worker_ids:
                valid_worker_ids = set(repository.validate_worker_ids(session, data.worker_ids))
                invalid_ids = set(data.worker_ids) - valid_worker_ids
                if invalid_ids:
                    raise WorkerNotFoundError(f"Исполнители с ID {sorted(invalid_ids)} не найдены")
            repository.set_ticket_assignees(session, ticket_id, data.worker_ids)

        update_values = data.model_dump(exclude_unset=True, exclude={"worker_ids"})
        if "status" in update_values and update_values["status"] is not None:
            update_values["status"] = data.status.value

        if update_values:
            repository.update_ticket(session, ticket_id, update_values)

        return get_ticket(session, ticket_id)


def assign_workers(session: Session, ticket_id: int, worker_ids: list[int]) -> TicketRead:
    with session.begin():
        existing = repository.find_ticket(session, ticket_id)
        if existing is None:
            raise TicketNotFoundError
        if worker_ids:
            valid_worker_ids = set(repository.validate_worker_ids(session, worker_ids))
            invalid_ids = set(worker_ids) - valid_worker_ids
            if invalid_ids:
                raise WorkerNotFoundError(f"Исполнители с ID {sorted(invalid_ids)} не найдены")
        repository.set_ticket_assignees(session, ticket_id, worker_ids)
        return get_ticket(session, ticket_id)
