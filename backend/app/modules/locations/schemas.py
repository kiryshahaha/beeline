"""Address representation assembled from the normalized directory for API responses."""

from pydantic import BaseModel, computed_field


class LocationRead(BaseModel):
    id: int
    city_id: int
    city: str
    street_id: int
    street: str
    building_id: int
    building_number: str
    block: str | None
    entrance_id: int | None
    entrance_number: str | None
    floor: int | None
    apartment: str | None
    latitude: float | None
    longitude: float | None

    @computed_field
    @property
    def address(self) -> str:
        """A display string; the database still stores separate directory references."""
        parts = [self.city, self.street, f"д. {self.building_number}"]
        if self.block is not None:
            parts.append(self.block)
        if self.entrance_number is not None:
            parts.append(f"подъезд {self.entrance_number}")
        if self.floor is not None:
            parts.append(f"этаж {self.floor}")
        if self.apartment is not None:
            parts.append(f"кв./пом. {self.apartment}")
        return ", ".join(parts)
