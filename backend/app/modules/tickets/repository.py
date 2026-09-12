"""Literal, parameterized SQL. Transaction boundaries are owned by the service."""

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session


def find_location_id(session: Session, location_id: int) -> int | None:
    # Keep this location from being deleted while its ticket is being inserted.
    return session.execute(
        text("SELECT id FROM locations WHERE id = :location_id FOR KEY SHARE"),
        {"location_id": location_id},
    ).scalar_one_or_none()


def add_ticket(session: Session, values: dict[str, object]) -> int:
    return session.execute(
        text("""
            INSERT INTO tickets (
                location_id, title, description, work_type, status,
                visit_window_start, visit_window_end, planned_start_at, planned_end_at,
                estimated_duration_minutes, actual_duration_minutes
            ) VALUES (
                :location_id, :title, :description, :work_type, :status,
                :visit_window_start, :visit_window_end, :planned_start_at, :planned_end_at,
                :estimated_duration_minutes, :actual_duration_minutes
            )
            RETURNING id
        """),
        values,
    ).scalar_one()


def find_ticket(session: Session, ticket_id: int) -> RowMapping | None:
    return (
        session.execute(
            text("""
            SELECT
                t.id, t.location_id, t.title, t.description, t.work_type, t.status,
                t.visit_window_start, t.visit_window_end, t.planned_start_at, t.planned_end_at,
                t.estimated_duration_minutes, t.actual_duration_minutes,
                t.created_at, t.updated_at,
                c.id AS city_id, c.name AS city,
                s.id AS street_id, s.name AS street,
                b.id AS building_id, b.number AS building_number, b.block,
                l.entrance_id, e.number AS entrance_number,
                l.floor, l.apartment, l.latitude, l.longitude
            FROM tickets AS t
            JOIN locations AS l ON l.id = t.location_id
            JOIN buildings AS b ON b.id = l.building_id
            JOIN streets AS s ON s.id = b.street_id
            JOIN cities AS c ON c.id = s.city_id
            LEFT JOIN entrances AS e ON e.id = l.entrance_id
            WHERE t.id = :ticket_id
        """),
            {"ticket_id": ticket_id},
        )
        .mappings()
        .one_or_none()
    )
