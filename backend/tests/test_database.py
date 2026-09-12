"""Integration tests use migrations and a unique schema in a dedicated test database."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.models import Building, City, Entrance, Location, Street, Ticket
from app.modules.tickets.enums import TicketStatus


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database_url = os.getenv("TEST_DATABASE_URL")
        if not database_url:
            raise unittest.SkipTest("Set TEST_DATABASE_URL for PostgreSQL integration tests")
        parsed_url = make_url(database_url)
        if (
            parsed_url.get_backend_name() != "postgresql"
            or not (parsed_url.database or "").endswith("_test")
        ):
            raise RuntimeError(
                "TEST_DATABASE_URL must point to a PostgreSQL database ending in _test"
            )

        cls.schema = "beeline_test_" + uuid4().hex
        cls.admin_engine = create_engine(database_url)
        cls.addClassCleanup(cls.admin_engine.dispose)
        with cls.admin_engine.begin() as connection:
            connection.execute(CreateSchema(cls.schema))
        cls.addClassCleanup(cls.drop_schema)
        cls.engine = create_engine(
            database_url, connect_args={"options": f"-csearch_path={cls.schema}"}
        )
        cls.addClassCleanup(cls.engine.dispose)

        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with cls.engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.downgrade(config, "base")
            if set(inspect(connection).get_table_names()) - {"alembic_version"}:
                raise AssertionError("Downgrade left domain tables behind")
            connection.commit()
            command.upgrade(config, "head")
            command.check(config)

    @classmethod
    def drop_schema(cls):
        with cls.admin_engine.begin() as connection:
            connection.execute(DropSchema(cls.schema, cascade=True))

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        self.addCleanup(self.connection.close)
        self.addCleanup(self.transaction.rollback)
        self.addCleanup(self.session.close)

        self.city = self.save(City(name="Санкт-Петербург"))
        self.street = self.save(Street(city_id=self.city.id, name="улица Ленина"))
        self.building = self.save(Building(street_id=self.street.id, number="12А"))
        self.entrance = self.save(Entrance(building_id=self.building.id, number="1"))
        self.location = self.save(Location(
            building_id=self.building.id,
            entrance_id=self.entrance.id,
            apartment="24Б",
            floor=5,
            latitude=Decimal("59.940000"),
            longitude=Decimal("30.320000"),
        ))
        self.window_start = datetime(2026, 9, 12, 10, tzinfo=timezone(timedelta(hours=3)))

    def save(self, model):
        self.session.add(model)
        self.session.flush()
        return model

    def ticket(self, **overrides):
        values = {
            "location_id": self.location.id,
            "title": "Настроить Wi-Fi",
            "work_type": "Настройка сети",
            "visit_window_start": self.window_start,
            "visit_window_end": self.window_start + timedelta(hours=4),
            "estimated_duration_minutes": 60,
        }
        return Ticket(**(values | overrides))

    def rejected(self, model):
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.save(model)

    def test_two_tickets_share_apartment_and_keep_manual_duration(self):
        first = self.save(self.ticket(
            planned_start_at=self.window_start + timedelta(hours=1),
            planned_end_at=self.window_start + timedelta(hours=2),
            actual_duration_minutes=75,
        ))
        second = self.save(self.ticket(title="Проверить соединение"))
        self.session.expire_all()
        self.assertEqual(first.location_id, second.location_id)
        self.assertEqual(first.actual_duration_minutes, 75)
        self.assertEqual(second.status, TicketStatus.PLANNED)
        self.assertIsNone(second.actual_duration_minutes)
        self.assertIsNone(second.planned_start_at)
        self.assertEqual(first.visit_window_start, self.window_start)
        self.assertIsNotNone(first.created_at.tzinfo)

    def test_city_duplicate_is_case_insensitive_in_cyrillic(self):
        self.rejected(City(name="санкт-петербург"))

    def test_street_duplicate_is_scoped_to_city(self):
        self.rejected(Street(city_id=self.city.id, name="УЛИЦА ЛЕНИНА"))
        other_city = self.save(City(name="Москва"))
        other_street = self.save(Street(city_id=other_city.id, name="улица Ленина"))
        self.assertNotEqual(other_street.id, self.street.id)

    def test_building_without_block_cannot_be_duplicated(self):
        self.rejected(Building(street_id=self.street.id, number="12а"))

    def test_buildings_with_different_blocks_are_distinct(self):
        other_building = self.save(
            Building(street_id=self.street.id, number="12А", block="корпус 2")
        )
        self.assertNotEqual(other_building.id, self.building.id)

    def test_entrance_duplicate_is_scoped_to_building(self):
        self.rejected(Entrance(building_id=self.building.id, number="1"))
        other_building = self.save(Building(street_id=self.street.id, number="14"))
        other_entrance = self.save(Entrance(building_id=other_building.id, number="1"))
        self.assertNotEqual(other_entrance.id, self.entrance.id)

    def test_apartment_duplicate_cannot_be_disguised_by_floor(self):
        self.rejected(Location(
            building_id=self.building.id, entrance_id=self.entrance.id, apartment="24б", floor=7
        ))

    def test_location_with_unspecified_entrance_and_apartment_is_unique(self):
        self.save(Location(building_id=self.building.id))
        self.rejected(Location(building_id=self.building.id))

    def test_entrance_from_another_building_is_rejected(self):
        other_building = self.save(Building(street_id=self.street.id, number="14"))
        self.rejected(Location(building_id=other_building.id, entrance_id=self.entrance.id))

    def test_invalid_coordinate_pairs_are_rejected(self):
        invalid_pairs = [(60, None), (None, 30), (91, 30), (60, 181), (-91, 0), (0, -181)]
        for latitude, longitude in invalid_pairs:
            with self.subTest(latitude=latitude, longitude=longitude):
                self.rejected(Location(
                    building_id=self.building.id, latitude=latitude, longitude=longitude
                ))

    def test_coordinate_boundaries_and_missing_coordinates_are_allowed(self):
        self.save(
            Location(building_id=self.building.id, apartment="1", latitude=-90, longitude=180)
        )
        self.save(
            Location(building_id=self.building.id, apartment="2", latitude=90, longitude=-180)
        )
        self.save(Location(building_id=self.building.id, apartment="3"))

    def test_invalid_intervals_and_durations_are_rejected(self):
        invalid_values = [
            {"visit_window_end": self.window_start},
            {"planned_start_at": self.window_start},
            {"planned_end_at": self.window_start},
            {"planned_start_at": self.window_start, "planned_end_at": self.window_start},
            {"estimated_duration_minutes": 0},
            {"estimated_duration_minutes": -1},
            {"actual_duration_minutes": -1},
        ]
        for values in invalid_values:
            with self.subTest(values=values):
                self.rejected(self.ticket(**values))

    def test_zero_manual_duration_is_distinct_from_missing(self):
        ticket = self.save(self.ticket(actual_duration_minutes=0))
        self.session.refresh(ticket)
        self.assertEqual(ticket.actual_duration_minutes, 0)

    def test_status_is_checked_by_database(self):
        self.rejected(self.ticket(status="unknown"))
        for status in TicketStatus:
            with self.subTest(status=status):
                ticket = self.save(self.ticket(status=status))
                self.session.refresh(ticket)
                self.assertEqual(ticket.status, status)

    def test_blank_directory_names_and_ticket_titles_are_rejected(self):
        for name in ["", " ", " Москва", "Москва "]:
            with self.subTest(name=name):
                self.rejected(City(name=name))
        self.rejected(self.ticket(title=" "))

    def test_referenced_location_cannot_be_deleted(self):
        self.save(self.ticket())
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.execute(delete(Location).where(Location.id == self.location.id))

    def test_report_groups_tickets_by_city_through_directory(self):
        self.save(self.ticket())
        self.save(self.ticket())
        other_city = self.save(City(name="Москва"))
        other_street = self.save(Street(city_id=other_city.id, name="улица Ленина"))
        other_building = self.save(Building(street_id=other_street.id, number="12А"))
        other_location = self.save(Location(building_id=other_building.id, apartment="24Б"))
        self.save(self.ticket(location_id=other_location.id, status=TicketStatus.COMPLETED))
        report = self.session.execute(
            select(City.id, Ticket.status, func.count(Ticket.id))
            .select_from(Ticket)
            .join(Location, Location.id == Ticket.location_id)
            .join(Building, Building.id == Location.building_id)
            .join(Street, Street.id == Building.street_id)
            .join(City, City.id == Street.city_id)
            .group_by(City.id, Ticket.status)
        ).all()
        self.assertCountEqual(report, [
            (self.city.id, TicketStatus.PLANNED, 2),
            (other_city.id, TicketStatus.COMPLETED, 1),
        ])
