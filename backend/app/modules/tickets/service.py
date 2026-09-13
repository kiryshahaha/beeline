"""Create and retrieve tickets without HTTP-specific exceptions."""

from sqlalchemy.orm import Session

from app.modules.locations.schemas import LocationRead
from app.modules.tickets import repository
from app.modules.tickets.schemas import TicketCreate, TicketFields, TicketRead


class LocationNotFoundError(Exception):
    pass


class TicketNotFoundError(Exception):
    pass


def get_ticket(session: Session, ticket_id: int) -> TicketRead:
    details = repository.find_ticket(session, ticket_id)
    if details is None:
        raise TicketNotFoundError
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
