"""Explicit model registry for Alembic; domain modules do not import one another."""

from app.modules.buildings.models import Building
from app.modules.cities.models import City
from app.modules.districts.models import District
from app.modules.entrances.models import Entrance
from app.modules.locations.models import Location
from app.modules.streets.models import Street
from app.modules.tickets.models import Ticket

__all__ = ["Building", "City", "District", "Entrance", "Location", "Street", "Ticket"]
