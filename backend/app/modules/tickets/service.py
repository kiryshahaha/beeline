"""Create and retrieve tickets without HTTP-specific exceptions."""

from sqlalchemy.orm import Session

from app.modules.locations.schemas import LocationRead
from app.modules.tickets import repository
from app.modules.tickets.models import Ticket
from app.modules.tickets.schemas import TicketCreate, TicketFields, TicketRead


class LocationNotFoundError(Exception):
    pass


class TicketNotFoundError(Exception):
    pass


def get_ticket(session: Session, ticket_id: int) -> TicketRead:
    details = repository.find_ticket(session, ticket_id)
    if details is None:
        raise TicketNotFoundError
    ticket, location, building, street, city, entrance = details
    return TicketRead(
        **TicketFields.model_validate(ticket).model_dump(),
        id=ticket.id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        location=LocationRead(
            id=location.id,
            city_id=city.id,
            city=city.name,
            street_id=street.id,
            street=street.name,
            building_id=building.id,
            building_number=building.number,
            block=building.block,
            entrance_id=location.entrance_id,
            entrance_number=entrance.number if entrance is not None else None,
            floor=location.floor,
            apartment=location.apartment,
            latitude=location.latitude,
            longitude=location.longitude,
        ),
    )


def create_ticket(session: Session, data: TicketCreate) -> TicketRead:
    with session.begin():
        if repository.find_location(session, data.location_id) is None:
            raise LocationNotFoundError
        ticket = Ticket(**data.model_dump())
        repository.add_ticket(session, ticket)
        # Build the response inside the transaction; a failed operation leaves no ticket.
        return get_ticket(session, ticket.id)
