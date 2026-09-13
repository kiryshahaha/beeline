"""Ticket request/response contracts; validation mirrors the agreed database constraints."""

from datetime import time
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
from app.modules.users.enums import UserRole

PositiveInt32 = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
NonNegativeInt32 = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]

# Documentation examples only. IDs must be replaced with values from the user's database.
TICKET_CREATE_EXAMPLE = {
    "location_id": 1,
    "title": "Настроить Wi-Fi",
    "description": "Учебный пример заявки",
    "work_type": "Настройка сети",
    "status": "planned",
    "visit_window_start": "2026-09-14T10:00:00+03:00",
    "visit_window_end": "2026-09-14T14:00:00+03:00",
    "planned_start_at": None,
    "planned_end_at": None,
    "estimated_duration_minutes": 60,
    "actual_duration_minutes": None,
    "worker_ids": [],
}

TICKET_UPDATE_EXAMPLE = {
    "status": "in_progress",
    "actual_duration_minutes": 50,
    "worker_ids": [2, 3],
}

TICKET_ASSIGN_WORKERS_EXAMPLE = {
    "worker_ids": [2, 3],
}

TICKET_READ_EXAMPLE = {
    "id": 1,
    "location_id": 1,
    "title": "Настроить Wi-Fi",
    "description": "Учебный пример заявки",
    "work_type": "Настройка сети",
    "status": "planned",
    "visit_window_start": "2026-09-14T10:00:00+03:00",
    "visit_window_end": "2026-09-14T14:00:00+03:00",
    "planned_start_at": None,
    "planned_end_at": None,
    "estimated_duration_minutes": 60,
    "actual_duration_minutes": None,
    "created_by_id": 1,
    "created_by": {
        "id": 1,
        "name": "Иван",
        "surname": "Иванов",
        "lastname": "Иванович",
        "username": "demo_observer",
        "role": "observer",
    },
    "assignees": [
        {
            "id": 2,
            "name": "Дмитрий",
            "surname": "Кузнецов",
        }
    ],
    "created_at": "2026-09-13T09:00:00+03:00",
    "updated_at": "2026-09-13T09:00:00+03:00",
    "location": {
        "id": 1,
        "city_id": 1,
        "city": "Санкт-Петербург",
        "district_id": 1,
        "district": "Невский район",
        "street_id": 1,
        "street": "Искровский проспект",
        "building_id": 1,
        "building_number": "4",
        "block": "корпус 2",
        "entrance_id": 1,
        "entrance_number": "1",
        "floor": 3,
        "apartment": "12",
        "latitude": 59.9156,
        "longitude": 30.4631,
        "address": (
            "Санкт-Петербург, Невский район, Искровский проспект, д. 4, корпус 2, "
            "подъезд 1, этаж 3, кв./пом. 12"
        ),
    },
}


class TicketUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    surname: str
    lastname: str | None = None
    username: str
    role: UserRole


class TicketAssigneeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    surname: str



class TicketFields(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    location_id: PositiveInt32 = Field(
        description="ID существующего места выполнения. В примере замените 1 на ID из вашей БД."
    )
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: str | None = None
    work_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    status: TicketStatus = Field(
        default=TicketStatus.PLANNED,
        description="planned — запланирована, in_progress — в работе, "
        "completed — завершена, wont_fix — не будет исправлено.",
    )
    visit_window_start: AwareDatetime = Field(
        description="Начало допустимого окна визита. Обязателен часовой пояс, например +03:00."
    )
    visit_window_end: AwareDatetime = Field(
        description="Конец допустимого окна визита, строго позже его начала."
    )
    planned_start_at: AwareDatetime | None = Field(
        default=None,
        description="Запланированное начало работы; null, если время ещё не назначено.",
    )
    planned_end_at: AwareDatetime | None = Field(
        default=None,
        description="Запланированное окончание, строго позже начала. "
        "Обе плановые даты заполняются вместе либо обе остаются null.",
    )
    estimated_duration_minutes: PositiveInt32 = Field(
        description="Ожидаемая длительность работы в минутах, больше нуля."
    )
    actual_duration_minutes: NonNegativeInt32 | None = Field(
        default=None,
        description="Фактическая длительность в минутах, введённая вручную. "
        "null — ещё не указана, 0 — явно введённые ноль минут.",
    )

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
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [TICKET_CREATE_EXAMPLE]}
    )

    worker_ids: list[PositiveInt32] = Field(
        default_factory=list,
        description="ID исполнителей, назначаемых на заявку при создании.",
    )


class TicketUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [TICKET_UPDATE_EXAMPLE]}
    )

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ] | None = None
    description: str | None = None
    work_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] | None = None
    status: TicketStatus | None = None
    visit_window_start: AwareDatetime | None = None
    visit_window_end: AwareDatetime | None = None
    planned_start_at: AwareDatetime | None = None
    planned_end_at: AwareDatetime | None = None
    estimated_duration_minutes: PositiveInt32 | None = None
    actual_duration_minutes: NonNegativeInt32 | None = None
    worker_ids: list[PositiveInt32] | None = Field(
        default=None,
        description="Новый список ID назначенных исполнителей. Если передан, заменяет текущий список.",
    )

    @field_validator("title", "description", "work_type")
    @classmethod
    def reject_null_character(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("Текст не может содержать нулевой символ")
        return value

    @model_validator(mode="after")
    def validate_intervals(self) -> Self:
        if (
            self.visit_window_start is not None
            and self.visit_window_end is not None
            and self.visit_window_end <= self.visit_window_start
        ):
            raise ValueError("Конец окна визита должен быть позже начала")
        if (
            self.planned_start_at is not None
            and self.planned_end_at is not None
            and self.planned_end_at <= self.planned_start_at
        ):
            raise ValueError("Плановое окончание должно быть позже начала")
        return self


class TicketAssignWorkersRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [TICKET_ASSIGN_WORKERS_EXAMPLE]}
    )

    worker_ids: list[PositiveInt32] = Field(
        description="Полный список ID исполнителей, назначенных на заявку."
    )


class TicketRead(TicketFields):
    model_config = ConfigDict(json_schema_extra={"examples": [TICKET_READ_EXAMPLE]})

    id: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    location: LocationRead
    created_by_id: int | None = None
    created_by: TicketUserRead | None = None
    assignees: list[TicketAssigneeRead] = Field(
        default_factory=list, description="Назначенные исполнители"
    )
