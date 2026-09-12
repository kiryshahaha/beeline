"""Ticket SQL queries. Transaction boundaries are owned by the service."""

from sqlalchemy import select
from sqlalchemy.orm import Session

# Import the registry so all foreign key targets are available even on the first POST.
from app.db.models import Building, City, Entrance, Location, Street, Ticket

TicketDetails = tuple[Ticket, Location, Building, Street, City, Entrance | None]


def find_location(session: Session, location_id: int) -> Location | None:
    # Keep this location from being deleted while its ticket is being inserted.
    return session.scalar(
        select(Location)
        .where(Location.id == location_id)
        .with_for_update(read=True, key_share=True)
    )


def add_ticket(session: Session, ticket: Ticket) -> None:
    session.add(ticket)
    session.flush()


def find_ticket(session: Session, ticket_id: int) -> TicketDetails | None:
    return (
        session.execute(
            select(Ticket, Location, Building, Street, City, Entrance)
            .join(Location, Location.id == Ticket.location_id)
            .join(Building, Building.id == Location.building_id)
            .join(Street, Street.id == Building.street_id)
            .join(City, City.id == Street.city_id)
            .outerjoin(Entrance, Entrance.id == Location.entrance_id)
            .where(Ticket.id == ticket_id)
        )
        .tuples()
        .one_or_none()
    )
