"""Create and retrieve tickets without HTTP-specific exceptions."""

from sqlalchemy import RowMapping
from sqlalchemy.orm import Session

from app.modules.locations.schemas import LocationRead
from app.modules.tickets import repository
from app.modules.tickets.enums import TicketStatus
from app.modules.tickets.schemas import TicketCreate, TicketFields, TicketRead


class LocationNotFoundError(Exception):
    pass


class TicketNotFoundError(Exception):
    pass


def get_ticket(session: Session, ticket_id: int) -> TicketRead:
    details = repository.find_ticket(session, ticket_id)
    if details is None:
        raise TicketNotFoundError
    return _ticket_from_row(details)


def list_tickets(
    session: Session,
    *,
    status: TicketStatus | None,
    city_id: int | None,
    district_id: int | None,
    limit: int,
    offset: int,
) -> list[TicketRead]:
    rows = repository.find_tickets(
        session,
        status=status.value if status is not None else None,
        city_id=city_id,
        district_id=district_id,
        limit=limit,
        offset=offset,
    )
    return [_ticket_from_row(row) for row in rows]


def _ticket_from_row(details: RowMapping) -> TicketRead:
    """Build the same full response from either a single row or a row in a page."""
    return TicketRead(
        **TicketFields.model_validate(details).model_dump(),
        id=details["id"],
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


def create_ticket(session: Session, data: TicketCreate) -> TicketRead:
    with session.begin():
        if repository.find_location_id(session, data.location_id) is None:
            raise LocationNotFoundError
        values = data.model_dump()
        values["status"] = data.status.value
        ticket_id = repository.add_ticket(session, values)
        # Build the response inside the transaction; a failed operation leaves no ticket.
        return get_ticket(session, ticket_id)
