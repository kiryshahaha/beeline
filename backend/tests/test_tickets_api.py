"""HTTP contracts exercised against migrated PostgreSQL, with a fresh session per request."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Building, City, Entrance, Location, Street, Ticket
from app.db.session import get_session
from app.main import app
from app.modules.tickets.enums import TicketStatus
from tests.support import DatabaseTestCase


class TicketsApiTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        city = self.save(City(name="Санкт-Петербург"))
        street = self.save(Street(city_id=city.id, name="Тестовая улица"))
        building = self.save(Building(street_id=street.id, number="12А", block="корпус 2"))
        entrance = self.save(Entrance(building_id=building.id, number="3"))
        self.location = self.save(
            Location(
                building_id=building.id,
                entrance_id=entrance.id,
                apartment="24Б",
                floor=5,
                latitude=59.94,
                longitude=30.32,
            )
        )
        self.location_id = self.location.id
        # Release the fixture savepoint; HTTP sessions share only the outer test transaction.
        self.session.commit()

        def override_session():
            with Session(bind=self.connection, join_transaction_mode="create_savepoint") as session:
                yield session

        app.dependency_overrides[get_session] = override_session
        self.addCleanup(app.dependency_overrides.pop, get_session)
        self.client = self.enterContext(TestClient(app))

    def save(self, instance):
        self.session.add(instance)
        self.session.flush()
        return instance

    def payload(self, **overrides):
        return {
            "location_id": self.location_id,
            "title": "Настроить Wi-Fi",
            "work_type": "Настройка сети",
            "visit_window_start": "2026-09-14T10:00:00+03:00",
            "visit_window_end": "2026-09-14T14:00:00+03:00",
            "estimated_duration_minutes": 60,
        } | overrides

    def create(self, **overrides):
        return self.client.post("/api/v1/tickets", json=self.payload(**overrides))

    def count_tickets(self):
        with Session(bind=self.connection, join_transaction_mode="create_savepoint") as session:
            return session.scalar(select(func.count()).select_from(Ticket))

    def test_post_then_get_with_fresh_session_returns_persisted_ticket_and_address(self):
        response = self.create(title="  Настроить Wi-Fi  ")
        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertEqual(created["title"], "Настроить Wi-Fi")
        self.assertEqual(created["status"], "planned")
        self.assertIsNone(created["planned_start_at"])
        self.assertIsNone(created["actual_duration_minutes"])
        self.assertIsNotNone(datetime.fromisoformat(created["created_at"]).tzinfo)
        self.assertIsNotNone(datetime.fromisoformat(created["updated_at"]).tzinfo)
        self.assertEqual(created["location_id"], self.location_id)
        location = created["location"]
        self.assertEqual(location["id"], self.location_id)
        self.assertEqual(location["apartment"], "24Б")
        self.assertEqual(location["latitude"], 59.94)
        self.assertEqual(location["longitude"], 30.32)
        self.assertEqual(
            location["address"],
            ("Санкт-Петербург, Тестовая улица, д. 12А, корпус 2, подъезд 3, этаж 5, кв./пом. 24Б"),
        )
        fetched = self.client.get(response.headers["Location"])
        self.assertEqual(fetched.status_code, 200)
        read_back = fetched.json()
        for field in ("visit_window_start", "visit_window_end", "created_at", "updated_at"):
            self.assertEqual(
                datetime.fromisoformat(read_back.pop(field)),
                datetime.fromisoformat(created.pop(field)),
            )
        self.assertEqual(read_back, created)
        self.assertEqual(self.count_tickets(), 1)

    def test_manual_duration_and_planned_interval_are_independent(self):
        response = self.create(
            planned_start_at="2026-09-14T11:00:00+03:00",
            planned_end_at="2026-09-14T12:00:00+03:00",
            actual_duration_minutes=75,
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["actual_duration_minutes"], 75)
        response = self.create(actual_duration_minutes=0)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["actual_duration_minutes"], 0)

    def test_all_agreed_statuses_are_accepted(self):
        for status in TicketStatus:
            with self.subTest(status=status):
                response = self.create(status=status.value)
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(response.json()["status"], status.value)

    def test_timezones_are_compared_as_instants(self):
        response = self.create(visit_window_end="2026-09-14T08:00:00Z")
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()
        delta = datetime.fromisoformat(data["visit_window_end"]) - datetime.fromisoformat(
            data["visit_window_start"]
        )
        self.assertEqual(delta, timedelta(hours=1))

    def test_plan_containment_is_not_an_agreed_constraint_yet(self):
        response = self.create(
            planned_start_at="2026-09-14T15:00:00+03:00",
            planned_end_at="2026-09-14T16:00:00+03:00",
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_invalid_inputs_are_422_and_do_not_insert_tickets(self):
        invalid = [
            {"title": " "},
            {"title": "x" * 201},
            {"work_type": ""},
            {"work_type": "x" * 101},
            {"description": "text\x00text"},
            {"status": "unknown"},
            {"location_id": 0},
            {"location_id": -1},
            {"location_id": True},
            {"location_id": "1"},
            {"location_id": 2**31},
            {"estimated_duration_minutes": 0},
            {"estimated_duration_minutes": 2**31},
            {"estimated_duration_minutes": 1.5},
            {"estimated_duration_minutes": True},
            {"actual_duration_minutes": -1},
            {"actual_duration_minutes": 2**31},
            {"actual_duration_minutes": False},
            {"title": None},
            {"status": None},
            {"visit_window_start": "2026-09-14T10:00:00"},
            {"visit_window_end": "2026-09-14T10:00:00+03:00"},
            {"visit_window_end": "2026-09-14T06:00:00Z"},
            {"planned_start_at": "2026-09-14T11:00:00+03:00"},
            {"planned_end_at": "2026-09-14T12:00:00+03:00"},
            {
                "planned_start_at": "2026-09-14T12:00:00+03:00",
                "planned_end_at": "2026-09-14T11:00:00+03:00",
            },
            {"id": 123},
            {"created_at": "2026-09-14T10:00:00Z"},
            {"unexpected": "value"},
        ]
        for values in invalid:
            with self.subTest(values=values):
                self.assertEqual(self.create(**values).status_code, 422)
        for field in (
            "location_id",
            "title",
            "work_type",
            "visit_window_start",
            "visit_window_end",
            "estimated_duration_minutes",
        ):
            payload = self.payload()
            del payload[field]
            with self.subTest(missing=field):
                self.assertEqual(self.client.post("/api/v1/tickets", json=payload).status_code, 422)
        self.assertEqual(self.count_tickets(), 0)

    def test_unknown_location_does_not_create_ticket(self):
        response = self.create(location_id=2_147_483_647)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Место выполнения не найдено"})
        self.assertEqual(self.count_tickets(), 0)

    def test_missing_ticket_and_invalid_path_id(self):
        response = self.client.get("/api/v1/tickets/2147483647")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Заявка не найдена"})
        for ticket_id in ("0", "-1", "text", "2147483648"):
            with self.subTest(ticket_id=ticket_id):
                self.assertEqual(self.client.get(f"/api/v1/tickets/{ticket_id}").status_code, 422)

    def test_building_location_without_coordinates_and_apartment_can_be_read(self):
        self.location.entrance_id = None
        self.location.floor = None
        self.location.apartment = None
        self.location.latitude = None
        self.location.longitude = None
        self.session.commit()
        response = self.create()
        self.assertEqual(response.status_code, 201, response.text)
        location = response.json()["location"]
        for field in (
            "entrance_id",
            "entrance_number",
            "floor",
            "apartment",
            "latitude",
            "longitude",
        ):
            self.assertIsNone(location[field])
        self.assertEqual(location["address"], "Санкт-Петербург, Тестовая улица, д. 12А, корпус 2")

    def test_openapi_exposes_only_two_ticket_operations(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertEqual(set(paths), {"/health", "/api/v1/tickets", "/api/v1/tickets/{id}"})
        self.assertEqual(set(paths["/api/v1/tickets"]), {"post"})
        self.assertEqual(set(paths["/api/v1/tickets/{id}"]), {"get"})
