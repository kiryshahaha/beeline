"""Demo data is repeatable, preserves existing records and needs no geocoding network call."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import func, select

from app.db.models import Building, City, Entrance, Location, Street, Ticket
from app.modules.tickets.enums import TicketStatus
from seed_demo import DEMO_VISITS, MOSCOW_TIME, seed_data
from tests.support import DatabaseTestCase


class SeedDemoTests(DatabaseTestCase):
    visit_date = date(2026, 9, 14)

    def counts(self):
        return [
            self.session.scalar(select(func.count()).select_from(model))
            for model in (City, Street, Building, Entrance, Location, Ticket)
        ]

    def test_complete_data_set_uses_one_city_and_six_map_points(self):
        results = seed_data(self.session, self.visit_date)
        self.assertEqual(self.counts(), [1, 6, 6, 0, 6, 6])
        self.assertTrue(all(result.created for result in results))
        for result, visit in zip(results, DEMO_VISITS, strict=True):
            ticket = self.session.get(Ticket, result.ticket_id)
            location = self.session.get(Location, result.location_id)
            self.assertEqual(location.latitude, Decimal(visit.latitude))
            self.assertEqual(location.longitude, Decimal(visit.longitude))
            self.assertIsNone(location.apartment)
            self.assertIsNone(location.entrance_id)
            local_start = ticket.visit_window_start.astimezone(MOSCOW_TIME)
            self.assertEqual(local_start.date(), self.visit_date)
            self.assertEqual(local_start.hour, visit.start_hour)
            self.assertEqual(ticket.status, TicketStatus.PLANNED)
            self.assertIsNone(ticket.planned_start_at)
            self.assertIsNone(ticket.actual_duration_minutes)

    def test_rerun_even_on_another_day_keeps_ids_and_manual_edits(self):
        first = seed_data(self.session, self.visit_date)
        ticket = self.session.get(Ticket, first[0].ticket_id)
        original_window = ticket.visit_window_start
        ticket.status = TicketStatus.COMPLETED
        ticket.actual_duration_minutes = 75
        ticket.description = "Пояснение после выполнения"
        self.session.flush()
        second = seed_data(self.session, self.visit_date + timedelta(days=1))
        self.assertEqual([r.ticket_id for r in first], [r.ticket_id for r in second])
        self.assertFalse(any(result.created for result in second))
        self.assertEqual(self.counts(), [1, 6, 6, 0, 6, 6])
        self.session.expire_all()
        self.assertEqual(ticket.visit_window_start, original_window)
        self.assertEqual(ticket.status, TicketStatus.COMPLETED)
        self.assertEqual(ticket.actual_duration_minutes, 75)
        self.assertEqual(ticket.description, "Пояснение после выполнения")

    def test_existing_directory_is_reused_case_insensitively(self):
        city = City(name="санкт-петербург")
        self.session.add(city)
        self.session.flush()
        street = Street(city_id=city.id, name=DEMO_VISITS[0].street.upper())
        self.session.add(street)
        self.session.flush()
        building = Building(street_id=street.id, number=DEMO_VISITS[0].building)
        self.session.add(building)
        self.session.flush()
        location = Location(building_id=building.id)
        self.session.add(location)
        self.session.flush()
        results = seed_data(self.session, self.visit_date)
        self.session.refresh(location)
        self.assertEqual(results[0].location_id, location.id)
        self.assertEqual(self.counts(), [1, 6, 6, 0, 6, 6])
        self.assertEqual(location.latitude, Decimal(DEMO_VISITS[0].latitude))
        self.assertEqual(city.name, "санкт-петербург")

    def test_coordinate_conflict_rolls_back_the_whole_attempt(self):
        results = seed_data(self.session, self.visit_date)
        # Leave only the last ticket, so a failed rerun first attempts five inserts.
        for result in results[:-1]:
            self.session.delete(self.session.get(Ticket, result.ticket_id))
        location = self.session.get(Location, results[-1].location_id)
        location.latitude = Decimal("59.950000")
        self.session.flush()
        with self.assertRaisesRegex(RuntimeError, "другие координаты"):
            with self.session.begin_nested():
                seed_data(self.session, self.visit_date)
        self.assertEqual(self.counts(), [1, 6, 6, 0, 6, 1])
        self.assertEqual(location.latitude, Decimal("59.950000"))

    def test_existing_non_demo_ticket_at_same_address_is_preserved(self):
        results = seed_data(self.session, self.visit_date)
        demo = self.session.get(Ticket, results[0].ticket_id)
        real = Ticket(
            location_id=demo.location_id,
            title="Обычная заявка",
            work_type=demo.work_type,
            estimated_duration_minutes=30,
            visit_window_start=demo.visit_window_start,
            visit_window_end=demo.visit_window_end,
        )
        self.session.add(real)
        self.session.flush()
        seed_data(self.session, self.visit_date)
        self.assertEqual(self.counts(), [1, 6, 6, 0, 6, 7])
        self.assertEqual(self.session.get(Ticket, real.id).title, "Обычная заявка")

    def test_quotes_in_demo_values_are_saved_as_text(self):
        visit = replace(DEMO_VISITS[0], title="[Демо] Офис 'Север'; SELECT 1 --")
        with patch("seed_demo.DEMO_VISITS", (visit,)):
            first = seed_data(self.session, self.visit_date)
            second = seed_data(self.session, self.visit_date)
        ticket = self.session.get(Ticket, first[0].ticket_id)
        self.assertEqual(ticket.title, visit.title)
        self.assertEqual(first[0].ticket_id, second[0].ticket_id)
        self.assertEqual(self.counts(), [1, 1, 1, 0, 1, 1])
