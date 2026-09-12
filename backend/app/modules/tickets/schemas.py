"""Ticket request/response contracts; validation mirrors the agreed database constraints."""

from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.modules.locations.schemas import LocationRead
from app.modules.tickets.enums import TicketStatus

PositiveInt32 = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
NonNegativeInt32 = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]


class TicketFields(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    location_id: PositiveInt32
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: str | None = None
    work_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    status: TicketStatus = TicketStatus.PLANNED
    visit_window_start: AwareDatetime
    visit_window_end: AwareDatetime
    planned_start_at: AwareDatetime | None = None
    planned_end_at: AwareDatetime | None = None
    estimated_duration_minutes: PositiveInt32
    actual_duration_minutes: NonNegativeInt32 | None = None

    @field_validator("title", "description", "work_type")
    @classmethod
    def reject_null_character(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("Текст не может содержать нулевой символ")
        return value

    @model_validator(mode="after")
    def validate_intervals(self) -> Self:
        if self.visit_window_end <= self.visit_window_start:
            raise ValueError("Конец окна визита должен быть позже начала")
        if (self.planned_start_at is None) != (self.planned_end_at is None):
            raise ValueError("Плановые начало и окончание нужно передавать вместе")
        if (
            self.planned_start_at is not None
            and self.planned_end_at is not None
            and self.planned_end_at <= self.planned_start_at
        ):
            raise ValueError("Плановое окончание должно быть позже начала")
        return self


class TicketCreate(TicketFields):
    model_config = ConfigDict(extra="forbid")


class TicketRead(TicketFields):
    id: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    location: LocationRead
