"""Fill an existing, migrated database: python seed_demo.py [--date YYYY-MM-DD]."""

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_engine

MOSCOW_TIME = timezone(timedelta(hours=3))
CITY_NAME = "Санкт-Петербург"


@dataclass(frozen=True)
class DemoVisit:
    street: str
    building: str
    latitude: str
    longitude: str
    source_url: str
    title: str
    work_type: str
    start_hour: int
    end_hour: int
    duration_minutes: int


# Address/coordinate pairs checked on 2026-09-12; jobs and windows are fictional.
# These are map points for buildings, not verified vehicle access or apartment positions.
DEMO_VISITS = (
    DemoVisit(
        "Лиговский проспект",
        "30",
        "59.927563",
        "30.360613",
        "https://yandex.by/maps/2/saint-petersburg/house/ligovskiy_prospekt_30/"
        "Z0kYdQFgT0QEQFtjfXVzdnllZw==/",
        "[Демо] Настроить Wi-Fi",
        "Настройка сети",
        9,
        13,
        60,
    ),
    DemoVisit(
        "Инженерная улица",
        "4",
        "59.938694",
        "30.332595",
        "https://roskarta.net/Санкт-Петербург/Инженерная_улица/4",
        "[Демо] Проверить соединение",
        "Диагностика сети",
        10,
        14,
        45,
    ),
    DemoVisit(
        "Большой проспект Петроградской стороны",
        "84",
        "59.9644",
        "30.3092",
        "https://spb.ginfo.ru/ulicy/bolshoy_prospekt_petrogradskoy_storony/84/",
        "[Демо] Заменить маршрутизатор",
        "Замена оборудования",
        11,
        16,
        60,
    ),
    DemoVisit(
        "Московский проспект",
        "111",
        "59.88911",
        "30.318734",
        "https://stilnaya.com/contacts/stores/64455/",
        "[Демо] Проверить кабель",
        "Диагностика сети",
        9,
        12,
        30,
    ),
    DemoVisit(
        "Библиотечный переулок",
        "4",
        "59.9068",
        "30.2967",
        "https://spb.ginfo.ru/ulicy/bibliotechnyy_pereulok/4/",
        "[Демо] Подключить точку доступа",
        "Настройка сети",
        13,
        18,
        90,
    ),
    DemoVisit(
        "Университетская набережная",
        "13",
        "59.939271",
        "30.298162",
        "https://roskarta.net/Санкт-Петербург/Университетская_набережная/13",
        "[Демо] Проверить покрытие Wi-Fi",
        "Диагностика сети",
        14,
        18,
        45,
    ),
)
# The Moscow Avenue source lists longitude first; fields above are latitude, longitude.


@dataclass(frozen=True)
class SeedResult:
    ticket_id: int
    location_id: int
    address: str
    created: bool


def get_or_create_id(session: Session, find_sql: str, insert_sql: str, parameters: dict) -> int:
    """Execute the literal SQL supplied below; values are always bound separately."""
    existing_id = session.execute(text(find_sql), parameters).scalar_one_or_none()
    if existing_id is not None:
        return existing_id
    return session.execute(text(insert_sql), parameters).scalar_one()


def seed_data(session: Session, visit_date: date) -> list[SeedResult]:
    """Caller owns the transaction. Existing tickets and filled coordinates are preserved."""
    # Serialize copies of this script; the lock is released on commit or rollback.
    session.execute(text("SELECT pg_advisory_xact_lock(20260912, 1)"))
    city_id = get_or_create_id(
        session,
        "SELECT id FROM cities WHERE lower(name) = lower(:name)",
        "INSERT INTO cities (name) VALUES (:name) RETURNING id",
        {"name": CITY_NAME},
    )
    results = []
    for visit in DEMO_VISITS:
        street_id = get_or_create_id(
            session,
            """
            SELECT id FROM streets
            WHERE city_id = :city_id AND lower(name) = lower(:name)
            """,
            "INSERT INTO streets (city_id, name) VALUES (:city_id, :name) RETURNING id",
            {"city_id": city_id, "name": visit.street},
        )
        building_id = get_or_create_id(
            session,
            """
            SELECT id FROM buildings
            WHERE street_id = :street_id AND lower(number) = lower(:number) AND block IS NULL
            """,
            "INSERT INTO buildings (street_id, number) VALUES (:street_id, :number) RETURNING id",
            {"street_id": street_id, "number": visit.building},
        )
        coordinates = {"latitude": Decimal(visit.latitude), "longitude": Decimal(visit.longitude)}
        location = (
            session.execute(
                text("""
                SELECT id, latitude, longitude FROM locations
                WHERE building_id = :building_id AND entrance_id IS NULL AND apartment IS NULL
                FOR UPDATE
            """),
                {"building_id": building_id},
            )
            .mappings()
            .one_or_none()
        )
        if location is None:
            location = (
                session.execute(
                    text("""
                    INSERT INTO locations (building_id, latitude, longitude)
                    VALUES (:building_id, :latitude, :longitude)
                    RETURNING id, latitude, longitude
                """),
                    {"building_id": building_id, **coordinates},
                )
                .mappings()
                .one()
            )

        location_id = location["id"]
        if location["latitude"] is None and location["longitude"] is None:
            session.execute(
                text("""
                    UPDATE locations SET latitude = :latitude, longitude = :longitude
                    WHERE id = :location_id
                """),
                {"location_id": location_id, **coordinates},
            )
        elif (
            location["latitude"] != coordinates["latitude"]
            or location["longitude"] != coordinates["longitude"]
        ):
            raise RuntimeError(
                f"У location_id={location_id} уже другие координаты. "
                "Заполнение отменено: проверьте это место вручную."
            )

        # Natural key for this fixed demo set; dates/statuses are not overwritten on reruns.
        ticket_id = session.execute(
            text("SELECT id FROM tickets WHERE location_id = :location_id AND title = :title"),
            {"location_id": location_id, "title": visit.title},
        ).scalar()
        created = ticket_id is None
        if created:
            ticket_id = session.execute(
                text("""
                    INSERT INTO tickets (
                        location_id, title, description, work_type,
                        visit_window_start, visit_window_end, estimated_duration_minutes
                    ) VALUES (
                        :location_id, :title, :description, :work_type,
                        :visit_window_start, :visit_window_end, :estimated_duration_minutes
                    )
                    RETURNING id
                """),
                {
                    "location_id": location_id,
                    "title": visit.title,
                    "description": (
                        "Учебная заявка: работа, длительность и окно визита вымышлены. "
                        "Это не сообщение о реальной неисправности по данному адресу."
                    ),
                    "work_type": visit.work_type,
                    "visit_window_start": datetime.combine(
                        visit_date, time(visit.start_hour), MOSCOW_TIME
                    ),
                    "visit_window_end": datetime.combine(
                        visit_date, time(visit.end_hour), MOSCOW_TIME
                    ),
                    "estimated_duration_minutes": visit.duration_minutes,
                },
            ).scalar_one()
        results.append(
            SeedResult(
                ticket_id=ticket_id,
                location_id=location_id,
                address=f"{CITY_NAME}, {visit.street}, {visit.building}",
                created=created,
            )
        )
    return results


def run_seed(engine: Engine, visit_date: date) -> list[SeedResult]:
    """Check schema and commit the entire data set atomically; never create/drop tables."""
    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    with engine.begin() as connection:
        actual_heads = set(MigrationContext.configure(connection).get_current_heads())
        if actual_heads != expected_heads:
            raise RuntimeError(
                "Сначала примените схему БД: python -m alembic upgrade head. "
                "Затем повторите python seed_demo.py."
            )
        with Session(bind=connection) as session:
            return seed_data(session, visit_date)


def main() -> int:
    parser = argparse.ArgumentParser(description="Заполнить БД демозаявками в Санкт-Петербурге.")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=datetime.now(MOSCOW_TIME).date(),
        help="Дата окон новых заявок, YYYY-MM-DD. По умолчанию сегодня, UTC+03:00.",
    )
    args = parser.parse_args()
    try:
        results = run_seed(get_engine(), args.date)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (SQLAlchemyError, ValidationError):
        print(
            "Не удалось заполнить БД. Изменения этого запуска отменены. "
            "Проверьте PostgreSQL, DATABASE_URL в .env и применённые миграции.",
            file=sys.stderr,
        )
        return 1
    created_count = sum(result.created for result in results)
    print(
        f"Готово. Создано заявок: {created_count}; "
        f"уже существовало: {len(results) - created_count}."
    )
    for result in results:
        print(f"ticket_id={result.ticket_id}; location_id={result.location_id}; {result.address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
